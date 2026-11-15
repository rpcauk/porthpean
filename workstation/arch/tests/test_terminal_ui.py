import pathlib
import subprocess
import tempfile
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]

class TerminalUI(unittest.TestCase):
    def test_output_is_visible_logged_and_failure_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            log = pathlib.Path(directory) / 'install.log'
            result = subprocess.run(['bash', '-c',
                'source "$1/ui.sh"; install_log=$2; run_progress Testing bash -c "echo output; echo failure >&2; exit 47"',
                'test', str(BASE), str(log)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 47)
            self.assertIn('== Testing ==', result.stdout)
            self.assertIn('output', result.stdout)
            self.assertIn('failure', result.stdout)
            self.assertEqual(log.read_text(), 'output\nfailure\n')

    def test_yay_receives_configured_privilege_options(self):
        result = subprocess.check_output(['bash', '-c',
            'source "$1/aur.sh"; aur_as_user() { printf "%s\\n" "$@"; }; aur_yay -S --needed example',
            'test', str(BASE)], text=True)
        self.assertEqual(result.splitlines(), ['/usr/bin/yay', '--sudo', '/usr/bin/sudo',
                         '--sudoflags=-n', '--sudoloop=false', '-S', '--needed', 'example'])
        self.assertNotIn('--sudobin', (BASE / 'install-citrix').read_text())

    def test_installers_do_not_use_removed_yay_options(self):
        for name in ('aur.sh',):
            text = (BASE / name).read_text()
            self.assertNotIn('--nosudoloop', text)
            self.assertNotIn('--sudobin', text)
            self.assertIn('--sudoloop=false', text)
