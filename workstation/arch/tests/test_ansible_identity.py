"""Exercise the real Zoom guard only; never run package or Citrix tasks."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
ANSIBLE = shutil.which('ansible-playbook')


@unittest.skipUnless(ANSIBLE, 'ansible-playbook needed')
class IdentityGuard(unittest.TestCase):
    def test_effective_uid_controls_root_check_despite_inherited_username(self):
        for uid, username, expected in [(0, 'ryan', 0), (1000, 'root', 2)]:
            with self.subTest(uid=uid, username=username), tempfile.TemporaryDirectory() as directory:
                overrides = {'ansible_python_interpreter': sys.executable,
                    'ansible_facts': {'distribution': 'Archlinux', 'effective_user_id': uid, 'user_id': username}}
                result = subprocess.run([ANSIBLE, '-i', 'localhost,', '-c', 'local',
                    str(BASE / 'zoom.yml'), '--tags', 'identity-test-only', '-e', json.dumps(overrides)],
                    env=dict(os.environ, ANSIBLE_LOCAL_TEMP=directory, ANSIBLE_NOCOLOR='1'),
                    capture_output=True, text=True)
                output = result.stdout + result.stderr
                self.assertEqual(result.returncode, expected, output)
                self.assertIn('Require installed Arch and root access', output)
                self.assertNotIn('TASK [Register Zoom virtual channel', output)
                self.assertNotIn('TASK [Link the native Zoom', output)
