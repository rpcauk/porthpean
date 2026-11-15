"""Progress parser and real PTY streaming tests with harmless synthetic workers."""
import importlib.util
import os
import pathlib
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
HELPER = ROOT / 'workstation/arch/progress.py'
spec = importlib.util.spec_from_file_location('installer_progress', HELPER)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProgressTests(unittest.TestCase):
    def test_package_progress_has_real_percentage_and_package_position(self):
        value, message = module.progress('( 12/201) installing linux-lts [#####] 37%', 'Arch base')
        self.assertEqual(value, 37)
        self.assertIn('linux-lts (12/201)', message)

    def test_download_progress_and_control_sequences(self):
        value, message = module.progress('\x1b[2K linux-6.12-x86_64 50 MiB [###] 61%\x1b[0m', 'Downloading')
        self.assertEqual(value, 61)
        self.assertEqual(message, 'Downloading')
        self.assertNotIn('\x1b', message)

    def test_work_without_percentage_does_not_invent_one(self):
        value, message = module.progress('Building initramfs', 'Boot images')
        self.assertIsNone(value)
        self.assertEqual(message, 'Boot images')

    def test_gauge_output_cannot_be_injected_by_command_output(self):
        frame = module.frame(50, 'stage\nXXX\nmalicious text').decode()
        self.assertEqual(frame.splitlines().count('XXX'), 2)

    def run_worker(self, code, stdin=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        folder = pathlib.Path(directory.name)
        frames = folder / 'frames'
        viewer = folder / 'gauge.py'
        viewer.write_text('import pathlib,sys\npathlib.Path(sys.argv[1]).write_bytes(sys.stdin.buffer.read())\n')
        log = folder / 'install.log'
        with open(os.devnull, 'wb') as terminal:
            status = module.run_command([sys.executable, '-c', textwrap.dedent(code)], 'Test stage', str(log),
                                        terminal=terminal, stdin=stdin,
                                        gauge_command=[sys.executable, str(viewer), str(frames)])
        return status, log.read_text(), frames.read_text(), log.stat().st_mode & 0o777

    def test_actual_tty_output_streams_into_gauge(self):
        status, log, frames, mode = self.run_worker('''
            import os,time
            assert os.isatty(1) and os.isatty(2)
            print('(1/2) installing sample [###] 42%', flush=True)
            time.sleep(0.15)
            print('(2/2) installing next [###] 81%', flush=True)
            time.sleep(0.15)
        ''')
        self.assertEqual(status, 0)
        self.assertIn('Installing sample (1/2)', frames)
        self.assertIn('Installing next (2/2)', frames)
        self.assertIn('\n42\n', frames)
        self.assertIn('\n81\n', frames)
        self.assertIn('Exit status: 0', log)
        self.assertEqual(mode, 0o600)

    def test_child_environment_disables_interactive_pagers(self):
        status, _, _, _ = self.run_worker("""
            import os
            assert os.environ['LC_ALL'] == 'C.UTF-8'
            for key in ['SYSTEMD_PAGER', 'PAGER', 'GIT_PAGER']:
                assert os.environ[key] == 'cat', key
        """)
        self.assertEqual(status, 0)

    def test_package_marker_persists_without_raw_output(self):
        status, log, frames, _ = self.run_worker("""
            print('PORTHPEAN_PACKAGE 2/3 niri', flush=True)
            print('very long raw pacman output', flush=True)
        """)
        self.assertEqual(status, 0)
        self.assertIn('Package 2/3: niri', frames)
        self.assertNotIn('very long raw pacman output', frames)
        self.assertIn('very long raw pacman output', log)

    def test_failure_returns_real_status_without_false_completion(self):
        status, log, frames, _ = self.run_worker('''
            import sys
            print('synthetic package failure', flush=True)
            sys.exit(7)
        ''')
        self.assertEqual(status, 7)
        self.assertIn('synthetic package failure', log)
        self.assertNotIn('\n100\n', frames)

    def test_secret_stdin_is_not_a_tty_and_is_not_logged(self):
        reader, writer = os.pipe()
        os.write(writer, b'synthetic-secret')
        os.close(writer)
        with os.fdopen(reader, 'rb') as source:
            status, log, frames, _ = self.run_worker('''
                import os,sys
                assert not os.isatty(0)
                assert sys.stdin.buffer.read() == b'synthetic-secret'
                print('Operation finished', flush=True)
            ''', stdin=source)
        self.assertEqual(status, 0)
        self.assertNotIn('synthetic-secret', log + frames)

    def test_standalone_installer_embeds_identical_helper(self):
        text = (ROOT / 'arch-install.sh').read_text()
        embedded = text.split("<<'PORTHPEAN_PROGRESS_PY'\n", 1)[1].split('\nPORTHPEAN_PROGRESS_PY\n', 1)[0]
        self.assertEqual(embedded, HELPER.read_text().rstrip('\n'))


if __name__ == '__main__':
    unittest.main()
