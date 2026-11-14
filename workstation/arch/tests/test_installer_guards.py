"""Read-only/fake-command tests: never call actual partition or filesystem tools."""
import pathlib
import subprocess
import shlex
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

    def cleanup_fixture(self, mounts, extra=''):
        # Canonical fake devices; every real host probe/mutation is overridden.
        return '''readlink() { printf '%s\\n' "${@: -1}"; }
        lsblk() {
          case "$*" in
            *MOUNTPOINTS*) echo '' ;;
            *PATH,TYPE*) printf '/dev/linux disk\\n/dev/linux1 part\\n/dev/linux2 part\\n' ;;
            *PATH*) printf '/dev/linux\\n/dev/linux1\\n/dev/linux2\\n' ;;
            *RO*|*RM*) echo 0 ;;
          esac
        }
        cryptroot_open() { return 1; }
        mountpoint() { return 0; }
        findmnt() {
          if [[ $* == '-rn -o SOURCE,TARGET' ]]; then printf '%s\\n' MOUNT_RECORDS; else echo mount-plan; fi
        }
        '''.replace('MOUNT_RECORDS', shlex.quote(mounts)) + extra

    def test_accepts_selected_partial_mounts(self):
        result = shell(self.cleanup_fixture('/dev/linux2[/@] /mnt\n/dev/linux1 /mnt/efi') + '\nplan_partial_cleanup /dev/linux')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Partial installation mounts', result.stdout)

    def test_refuses_other_disk_mounted_under_mnt(self):
        result = shell(self.cleanup_fixture('/dev/linux2[/@] /mnt\n/dev/windows1 /mnt/efi') + '\nplan_partial_cleanup /dev/linux')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not on the selected Linux disk', result.stderr)

    def test_refuses_selected_disk_used_outside_install_tree(self):
        result = shell(self.cleanup_fixture('/dev/linux2 /run/archiso/bootmnt') + '\nplan_partial_cleanup /dev/linux')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Target is in use', result.stderr)

    def test_refuses_active_chroot_mount(self):
        result = shell(self.cleanup_fixture('/dev/linux2 /mnt\ndev /mnt/dev') + '\nplan_partial_cleanup /dev/linux')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Target is in use', result.stderr)

    def test_refuses_cryptroot_on_another_disk(self):
        extra = '''cryptroot_open() { return 0; }
        cryptsetup() { printf 'device: /dev/windows2\\n'; }
        '''
        result = shell(self.cleanup_fixture('/dev/linux2 /mnt', extra) + '\nplan_partial_cleanup /dev/linux')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('belongs to another disk', result.stderr)

    def test_busy_unmount_stops_before_closing_mapping(self):
        extra = '''umount() { echo BUSY >&2; return 1; }
        cryptroot_open() { return 0; }
        cryptsetup() { if [[ $1 == status ]]; then echo 'device: /dev/linux2'; else echo SHOULD-NOT-CLOSE; fi; }
        '''
        result = shell(self.cleanup_fixture('/dev/linux2 /mnt', extra) + '\nclear_partial_install /dev/linux')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Target is busy', result.stderr)
        self.assertNotIn('SHOULD-NOT-CLOSE', result.stdout)

    def test_successful_cleanup_runs_unmount_then_unused_check(self):
        extra = '''umount() { echo "UNMOUNT $*"; }
        cryptroot_open() { return 0; }
        cryptsetup() { if [[ $1 == status ]]; then echo 'device: /dev/linux2'; else echo "CLOSE $*"; fi; }
        unused_disk() { echo "CHECK-UNUSED $*"; }
        '''
        result = shell(self.cleanup_fixture('/dev/linux2 /mnt', extra) + '\nclear_partial_install /dev/linux')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('UNMOUNT -R /mnt', result.stdout)
        self.assertGreater(result.stdout.index('CLOSE close cryptroot'), result.stdout.index('UNMOUNT'))
        self.assertGreater(result.stdout.index('CHECK-UNUSED'), result.stdout.index('CLOSE close cryptroot'))


if __name__ == '__main__':
    unittest.main()
