"""Exercise boot menu generation with fake device, mount and firmware commands."""
import pathlib
import subprocess
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[3] / 'arch-install.sh'
GUID = '11111111-2222-3333-4444-555555555555'

class BootMenu(unittest.TestCase):
    def run_fixture(self, active=True, first=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for directory in ['usr/share/refind', 'efi/EFI/BOOT']:
                (root / directory).mkdir(parents=True)
            (root / 'usr/share/refind/refind_x64.efi').write_bytes(b'fake-efi')
            record = f'Boot00AB{"*" if active else " "} Arch Linux HD(1,GPT,{GUID},0,0)/File(\\EFI\\refind\\refind_x64.efi)'
            body = '''source "$1"
blkid() { echo 11111111-2222-3333-4444-555555555555; }
lsblk() { echo '/dev/fake2 c12a7328-f81f-11d2-ba4b-00a0c93ec93b'; }
mktemp() { command mktemp -d "$fixture_root/probe.XXXXXXXX"; }
mount() { [[ $* == '-o ro,nosuid,nodev,noexec '* ]] || return 90; mkdir -p "${@: -1}/EFI/Microsoft/Boot"; touch "${@: -1}/EFI/Microsoft/Boot/bootmgfw.efi"; }
umount() { rm -r "$1/EFI"; }
efibootmgr() { if [[ $1 == -v ]]; then printf '%s\\n' "$3" "$4"; fi; }
# Preserve fixture arguments for the mock firmware output.
firmware_records() { :; }
'''
            # Capture records in globals rather than positional parameters of the mock.
            body = body.replace('"$3" "$4"', '"$record" "$order"')
            body += 'fixture_root=$2; record=$3; order=$4\nconfigure_boot_menu /dev/fake /dev/fake1 "$2"\n'
            result = subprocess.run(['bash', '-euo', 'pipefail', '-c', body, 'test', str(SCRIPT), tmp, record, 'BootOrder: ' + ('00AB,0000' if first else '0000,00AB')], text=True, capture_output=True)
            config = root / 'efi/EFI/refind/refind.conf'
            return result, config.read_text() if config.exists() else ''

    def test_windows_and_arch_menu_and_firmware_verification(self):
        result, config = self.run_fixture()
        self.assertEqual(result.returncode, 0, result.stderr)
        for text in ['timeout 5', 'default_selection "Arch Linux LTS"', 'menuentry "Windows"', '/EFI/Linux/arch-lts.efi', '/EFI/Microsoft/Boot/bootmgfw.efi']:
            self.assertIn(text, config)

    def test_boot_listing_cannot_open_interactive_pager(self):
        script = SCRIPT.read_text()
        self.assertIn("bootctl --no-pager --esp-path=/efi list", script)
        self.assertNotIn("bootctl --esp-path=/efi list", script)

    def test_inactive_entry_blocks_completion(self):
        result, _ = self.run_fixture(active=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('No active firmware entry', result.stderr)

    def test_wrong_boot_order_blocks_completion(self):
        result, _ = self.run_fixture(first=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not first', result.stderr)
