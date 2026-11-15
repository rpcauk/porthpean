"""Read-only/fake-command tests: never call actual partition or filesystem tools."""
import pathlib
import subprocess
import shlex
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[3] / 'arch-install.sh'


def shell(body):
    return subprocess.run(['bash', '-c', 'source "$1"\n' + body, 'test', str(SCRIPT)], text=True, capture_output=True)


class DiskGuards(unittest.TestCase):
    def test_package_installation_uses_service_accessible_umask(self):
        # Reproduce the inherited-mask failure without installing any packages.
        script = SCRIPT.read_text()
        start = script.index('umask 022', script.index('format_and_unlock "$crypt"'))
        packages = script.index('run_progress "Installing the Arch base"', start)
        reset = script.index('umask 077', packages)
        self.assertNotIn('umask 077', script[start:packages])
        self.assertLess(packages, reset)
        self.assertIn('ensure_system_permissions /mnt', script[reset:])
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run(['bash', '-c', 'umask 077; umask 022; mkdir "$1/etc"', 'test', root], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((pathlib.Path(root) / 'etc').stat().st_mode & 0o777, 0o755)


    def test_sourcing_runs_no_installation(self):
        result = shell('echo definitions-only')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'definitions-only')

    def test_accepts_whole_disk_paths_with_fake_probes_only(self):
        for value in ['/dev/sda', '/dev/nvme0n1', '/dev/disk/by-id/example']:
            fixture = '''is_block_device() { return 0; }
            readlink() { printf '%s\\n' "${@: -1}"; }
            lsblk() { echo disk; }
            '''
            result = shell(fixture + 'whole_disk ' + shlex.quote(value))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), value)

    def test_rejects_partitions_even_when_they_are_block_devices(self):
        for value in ['/dev/sda1', '/dev/nvme0n1p2', '/dev/disk/by-id/example-part1']:
            fixture = '''is_block_device() { return 0; }
            readlink() { printf '%s\\n' "${@: -1}"; }
            lsblk() { echo part; }
            '''
            result = shell(fixture + 'whole_disk ' + shlex.quote(value))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('whole disk, not a partition', result.stderr)

    def test_rejects_non_device_paths(self):
        for value in ['', '/etc/passwd', 'sda']:
            result = shell('whole_disk ' + shlex.quote(value))
            self.assertNotEqual(result.returncode, 0)

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

    def test_cancelled_erase_dialog_stops_confirmation(self):
        result = shell('''lsblk() { echo '1T Test SSD'; }
        whiptail() { return 1; }
        confirm_erase /dev/fake''')
        self.assertNotEqual(result.returncode, 0)

    def test_erase_dialog_defaults_to_cancel_and_names_target(self):
        result = shell('''lsblk() { echo '1T Test SSD'; }
        whiptail() { printf '%s\\n' "$@"; }
        confirm_erase /dev/fake''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--defaultno', result.stdout)
        self.assertIn('/dev/fake', result.stdout)
        self.assertIn('All partitions and data', result.stdout)

    def test_disk_menu_filters_partitions_and_unusable_disks(self):
        result = shell('''lsblk() {
          case "$*" in
            *PATH,TYPE,RO,RM*) printf '/dev/sda disk 0 0\\n/dev/sda1 part 0 0\\n/dev/sdb disk 0 1\\n/dev/sdc disk 1 0\\n' ;;
            *) echo '1T Test SSD' ;;
          esac
        }
        whiptail() { printf '%s\\n' "$@" >&3; }
        select_disk''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('/dev/sda', result.stdout)
        for path in ['/dev/sda1', '/dev/sdb', '/dev/sdc']:
            self.assertNotIn(path, result.stdout)

    def test_input_dialog_routes_value_without_prompt_text(self):
        result = shell('''whiptail() { printf 'chosen-host' >&3; }
        value=$(ui_input Hostname Prompt t480s)
        printf '%s' "$value"''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'chosen-host')

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
