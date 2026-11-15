import importlib.util
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('citrix_source', BASE / 'citrix-source.py')
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
RECIPE = '''pkgver=26.04.10.1
url='https://www.citrix.com/downloads/workspace-app/linux/workspace-app-for-linux-latest.html'
_dl_urls_="$(curl -sL "$url" | grep -F ".tar.gz?__gda__")"
_dl_urls="$(echo "$_dl_urls_" | grep -F "$pkgver.tar.gz?__gda__")"
_source64=https:"$(echo "$_dl_urls" | sed -En 's|^.*rel="(//.*/linuxx64-[^"]*)".*$|\\1|p')"
_sourceaarch64=https:
source=('citrix-configmgr.desktop')
source_x86_64=("$pkgname-x64-$pkgver.tar.gz::$_source64")
source_aarch64=("$pkgname-arm64-$pkgver.tar.gz::$_sourceaarch64")
sha256sums_x86_64=('unchanged-checksum')
'''


class CitrixSourceTests(unittest.TestCase):
    def run_recipe(self, recipe, curl):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'PKGBUILD').write_text(recipe)
            (root / 'curl').write_text('#!/bin/sh\n' + curl)
            (root / 'curl').chmod(0o700)
            env = dict(os.environ, PATH=str(root) + ':' + os.environ['PATH'])
            return subprocess.run(['bash', '-c', 'pkgname=icaclient; source "$1" && printf "%s\\n" "$url" "${source_x86_64[@]}"', 'test', str(root / 'PKGBUILD')], capture_output=True, text=True, env=env)

    def test_version_page_retains_signed_link_and_checksum(self):
        recipe = source.transform(RECIPE)
        result = self.run_recipe(recipe, '''printf '%s\\n' '<a rel="//downloads.citrix.com/123/linuxx64-gcc-8-26.04.10.1.tar.gz?__gda__=signed">Download</a>'
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(source.ARCHIVE, result.stdout)
        self.assertIn('https://downloads.citrix.com/123/linuxx64-gcc-8-26.04.10.1.tar.gz?__gda__=signed', result.stdout)
        self.assertIn("sha256sums_x86_64=('unchanged-checksum')", recipe)

    def test_http_error_is_reported_and_stops_recipe(self):
        result = self.run_recipe(source.transform(RECIPE), 'echo "curl: (22) HTTP 403" >&2; exit 22\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('HTTP 403', result.stderr)
        self.assertEqual(result.stdout, '')

    def test_missing_pinned_download_is_explicit(self):
        result = self.run_recipe(source.transform(RECIPE), 'echo "different version"\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no matching x86_64 tarball', result.stderr)

    def test_local_fallback_never_fetches_page(self):
        result = self.run_recipe(source.transform(RECIPE, local=True), 'echo "MUST NOT RUN" >&2; exit 1\n')
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('MUST NOT RUN', result.stderr)
        self.assertIn('icaclient-x64-26.04.10.1.tar.gz', result.stdout)
        self.assertNotIn('::https', result.stdout)

    def test_unexpected_revision_rejected(self):
        with self.assertRaises(ValueError):
            source.transform(RECIPE.replace('pkgver=26.04.10.1', 'pkgver=26.08'))
