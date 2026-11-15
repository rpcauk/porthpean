#!/usr/bin/env python3
"""Narrow fixes for the reviewed icaclient recipe; never execute its shell code."""
from pathlib import Path
import sys

LATEST = 'https://www.citrix.com/downloads/workspace-app/linux/workspace-app-for-linux-latest.html'
ARCHIVE = 'https://www.citrix.com/downloads/workspace-app/legacy-workspace-app-for-linux/workspace-app-for-linux-2604-10.html'
REMOTE = 'source_x86_64=("$pkgname-x64-$pkgver.tar.gz::$_source64")'
LOCAL = 'source_x86_64=("$pkgname-x64-$pkgver.tar.gz")'


def transform(text, local=False):
    if 'pkgver=26.04.10.1\n' not in text or text.count(REMOTE) != 1:
        raise ValueError('Unexpected Citrix recipe: review it before changing source handling')
    if text.count("url='" + LATEST + "'") != 1:
        raise ValueError('Unexpected Citrix download page')
    text = text.replace("url='" + LATEST + "'", "url='" + ARCHIVE + "'")
    if local:
        start = text.index('_dl_urls_=')
        end = text.index("source=('citrix-configmgr.desktop'", start)
        text = text[:start] + text[end:]
        text = text.replace(REMOTE, LOCAL)
        text = text.replace('source_aarch64=("$pkgname-arm64-$pkgver.tar.gz::$_sourceaarch64")', 'source_aarch64=()')
    else:
        # curl must retain the HTTP error in the installer log and fail the recipe.
        old = '_dl_urls_="$(curl -sL "$url" | grep -F ".tar.gz?__gda__")"'
        new = '_citrix_page="$(curl -fLsS "$url")" || return 1\n_dl_urls_="$(printf \'%s\\n\' "$_citrix_page" | grep -F ".tar.gz?__gda__")"'
        if text.count(old) != 1:
            raise ValueError('Unexpected Citrix page parser')
        text = text.replace(old, new)
        old = 'source_x86_64=("$pkgname-x64-$pkgver.tar.gz::$_source64")'
        text = text.replace(old, '[[ $_source64 == https://* ]] || { printf \'Citrix archive page contains no matching x86_64 tarball for 26.04.10.1.\\n\' >&2; return 1; }\n' + old)
    return text


if __name__ == '__main__':
    # Read the untouched, pinned recipe each time, including for the local fallback.
    original, destination = map(Path, sys.argv[1:3])
    destination.write_text(transform(original.read_text(), local='--local' in sys.argv[3:]))
