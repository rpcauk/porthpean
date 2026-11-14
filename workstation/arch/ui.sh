# Shared non-secret dialogs for the installed-system bootstrap.
ui_cancel() { echo 'Cancelled.'; exit 0; }
ui_input() {
  whiptail --backtitle 'Porthpean workstation' --title "$1" --output-fd 3 \
    --inputbox "$2" 10 72 "$3" 3>&1 1>&2
}
ui_yesno() {
  whiptail --backtitle 'Porthpean workstation' --title "$1" --defaultno \
    --yesno "$2" 12 76
}
