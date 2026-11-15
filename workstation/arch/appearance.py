#!/usr/bin/env python3
"""Idempotent edits to this installer's known boot configuration, preserving disk IDs."""
import argparse
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['kernel', 'menu'])
    parser.add_argument('--root', default='/')
    args = parser.parse_args()
    root = pathlib.Path(args.root)
    if args.mode == 'kernel':
        cmd = root / 'etc/kernel/cmdline'
        config = root / 'etc/mkinitcpio.conf'
        # Validate both before writing either.
        new_cmd, new_hooks = cmdline(cmd.read_text()), hooks(config.read_text())
        cmd.write_text(new_cmd)
        config.write_text(new_hooks)
    else:
        config = root / 'efi/EFI/refind/refind.conf'
        config.write_text(refind(config.read_text()))

if __name__ == '__main__':
    main()
