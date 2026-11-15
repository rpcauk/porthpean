"""Exercise local recipe orchestration without building or installing host packages."""
import pathlib
import subprocess
import tempfile
import unittest

BASE = pathlib.Path(__file__).resolve().parents[1]

class LocalPackages(unittest.TestCase):
    def test_detached_recipe_edits_survive_build_and_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = pathlib.Path(temporary)
            recipe = directory / 'PKGBUILD'
            recipe.write_text('reviewed original\n')
            def git(*args):
                return subprocess.check_output(['git', '-C', temporary, *args], stderr=subprocess.DEVNULL)
            git('init')
            git('add', 'PKGBUILD')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture')
            git('checkout', '--detach')
            recipe.write_text('reviewed with local source fix\n')
            before = git('status', '--porcelain')
            tools = directory / 'tools'
            tools.mkdir()
            makepkg = tools / 'makepkg'
            makepkg.write_text('''#!/usr/bin/env bash
[[ $(cat PKGBUILD) == 'reviewed with local source fix' ]] || exit 91
case "$1" in
  --cleanbuild) touch "$PWD/example.pkg.tar.zst" ;;
  --packagelist) printf '%s\\n' "$PWD/example.pkg.tar.zst" ;;
  *) exit 92 ;;
esac
''')
            makepkg.chmod(0o755)
            script = r'''source "$1/aur.sh"
set -euo pipefail
directory=$2
export PATH="$directory/tools:$PATH"
# Execute the real working-directory wrapper, replacing only identity/tools.
aur_as_user() { "$@"; }
aur_enable_install() { echo grant; }
aur_yay() { printf '%s\n' "$@"; }
aur_install_local "$directory"
'''
            result = subprocess.run(['bash', '-c', script, 'test', str(BASE), temporary], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(recipe.read_text(), 'reviewed with local source fix\n')
            self.assertTrue(git('status', '--porcelain').startswith(before))
            self.assertEqual(result.stdout.splitlines(), ['grant', '-U', '--needed', '--noconfirm', str(directory / 'example.pkg.tar.zst')])

    def test_failed_build_never_requests_installation(self):
        script = '''source "$1/aur.sh"
aur_as_user() { return 47; }
aur_enable_install() { echo unexpected; }
aur_yay() { echo unexpected; }
aur_install_local /unused
'''
        result = subprocess.run(['bash', '-c', script, 'test', str(BASE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 47)
        self.assertEqual(result.stdout, '')
