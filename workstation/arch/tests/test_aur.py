import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
VISUDO = shutil.which('visudo') or '/usr/sbin/visudo'


@unittest.skipUnless(Path(VISUDO).is_file(), 'visudo needed')
class SudoTests(unittest.TestCase):
    def test_permanent_rule_syntax(self):
        with tempfile.NamedTemporaryFile('w') as stream:
            stream.write((BASE / 'files/daily-sudoers.j2').read_text().replace('{{ daily_user }}', 'ryan'))
            stream.flush()
            result = subprocess.run([VISUDO, '-cf', stream.name], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_temporary_rule_removed_after_success_failure_and_interrupt(self):
        for ending in ('exit 0', 'exit 47', 'kill -TERM $$'):
            with self.subTest(ending=ending), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                script = '''source "$1/aur.sh"
set -euo pipefail
daily=ryan
aur_sudo_file="$2/grant"
# Validate the generated file with real visudo; do not inspect/change host policy.
visudo() { if [[ $# -gt 1 ]]; then "$TEST_VISUDO" "$@"; else return 0; fi; }
trap aur_cleanup EXIT
trap 'exit 143' TERM
umask 022
aur_enable_install
[[ -s $aur_sudo_file ]]
python3 -c 'import pathlib,sys; print(oct(pathlib.Path(sys.argv[1]).stat().st_mode & 0o777))' "$aur_sudo_file" > "$2/mode"
cat "$aur_sudo_file" > "$2/captured"
'''+ending
                result = subprocess.run(['bash', '-c', script, 'test', str(BASE), directory],
                                        env=dict(os.environ, TEST_VISUDO=VISUDO), capture_output=True, text=True)
                self.assertEqual(result.returncode, {'exit 0': 0, 'exit 47': 47, 'kill -TERM $$': 143}[ending], result.stderr)
                self.assertFalse((root / 'grant').exists())
                self.assertEqual((root / 'mode').read_text().strip(), '0o440')
                text = (root / 'captured').read_text()
                self.assertIn('ryan ALL=(root) NOPASSWD: /usr/bin/pacman', text)
                self.assertNotIn('NOPASSWD: ALL', text)


    def test_build_environment_drops_root_cache_variables_and_changes_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            script = '''source "$1/aur.sh"
daily=ryan
aur_home=$2
# Emulate only the identity switch; execute the actual env/cwd wrapper.
runuser() { [[ $1 == -u && $2 == ryan && $3 == -- ]] || return 1; shift 3; "$@"; }
aur_as_user /bin/sh -c 'pwd; env'
'''
            result = subprocess.check_output(['bash', '-c', script, 'test', str(BASE), directory],
                                             env=dict(os.environ, GOCACHE='/root/cache', SECRET_TEST='must-not-inherit'), text=True)
            lines = result.splitlines()
            self.assertEqual(Path(lines[0]).resolve(), Path(directory).resolve())
            environment = dict(line.split('=', 1) for line in lines[1:] if '=' in line)
            self.assertEqual(environment['HOME'], directory)
            self.assertEqual(environment['USER'], 'ryan')
            self.assertEqual(environment['LC_ALL'], 'C.UTF-8')
            self.assertNotIn('GOCACHE', environment)
            self.assertNotIn('SECRET_TEST', environment)
