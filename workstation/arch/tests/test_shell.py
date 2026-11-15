import concurrent.futures
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest

BASE = Path(__file__).resolve().parents[1]
HISTORY = BASE / 'files/porthpean-shell-history'


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class HistoryTests(unittest.TestCase):
    def test_concurrent_multiline_unicode_and_private_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state/history'
            commands = [f'print "héllo {i}\nsecond line"\n' for i in range(24)]
            def append(command):
                subprocess.run([str(HISTORY), 'append', str(path)], input=command, text=True, check=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(append, commands))
            append(' hidden secret\n')
            append(commands[0])
            records = [json.loads(line)['command'] for line in path.read_text().splitlines()]
            self.assertEqual(len(records), 25)
            listed = subprocess.check_output([str(HISTORY), 'list', str(path)]).decode().split('\0')[:-1]
            self.assertEqual(len(listed), 24)
            self.assertEqual(listed[0], commands[0].rstrip('\n'))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn('hidden secret', path.read_text())

    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / 'target'
            target.write_text('original')
            link = Path(temp) / 'history'
            link.symlink_to(target)
            result = subprocess.run([str(HISTORY), 'append', str(link)], input='hello', text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), 'original')

    def test_partial_write_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'history'
            path.write_text('{"interrupted":')
            subprocess.run([str(HISTORY), 'append', str(path)], input='new command\n', text=True, check=True)
            self.assertEqual(subprocess.check_output([str(HISTORY), 'list', str(path)]), b'new command\0')


class Shell:
    def __init__(self, home):
        master, slave = pty.openpty()
        self.master = master
        env = dict(os.environ, HOME=str(home), ZDOTDIR=str(home / '.config/zsh'),
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_CACHE_HOME=str(home / '.cache'),
                   XDG_STATE_HOME=str(home / '.local/state'), PORTHPEAN_NO_TMUX='1',
                   TERM='xterm-256color', PATH=str(home / '.local/bin') + ':' + os.environ['PATH'])
        env.pop('TMUX', None)
        self.process = subprocess.Popen(['zsh', '-d', '-i'], stdin=slave, stdout=slave, stderr=slave, env=env)
        os.close(slave)
        self.read()
    def read(self):
        result = b''
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if select.select([self.master], [], [], 0.15)[0]:
                try:
                    result += os.read(self.master, 65536)
                except OSError:
                    break
            elif result:
                break
        return result
    def send(self, command):
        os.write(self.master, command.encode())
        return self.read()
    def close(self):
        self.send('exit\n')
        self.process.wait(timeout=5)
        os.close(self.master)


@unittest.skipUnless(shutil.which('zsh'), 'Zsh needed')
class InteractiveTests(unittest.TestCase):
    def test_two_real_shells_prompt_widgets_and_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            config = home / '.config/zsh'
            config.mkdir(parents=True)
            shutil.copy(BASE / 'files/shell/zshrc', config / '.zshrc')
            shutil.copy(BASE / 'files/shell/zshenv', home / '.zshenv')
            binary = home / '.local/bin'
            binary.mkdir(parents=True)
            (binary / 'porthpean-shell-history').symlink_to(HISTORY)
            # A deterministic selector lets the real ZLE widgets run without fzf's UI.
            (binary / 'fzf').write_text('#!/usr/bin/env python3\nimport sys,os\nfrom pathlib import Path\npick=(Path(os.environ["HOME"])/"pick").read_text()\nitems=sys.stdin.buffer.read().split(b"\\0")\nfor item in items:\n if item.decode()==pick:\n  sys.stdout.buffer.write(item+b"\\0");break\nelse: sys.exit(1)\n')
            (binary / 'fzf').chmod(0o700)
            first, second = Shell(home), Shell(home)
            try:
                first.send('print -r -- FIRST_ONLY\n')
                second.send('print -r -- SECOND_ONLY\n')
                first.send('_porthpean_session_history > "$HOME/session"\n')
                self.assertNotIn('SECOND_ONLY', (home / 'session').read_text())
                self.assertIn('FIRST_ONLY', (home / 'session').read_text())
                first.send('print -r -- "$HISTFILE" > "$HOME/first-file"\n')
                second.send('print -r -- "$HISTFILE" > "$HOME/second-file"\n')
                files = [(home / name).read_text().strip() for name in ['first-file', 'second-file']]
                self.assertNotEqual(*files)
                # Alt+R cannot select the other shell's command.
                (home / 'pick').write_text('print -r -- SECOND_ONLY')
                output = first.send('\x1br')
                self.assertNotIn(b'SECOND_ONLY', output)
                # Ctrl+R can recall it; selection does not execute until Enter.
                output = first.send('\x12')
                self.assertIn(b'SECOND_ONLY', output)
                output = first.send('\n')
                self.assertIn(b'SECOND_ONLY', output)
                first.send('print -r -- UP_OWN\n')
                output = first.send('\x1b[A\n')
                self.assertIn(b'UP_OWN', output)
                output = first.send('false\n')
                self.assertIn(b'\x1b[31m$', output)
                output = first.send('true\n')
                self.assertIn(b'\x1b[37m$', output)
                first.send(' hidden_not_a_command\n')
                self.assertNotIn('hidden_not_a_command', (home / '.local/state/zsh/history.jsonl').read_text())
            finally:
                first.close()
                second.close()
            for path in files:
                self.assertFalse(Path(path).parent.exists(), 'session temporary directory should be removed')


class ZoomTests(unittest.TestCase):
    def test_idempotent_preserves_channels_comments_and_crlf(self):
        zoom = load('zoom_config', BASE / 'files/zoom/configure.py')
        source = '; Keep me\r\n[ICA3.0]\r\nVirtualDriver=Thinwire,Other\r\n\r\n[Other]\r\nDriverName=Other.so\r\n'
        result = zoom.configure(source)
        self.assertEqual(result, zoom.configure(result))
        self.assertIn('VirtualDriver=Thinwire,Other,ZoomMedia\r\nZoomMedia=On', result)
        self.assertIn('; Keep me\r\n', result)
        self.assertIn('DriverName=Other.so', result)
        self.assertIn('[ZoomMedia]\r\nDriverName=ZoomMedia.so', result)
        with self.assertRaises(ValueError):
            zoom.configure('VirtualDriver=A\nVirtualDriver=B\n')


class PyreTests(unittest.TestCase):
    def test_private_environment_and_symlink_dispatch(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            binary = home / 'bin'
            library = binary / 'lib'
            library.mkdir(parents=True)
            shutil.copy(BASE / 'files/shell/pyre', binary / 'pyre')
            (binary / 'hello').symlink_to('pyre')
            (library / 'hello.py').write_text('import sys; print("hello", sys.argv[1])')
            env = dict(os.environ, HOME=str(home), XDG_CACHE_HOME=str(home / 'cache'))
            output = subprocess.check_output([str(binary / 'hello'), 'world'], env=env, text=True)
            self.assertEqual(output.strip(), 'hello world')
            self.assertEqual((home / 'cache/pyre').stat().st_mode & 0o777, 0o700)
            self.assertEqual(len(list((home / 'cache/pyre').glob('*/bin/python'))), 1)
            self.assertEqual(subprocess.check_output([str(binary / 'hello'), 'again'], env=env, text=True).strip(), 'hello again')
