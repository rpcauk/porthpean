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
        metadata = root / 'var/lib/pacman/local/example-1.0-1'
        metadata.mkdir(mode=0o700)
        (metadata / 'desc').write_text('public package metadata')
        (metadata / 'desc').chmod(0o600)
        (root / 'var/lib/pacman/sync/download-private').mkdir(mode=0o700)
        (root / 'var/lib/pacman/sync/download-private/core.db.part').write_text('private partial')
        (root / 'var/lib/pacman/sync/download-private/core.db.part').chmod(0o600)
        (root / 'var/lib/pacman/sync/core.db').write_text('public repo database')
        (root / 'var/lib/pacman/sync/core.db').chmod(0o600)
        (root / 'var/lib/pacman/db.lck').write_text('private lock')
        (root / 'var/lib/pacman/db.lck').chmod(0o600)
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
ensure_system_permissions "$2"
'''
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', body, 'test', str(HELPER), str(root)], text=True, capture_output=True)

    def test_converges_declared_directories_without_touching_package_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            for path in ['etc', 'var/cache', 'var/cache/pacman/pkg', 'var/lib', 'var/lib/pacman', 'var/lib/pacman/local', 'var/lib/pacman/sync']:
                (root / path).chmod(0o700)
            for _ in range(2):
                result = self.run_helper(root)
                self.assertEqual(result.returncode, 0, result.stderr)
            for path, mode in [('etc', 0o755), ('var/cache/pacman/pkg', 0o755), ('var/tmp', 0o1777), ('root', 0o700), ('var/cache/pacman/pkg/download-test', 0o700), ('root/secret', 0o600), ('var/lib', 0o755), ('var/lib/pacman/local/example-1.0-1', 0o700), ('var/lib/pacman/local/example-1.0-1/desc', 0o600), ('var/lib/pacman/db.lck', 0o600), ('var/lib/pacman/sync/core.db', 0o600), ('var/lib/pacman/sync/download-private', 0o700), ('var/lib/pacman/sync/download-private/core.db.part', 0o600)]:
                self.assertEqual((root / path).stat().st_mode & 0o7777, mode, path)

    def test_second_normal_run_does_not_mutate_files_or_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            result = self.run_helper(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = lambda: {str(p): (p.stat().st_mode, p.stat().st_mtime_ns, p.stat().st_ctime_ns) for p in [root, *root.rglob('*')]}
            before = snapshot()
            result = self.run_helper(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, snapshot())

    def test_explicit_legacy_recovery_is_separate_and_repeat_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            command = ['bash', '-e', '-c', 'source "$1"; recover_legacy_pacman_metadata "$2"',
                       'recovery', str(BASE / 'recovery/pacman-metadata.sh'), str(root)]
            subprocess.run(command, check=True)
            metadata = root / 'var/lib/pacman/local/example-1.0-1/desc'
            self.assertEqual(metadata.stat().st_mode & 0o7777, 0o644)
            before = metadata.stat().st_ctime_ns
            subprocess.run(command, check=True)
            self.assertEqual(before, metadata.stat().st_ctime_ns)
            self.assertEqual((root / 'var/lib/pacman/db.lck').stat().st_mode & 0o7777, 0o600)
            self.assertEqual((root / 'var/lib/pacman/sync/download-private').stat().st_mode & 0o7777, 0o700)

    def test_refuses_symlink_in_managed_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            (root / 'etc').rmdir()
            (root / 'etc').symlink_to(root / 'home')
            result = self.run_helper(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Expected real system directory', result.stderr)

    def test_database_symlinks_do_not_expose_private_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            self.fixture(root)
            (root / 'var/lib/pacman/sync/private-link').symlink_to(root / 'root/secret')
            result = self.run_helper(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((root / 'root/secret').stat().st_mode & 0o7777, 0o600)

    def test_standalone_installer_embeds_same_permissions_policy(self):
        self.assertIn(HELPER.read_text(), (BASE.parents[1] / 'arch-install.sh').read_text())
