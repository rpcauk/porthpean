import pathlib
import subprocess
import tempfile
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
HELPER = BASE / 'permissions.sh'

class Permissions(unittest.TestCase):
    def fixture(self, root):
        for line in HELPER.read_text().split("<<'MODES'\n")[1].split('\nMODES')[0].splitlines():
            _, path = line.split()
            (root / path.lstrip('/')).mkdir(parents=True, exist_ok=True)
        (root / 'var/cache/pacman/pkg/download-test').mkdir(mode=0o700)
        (root / 'root/secret').write_text('fixture')
        (root / 'root/secret').chmod(0o600)

    def run_helper(self, root):
        # Portable stat adapter; no real system directories or privileged operations.
        body = '''source "$1"
stat() {
  if [[ $2 == %u ]]; then echo 0; else
    python3 -c 'import os,sys; print(oct(os.stat(sys.argv[1]).st_mode & 0o7777)[2:])' "$3"
  fi
}
repair_system_permissions "$2"
'''
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', body, 'test', str(HELPER), str(root)], text=True, capture_output=True)

    def test_repairs_directories_without_touching_private_children(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            for path in ['etc', 'var/cache', 'var/cache/pacman/pkg']:
                (root / path).chmod(0o700)
            for _ in range(2):
                result = self.run_helper(root)
                self.assertEqual(result.returncode, 0, result.stderr)
            for path, mode in [('etc', 0o755), ('var/cache/pacman/pkg', 0o755), ('var/tmp', 0o1777), ('root', 0o700), ('var/cache/pacman/pkg/download-test', 0o700), ('root/secret', 0o600)]:
                self.assertEqual((root / path).stat().st_mode & 0o7777, mode, path)

    def test_refuses_symlink_in_managed_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            (root / 'etc').rmdir()
            (root / 'etc').symlink_to(root / 'home')
            result = self.run_helper(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Expected real system directory', result.stderr)

    def test_standalone_installer_embeds_same_permissions_policy(self):
        self.assertIn(HELPER.read_text(), (BASE.parents[1] / 'arch-install.sh').read_text())
