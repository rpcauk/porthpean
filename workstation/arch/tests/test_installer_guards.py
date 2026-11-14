"""Read-only/fake-command tests: never call actual partition or filesystem tools."""
import pathlib
import subprocess
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[3] / 'arch-install.sh'


def shell(body):
    return subprocess.run(['bash', '-c', 'source "$1"\n' + body, 'test', str(SCRIPT)], text=True, capture_output=True)


class DiskGuards(unittest.TestCase):
    def test_sourcing_runs_no_installation(self):
        result = shell('echo definitions-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'definitions-only')

    def test_requires_stable_whole_disk_identifier(self):
        for value in ['/dev/nvme0n1', '/dev/sda', '/dev/disk/by-id/nvme-example-part1', '']:
            result = shell(f'whole_disk {value!r}')
            self.assertNotEqual(result.returncode, 0, value)

    def test_rejects_nonexistent_disk(self):
        result = shell('whole_disk /dev/disk/by-id/porthpean-does-not-exist')
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_mounted_descendant_or_swap(self):
        for mounted in ['/mnt', '/run/archiso/bootmnt', '[SWAP]']:
            result = shell('lsblk() { printf "%s\\n" ' + repr(mounted) + '; }; unused_disk /dev/fake')
            self.assertNotEqual(result.returncode, 0, mounted)
            self.assertIn('mounted/active swap', result.stderr)

    def test_rejects_active_mapping(self):
        result = shell('''lsblk() {
          case "$*" in *MOUNTPOINTS*) echo '' ;; *TYPE*) printf 'disk\npart\ncrypt\n' ;; esac
        }; unused_disk /dev/fake''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('active mapped', result.stderr)

    def test_rejects_readonly_or_removable(self):
        for readonly, removable in [(1, 0), (0, 1)]:
            result = shell('''lsblk() {
              case "$*" in *MOUNTPOINTS*) echo '' ;; *TYPE*) echo disk ;;
              *RO*) echo %s ;; *RM*) echo %s ;; esac
            }; unused_disk /dev/fake''' % (readonly, removable))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('read-only or removable', result.stderr)

    def test_accepts_unused_fixed_disk_with_fake_probes_only(self):
        result = shell('''lsblk() {
          case "$*" in *MOUNTPOINTS*) echo '' ;; *TYPE*) printf 'disk\npart\n' ;;
          *RO*|*RM*) echo 0 ;; esac
        }; unused_disk /dev/fake''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_confirmation_required(self):
        result = shell('confirm "ERASE expected-serial" <<< "ERASE other-serial"')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Confirmation did not match', result.stderr)

    def test_rejects_efi_partition_on_another_disk(self):
        result = shell('''lsblk() {
          case "$*" in *TYPE*) echo part ;; *PKNAME*root*) echo nvme0n1 ;;
          *PKNAME*efi*) echo nvme1n1 ;; esac
        }; same_install_disk /dev/root /dev/efi''')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('different disks', result.stderr)

    def test_accepts_same_disk_efi_with_fake_probes_only(self):
        result = shell('''lsblk() {
          case "$*" in *TYPE*) echo part ;; *PKNAME*) echo nvme0n1 ;; esac
        }; same_install_disk /dev/root /dev/efi''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'nvme0n1')

    def test_continue_validation_section_has_no_formatting_calls(self):
        # Guard structural separation in addition to runtime disk rejection tests.
        text = SCRIPT.read_text()
        section = text.split('# Shared strict validation.', 1)[1]
        for command in ['sfdisk ', 'mkfs.', 'luksFormat', 'cryptsetup open']:
            self.assertNotIn(command, section)


if __name__ == '__main__':
    unittest.main()
