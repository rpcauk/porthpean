import configparser
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('appearance', BASE / 'appearance.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Appearance(unittest.TestCase):
    def test_kernel_edits_preserve_encryption_and_are_idempotent(self):
        initial='rd.luks.name=1234=cryptroot root=/dev/mapper/cryptroot rootflags=subvol=@ rw quiet splash loglevel=4\n'
        changed=module.cmdline(initial)
        self.assertEqual(module.cmdline(changed), changed)
        for option in ['rd.luks.name=1234=cryptroot', 'root=/dev/mapper/cryptroot', 'rootflags=subvol=@', 'rw']:
            self.assertIn(option, changed.split())
        self.assertEqual(changed.split().count('splash'), 1)

    def test_plymouth_hook_precedes_decryption_and_preserves_other_hooks(self):
        initial='HOOKS=(base systemd autodetect keyboard sd-vconsole block sd-encrypt filesystems fsck)\n'
        changed=module.hooks(initial)
        self.assertEqual(module.hooks(changed), changed)
        self.assertLess(changed.index('systemd'), changed.index('plymouth'))
        self.assertLess(changed.index('plymouth'), changed.index('sd-encrypt'))
        self.assertIn('sd-vconsole', changed)
        with self.assertRaises(ValueError): module.hooks('HOOKS=(base encrypt)\n')

    def test_refind_preserves_windows_volume_default_and_timeout(self):
        initial='timeout 5\ndefault_selection "Arch Linux LTS"\ntextonly\nmenuentry "Windows" {\n    volume abc-123\n    loader /EFI/Microsoft/Boot/bootmgfw.efi\n}\nmenuentry "Arch Linux LTS" {\n    loader /EFI/Linux/arch-lts.efi\n}\n'
        changed=module.refind(initial)
        self.assertEqual(module.refind(changed), changed)
        for text in ['volume abc-123','default_selection "Arch Linux LTS"','timeout 5','arch-lts-recovery.efi','windows.png']:
            self.assertIn(text, changed)
        self.assertNotIn('textonly', changed)

    def test_structured_desktop_configs_parse(self):
        files=BASE/'files'
        bar=json.loads((files/'waybar.jsonc').read_text())
        self.assertEqual(bar['position'], 'bottom')
        self.assertEqual(bar['modules-left'], ['niri/workspaces'])
        self.assertNotIn('format-icons', (files/'waybar.jsonc').read_text())
        for name in ['fuzzel.ini','foot.ini','gtk-settings.ini']:
            config=configparser.ConfigParser(interpolation=None)
            config.read(files/name)
        self.assertIn('width = 100%', (files/'tofi.conf').read_text())
        self.assertIn('margin-bottom = 30', (files/'tofi.conf').read_text())
        self.assertTrue(bar['niri/workspaces']['hide-empty'])
        self.assertEqual(bar['battery']['format-charging'], 'B:{capacity}% ↑')

    def test_assets_are_deterministic_and_wallpaper_is_jpeg(self):
        assets=list((BASE/'files/boot').glob('*.png'))
        before={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in assets}
        subprocess.run(['python3', str(BASE/'files/boot/build-assets.py')],check=True)
        self.assertEqual(before,{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in assets})
        self.assertTrue((BASE/'files/wallpapers/diogenes.jpg').read_bytes().startswith(b'\xff\xd8'))

class AppearanceConvergence(unittest.TestCase):
    def test_first_apply_second_noop_and_menu_only_change(self):
        import os
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            target = pathlib.Path(directory) / 'target'
            binary = pathlib.Path(directory) / 'bin'
            binary.mkdir()
            for name in ['etc/kernel', 'etc/plymouth', 'efi/EFI/refind', 'efi/EFI/Linux', 'root']:
                (target / name).mkdir(parents=True)
            (target / 'etc/kernel/cmdline').write_text('rd.luks.name=1234=cryptroot root=/dev/mapper/cryptroot rw\n')
            (target / 'etc/mkinitcpio.conf').write_text('HOOKS=(base systemd block sd-encrypt filesystems)\n')
            (target / 'etc/plymouth/plymouthd.conf').write_text('[Daemon]\nTheme=old\n')
            (target / 'efi/EFI/refind/refind.conf').write_text('timeout 5\ntextonly\nmenuentry "Arch Linux LTS" {\n    loader /EFI/Linux/arch-lts.efi\n}\n')
            for name in ['arch-lts', 'arch-linux']:
                (target / f'efi/EFI/Linux/{name}.efi').write_bytes(b'original image')
            (binary / 'mountpoint').write_text('#!/bin/sh\nexit 0\n')
            (binary / 'plymouth-set-default-theme').write_text('#!/bin/sh\nprintf "[Daemon]\\nTheme=porthpean\\n" > "$TEST_ROOT/etc/plymouth/plymouthd.conf"\n')
            (binary / 'mkinitcpio').write_text('#!/bin/sh\necho rebuilt >> "$TEST_ROOT/rebuilds"\nfor name in arch-lts arch-linux; do echo "rebuilt image" > "$TEST_ROOT/efi/EFI/Linux/$name.efi"; done\n')
            for path in binary.iterdir():
                path.chmod(0o700)
            program = (BASE / 'setup-appearance').read_text()
            program = program.replace('[[ $EUID == 0 && -f /etc/arch-release && ! -d /run/archiso ]] || exit 1', 'true # identity guard excluded ONLY in this temporary-filesystem simulation')
            program = program.replace('base=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)', 'base="$TEST_BASE"')
            for prefix in ['/sys/firmware', '/usr/share', '/efi', '/etc', '/root']:
                program = program.replace(prefix, str(target) + prefix)
            for mode in ['state', 'kernel', 'menu']:
                program = program.replace(f'"$base/appearance.py" {mode}', f'"$base/appearance.py" {mode} --root "$TEST_ROOT"')
            env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'], TEST_ROOT=str(target), TEST_BASE=str(BASE))
            def apply():
                result = subprocess.run(['bash', '-c', program], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result
            def snapshot():
                return {str(p): (p.stat().st_mtime_ns, p.stat().st_ctime_ns, p.read_bytes() if p.is_file() else None) for p in [target, *target.rglob('*')]}
            apply()
            self.assertEqual((target / 'rebuilds').read_text().splitlines(), ['rebuilt'])
            self.assertEqual(len(list((target / 'root').iterdir())), 1)
            for name in ['arch-lts', 'arch-linux']:
                self.assertEqual((target / f'efi/EFI/Linux/{name}-recovery.efi').read_bytes(), b'original image')
            before = snapshot()
            self.assertIn('no changes', apply().stdout)
            self.assertEqual(before, snapshot())
            # A changed boot-menu asset needs no kernel rebuild or recovery replacement.
            (target / 'efi/EFI/refind/themes/porthpean/theme.conf').write_text('changed locally\n')
            recovery = (target / 'efi/EFI/Linux/arch-lts-recovery.efi').stat().st_mtime_ns
            apply()
            self.assertEqual((target / 'rebuilds').read_text().splitlines(), ['rebuilt'])
            self.assertEqual(recovery, (target / 'efi/EFI/Linux/arch-lts-recovery.efi').stat().st_mtime_ns)
            self.assertEqual(len(list((target / 'root').iterdir())), 2)
            before = snapshot()
            apply()
            self.assertEqual(before, snapshot())
