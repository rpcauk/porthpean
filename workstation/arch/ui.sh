set +x
set +v
set +a
# Shared dialogs for the installed-system bootstrap.
ui_cancel() { echo 'Cancelled.'; exit 0; }
ui_input() {
  whiptail --backtitle 'Porthpean workstation' --title "$1" --output-fd 3 \
    --inputbox "$2" 10 72 "$3" 3>&1 1>&2
}
ui_yesno() {
  whiptail --backtitle 'Porthpean workstation' --title "$1" --defaultno \
    --yesno "$2" 12 76
}

# Return a confirmed secret on stdout only; dialog rendering stays on the terminal.
# Callers must keep xtrace/verbose/allexport disabled and unset the result promptly.
ui_password() {
  local title=$1 first second
  export -n first second
  while true; do
    if ! first=$(whiptail --title "$title" --output-fd 3 \
      --passwordbox 'Enter password:' 10 72 3>&1 1>&2); then return 1; fi
    if [[ -z $first || $first == *$'\n'* || $first == *$'\r'* ]]; then
      unset first
      whiptail --title "$title" --msgbox 'Enter a non-empty, single-line password.' 9 72 >&2 || true
      continue
    fi
    if ! second=$(whiptail --title "$title" --output-fd 3 \
      --passwordbox 'Repeat password:' 10 72 3>&1 1>&2); then unset first; return 1; fi
    if [[ $first == "$second" ]]; then
      printf '%s' "$first"
      unset first second
      return 0
    fi
    unset first second
    whiptail --title "$title" --msgbox 'Passwords did not match. Try again.' 9 72 >&2 || true
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
    whiptail --title 'Account password' --msgbox 'The password was not accepted. Try another password.' 10 72 >&2 || true
  done
}

run_progress() {
  local stage=$1
  shift
  if [[ -n ${progress_helper:-} ]]; then
    python3 "$progress_helper" --stage "$stage" --log "$install_log" -- "$@" 2>> "$install_log"
  else
    "$@"
  fi
}
