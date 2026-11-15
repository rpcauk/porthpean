#!/usr/bin/env python3
"""Idempotent edits to this installer's known boot configuration, preserving disk IDs."""
import argparse
import configparser
import pathlib
import re


def cmdline(text):
    words = [word for word in text.split() if word not in ('quiet', 'splash') and not word.startswith(('loglevel=', 'systemd.show_status=', 'rd.systemd.show_status='))]
    if not any(word.startswith('rd.luks.name=') for word in words):
        raise ValueError('Expected encrypted-root kernel command line')
    return ' '.join(words + ['quiet', 'splash', 'loglevel=3', 'systemd.show_status=auto', 'rd.systemd.show_status=auto']) + '\n'


def hooks(text):
    match = re.search(r'^HOOKS=\(([^\n]*)\)', text, re.M)
    if not match:
        raise ValueError('No single-line HOOKS configuration found')
    values = match[1].split()
    if 'systemd' not in values or 'sd-encrypt' not in values:
        raise ValueError('Expected systemd/sd-encrypt hooks')
    values = [value for value in values if value != 'plymouth']
    values.insert(values.index('sd-encrypt'), 'plymouth')
    return text[:match.start()] + 'HOOKS=(' + ' '.join(values) + ')' + text[match.end():]


def refind(text):
    text = re.sub(r'^\s*textonly[^\n]*\n', '', text, flags=re.M)
    text = re.sub(r'^include themes/porthpean/theme.conf\n', '', text, flags=re.M)
    text = re.sub(r'^    icon /EFI/refind/themes/porthpean/[^\n]*\n', '', text, flags=re.M)
    if 'Arch LTS recovery' not in text:
        text += '\nmenuentry "Arch LTS recovery" {\n    loader /EFI/Linux/arch-lts-recovery.efi\n}\n'
    for loader, icon in [('arch-lts.efi', 'arch-lts.png'), ('arch-linux.efi', 'arch.png'), ('bootmgfw.efi', 'windows.png'), ('arch-lts-recovery.efi', 'arch-lts.png')]:
        pattern = r'(\s+loader [^\n]*' + re.escape(loader) + r'\n)'
        text = re.sub(pattern, lambda match: match[1] + '    icon /EFI/refind/themes/porthpean/' + icon + '\n', text)
    return 'include themes/porthpean/theme.conf\n' + text


def changes_needed(root, files):
    """Compare managed inputs directly; no completion markers or historical versions."""
    def same(source, target):
        return target.is_file() and source.read_bytes() == target.read_bytes()
    cmd = root / 'etc/kernel/cmdline'
    hooks_file = root / 'etc/mkinitcpio.conf'
    menu = root / 'efi/EFI/refind/refind.conf'
    kernel_changed = cmd.read_text() != cmdline(cmd.read_text()) or hooks_file.read_text() != hooks(hooks_file.read_text())
    selection = configparser.ConfigParser()
    selection.read(root / 'etc/plymouth/plymouthd.conf')
    kernel_changed |= selection.get('Daemon', 'Theme', fallback='') != 'porthpean'
    kernel_changed |= any(not same(source, root / 'usr/share/plymouth/themes/porthpean' / source.name) for source in (files / 'plymouth').iterdir())
    menu_changed = menu.read_text() != refind(menu.read_text())
    assets = list((files / 'boot').glob('*.png')) + [files / 'boot/theme.conf']
    for directory in ('refind', 'BOOT'):
        menu_changed |= any(not same(source, root / f'efi/EFI/{directory}/themes/porthpean' / source.name) for source in assets)
    menu_changed |= not same(menu, root / 'efi/EFI/BOOT/refind.conf')
    for name in ('arch-lts', 'arch-linux'):
        recovery = root / f'efi/EFI/Linux/{name}-recovery.efi'
        menu_changed |= not recovery.is_file() or recovery.stat().st_size == 0
    return bool(kernel_changed), bool(menu_changed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['kernel', 'menu', 'state'])
    parser.add_argument('--root', default='/')
    args = parser.parse_args()
    root = pathlib.Path(args.root)
    if args.mode == 'state':
        print(' '.join(str(value).lower() for value in changes_needed(root, pathlib.Path(__file__).parent / 'files')))
        return 0
    if args.mode == 'kernel':
        cmd = root / 'etc/kernel/cmdline'
        config = root / 'etc/mkinitcpio.conf'
        # Validate both before writing either.
        new_cmd, new_hooks = cmdline(cmd.read_text()), hooks(config.read_text())
        outputs = [(cmd, new_cmd), (config, new_hooks)]
    else:
        config = root / 'efi/EFI/refind/refind.conf'
        outputs = [(config, refind(config.read_text()))]

    changed = [(path, content) for path, content in outputs if path.read_text() != content]
    for path, content in changed:
        path.write_text(content)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
