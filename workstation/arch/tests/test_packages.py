import os
import pathlib
import subprocess
import tempfile
import unittest

HELPER = pathlib.Path(__file__).resolve().parents[1] / 'install-packages'

class Packages(unittest.TestCase):
    def run_packages(self, packages):
        with tempfile.TemporaryDirectory() as tmp:
            fake = pathlib.Path(tmp) / 'pacman'
            fake.write_text('#!/bin/bash\nprintf "transaction:%s\\n" "$*"\n[[ ${@: -1} != broken ]]\n')
            fake.chmod(0o755)
            return subprocess.run(['bash', str(HELPER), *packages], env=dict(os.environ, PATH=tmp + ':' + os.environ['PATH']), text=True, capture_output=True)

    def test_separate_transactions(self):
        result = self.run_packages(['foot', 'niri'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PORTHPEAN_PACKAGE 2/2 niri', result.stdout)
        self.assertIn('transaction:-S --needed --noconfirm foot', result.stdout)
        self.assertIn('transaction:-S --needed --noconfirm niri', result.stdout)

    def test_failure_stops_before_next_package(self):
        result = self.run_packages(['foot', 'broken', 'niri'])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('niri', result.stdout)
