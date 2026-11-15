import configparser
import hashlib
import importlib.util
import json
import pathlib
import subprocess
import tomllib
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
        tomllib.loads((files/'regreet.toml').read_text())

    def test_assets_are_deterministic_and_wallpaper_is_jpeg(self):
        assets=list((BASE/'files/boot').glob('*.png'))
        before={path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in assets}
        subprocess.run(['python3', str(BASE/'files/boot/build-assets.py')],check=True)
        self.assertEqual(before,{path.name:hashlib.sha256(path.read_bytes()).hexdigest() for path in assets})
        self.assertTrue((BASE/'files/wallpapers/diogenes.jpg').read_bytes().startswith(b'\xff\xd8'))
