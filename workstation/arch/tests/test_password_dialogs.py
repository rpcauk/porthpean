"""Synthetic secrets and fake tools only; never change disks or real passwords."""
import pathlib
import shlex
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
LIVE = ROOT / 'arch-install.sh'
UI = ROOT / 'workstation/arch/ui.sh'
SECRET = '  fake:$value\\backslash`tick"quoted  '


def shell(path, body):
    # Adapt synthetic dialog responses to the terminal reader for shared secret tests.
    adapter = """
ui_read() { whiptail --passwordbox 3>&1; }
""" if path == UI else ''
    return subprocess.run(['bash', '-c', 'source "$1"\n' + adapter + body, 'test', str(path)], text=True, capture_output=True)


class PasswordDialogs(unittest.TestCase):
    def test_secret_roundtrip_and_no_secret_in_dialog_arguments(self):
        for path in (LIVE, UI):
            result = shell(path, 'expected=' + shlex.quote(SECRET) + '''
            whiptail() {
              [[ $* != *"$expected"* ]] || return 91
              printf '%s' "$expected" >&3
            }
            actual=$(ui_password 'Test account')
            [[ $actual == "$expected" ]] || exit 92
            echo OK
            ''')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'OK')
            self.assertNotIn(SECRET, result.stderr)

    def test_preexisting_export_flags_do_not_expose_collected_passwords(self):
        for path in (LIVE, UI):
            result = shell(path, 'expected=' + shlex.quote(SECRET) + '''
            export first=old second=old secret=old
            whiptail() {
              [[ $(env) != *"$expected"* ]] || return 91
              printf '%s' "$expected" >&3
            }
            value=$(ui_password Test)
            [[ $value == "$expected" ]]
            ui_password() { printf '%s' "$expected"; }
            arch-chroot() { [[ $(env) != *"$expected"* ]] || return 92; cat >/dev/null; }
            chpasswd() { [[ $(env) != *"$expected"* ]] || return 92; cat >/dev/null; }
            ''' + ('set_target_password root' if path == LIVE else 'ui_set_account_password root'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(SECRET, result.stdout + result.stderr)

    def test_cancel_returns_without_a_secret(self):
        for path in (LIVE, UI):
            result = shell(path, '''whiptail() { return 1; }
            if value=$(ui_password Test); then exit 90; fi
            [[ -z $value ]]
            ''')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')

    def test_mismatch_and_empty_password_retry(self):
        for path in (LIVE, UI):
            with tempfile.TemporaryDirectory() as directory:
                counter = pathlib.Path(directory) / 'counter'
                counter.write_text('0')
                result = shell(path, 'counter=' + shlex.quote(str(counter)) + '''
                whiptail() {
                  if [[ $* == *--passwordbox* ]]; then
                    n=$(cat "$counter"); n=$((n+1)); printf '%s' "$n" > "$counter"
                    case "$n" in 1) printf '' >&3 ;; 2) printf first >&3 ;;
                      3) printf mismatch >&3 ;; 4|5) printf accepted >&3 ;; *) return 99 ;; esac
                  else
                    return 1  # Dismissing a mismatch notice must still retry.
                  fi
                }
                actual=$(ui_password Test)
                [[ $actual == accepted && $(cat "$counter") == 5 ]]
                ''')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')

    def test_luks_receives_exact_bytes_through_stdin_and_secret_is_unset(self):
        result = shell(LIVE, 'expected=' + shlex.quote(SECRET) + '''
        drive_pass=$expected
        cryptsetup() {
          [[ $* != *"$expected"* && $* == *'--key-file -'* ]] || return 91
          actual=$(cat)
          [[ $actual == "$expected" ]] || return 92
          echo "$1"
        }
        format_and_unlock /dev/fake
        [[ ! ${drive_pass+x} ]]
        ''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['luksFormat', 'open'])
        self.assertNotIn(SECRET, result.stdout + result.stderr)

    def test_failed_luks_operation_also_unsets_secret(self):
        result = shell(LIVE, '''drive_pass=synthetic
        cryptsetup() { cat >/dev/null; return 1; }
        if format_and_unlock /dev/fake; then exit 90; fi
        [[ ! ${drive_pass+x} ]]
        ''')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejected_account_password_retries_even_when_notice_dismissed(self):
        for path, command in ((LIVE, 'set_target_password'), (UI, 'ui_set_account_password')):
            with tempfile.TemporaryDirectory() as directory:
                counter = pathlib.Path(directory) / 'attempts'
                counter.write_text('0')
                result = shell(path, 'counter=' + shlex.quote(str(counter)) + '''
                ui_password() { printf synthetic; }
                whiptail() { return 1; }
                accept_on_second_try() {
                  cat >/dev/null
                  n=$(cat "$counter"); n=$((n+1)); printf '%s' "$n" > "$counter"
                  [[ $n == 2 ]]
                }
                arch-chroot() { accept_on_second_try; }
                chpasswd() { accept_on_second_try; }
                ''' + command + ' root\n[[ $(cat "$counter") == 2 ]]')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '')

    def test_rejected_drive_unlock_retries_without_reformatting(self):
        with tempfile.TemporaryDirectory() as directory:
            attempts = pathlib.Path(directory) / 'attempts'
            operations = pathlib.Path(directory) / 'operations'
            attempts.write_text('0')
            result = shell(LIVE, 'attempts=' + shlex.quote(str(attempts)) + '\noperations=' + shlex.quote(str(operations)) + '''
            drive_pass=synthetic
            ui_password() { printf synthetic-retry; }
            whiptail() { return 1; }
            cryptsetup() {
              cat >/dev/null
              printf '%s\\n' "$1" >> "$operations"
              if [[ $1 == open ]]; then
                n=$(cat "$attempts"); n=$((n+1)); printf '%s' "$n" > "$attempts"
                [[ $n -gt 1 ]] || return 2
              fi
            }
            format_and_unlock /dev/fake
            [[ ! ${drive_pass+x} ]]
            ''')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(operations.read_text().splitlines(), ['luksFormat', 'open', 'open'])

    def test_account_password_piped_to_target_without_secret_arguments(self):
        for path, command in ((LIVE, 'set_target_password'), (UI, 'ui_set_account_password')):
            result = shell(path, 'expected=' + shlex.quote(SECRET) + '''
            ui_password() { printf '%s' "$expected"; }
            check_input() {
              [[ $* != *"$expected"* ]] || return 91
              IFS= read -r line
              [[ $line == "root:$expected" ]] || return 92
              echo OK
            }
            arch-chroot() { [[ $* == '/mnt chpasswd' ]] || return 93; check_input "$@"; }
            chpasswd() { check_input "$@"; }
            ''' + command + ' root')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'OK')
            self.assertNotIn(SECRET, result.stderr)


if __name__ == '__main__':
    unittest.main()
