set +x
set +v
set +a
# Plain terminal prompts. Prompts use stderr; answers alone use stdout.
ui_cancel() { echo 'Cancelled.'; exit 0; }
ui_read() {
  local prompt=$1 hidden=${2:-false} answer
  export -n answer
  printf '%b' "$prompt" >&2
  if [[ $hidden == true ]]; then
    IFS= read -r -s answer </dev/tty || return 1
    printf '\n' >&2
  else
    IFS= read -r answer </dev/tty || return 1
  fi
  printf '%s' "$answer"
}
ui_input() {
  local answer
  answer=$(ui_read "$1: $2 [$3] ") || return 1
  printf '%s' "${answer:-$3}"
}
ui_yesno() {
  local answer
  answer=$(ui_read "\n$1\n$2\nContinue? [y/N] ") || return 1
  [[ $answer == y || $answer == Y || $answer == yes ]]
}
ui_password() {
  local title=$1 first second
  export -n first second
  while true; do
    first=$(ui_read "$title — enter password: " true) || return 1
    if [[ -z $first || $first == *$'\n'* || $first == *$'\r'* ]]; then
      unset first
      printf 'Enter a non-empty, single-line password.\n' >&2
      continue
    fi
    second=$(ui_read 'Repeat password: ' true) || { unset first; return 1; }
    if [[ $first == "$second" ]]; then
      printf '%s' "$first"
      unset first second
      return 0
    fi
    unset first second
    printf 'Passwords did not match. Try again.\n' >&2
  done
}

ui_set_account_password() {
  local account=$1 secret
  export -n secret
  while true; do
    if ! secret=$(ui_password "$account account password"); then return 1; fi
    if printf '%s:%s\n' "$account" "$secret" | chpasswd; then
      unset secret
      return 0
    fi
    unset secret
    printf 'The password was not accepted. Try another password.\n' >&2
  done
}

run_progress() {
  local stage=$1
  shift
  printf '\n== %s ==\n' "$stage"
  if [[ -n ${install_log:-} ]]; then
    # pipefail preserves the command's failure; tee keeps the terminal readable
    # while retaining the complete output in a private log.
    (set -o pipefail; "$@" 2>&1 | tee -a "$install_log")
  else
    "$@"
  fi
}
