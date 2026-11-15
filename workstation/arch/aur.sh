# Root orchestration; all AUR code and yay itself run as the daily user.
aur_init() {
  [[ $EUID == 0 && -f /etc/arch-release ]] || { echo 'AUR setup requires root on Arch.' >&2; return 1; }
  daily=${PORTHPEAN_DAILY_USER:-}
  if [[ -z $daily && -r /etc/porthpean-workstation.json ]]; then
    daily=$(python3 -c 'import json; print(json.load(open("/etc/porthpean-workstation.json"))["daily_user"])')
  fi
  [[ $daily =~ ^[a-z][a-z0-9_-]*$ && $daily != root && $daily != codex && $daily != amp ]] || return 1
  [[ $(id -u "$daily") -ge 1000 && $(getent passwd "$daily" | cut -d: -f6) == "/home/$daily" ]] || return 1
  aur_home=/home/$daily
  # Serialize the temporary sudo grant and remove a stale grant on rerun.
  exec 9>/run/lock/porthpean-aur.lock
  flock -n 9 || { echo 'Another Porthpean AUR stage is running.' >&2; return 1; }
  aur_sudo_file=/etc/sudoers.d/zz-porthpean-install
  rm -f -- "$aur_sudo_file"
  trap aur_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM HUP
  install -d -m 0700 -o "$daily" -g "$(id -gn "$daily")" "$aur_home/.cache" "$aur_home/.cache/porthpean-build"
}
aur_as_user() {
  runuser -u "$daily" -- env -i HOME="$aur_home" USER="$daily" LOGNAME="$daily" SHELL=/bin/zsh TERM="${TERM:-linux}" XDG_CONFIG_HOME="$aur_home/.config" \
    XDG_CACHE_HOME="$aur_home/.cache" XDG_STATE_HOME="$aur_home/.local/state" \
    PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    bash -c 'cd -- "$1"; shift; exec "$@"' aur "$aur_home" "$@"
}
aur_new_build() {
  aur_as_user mktemp -d "$aur_home/.cache/porthpean-build/$1.XXXXXXXX"
}
aur_enable_install() {
  local temporary
  temporary=$(mktemp "$(dirname -- "$aur_sudo_file")/.porthpean.XXXXXXXX")
  printf 'Defaults:%s verifypw=never\n%s ALL=(root) NOPASSWD: /usr/bin/pacman\n' "$daily" "$daily" > "$temporary"
  chmod 0440 "$temporary"
  if ! visudo -cf "$temporary"; then rm -f -- "$temporary"; return 1; fi
  mv -f -- "$temporary" "$aur_sudo_file"
  visudo -c
}
aur_yay() {
  aur_as_user /usr/bin/yay --sudo /usr/bin/sudo --sudoflags=-n --sudoloop=false "$@"
}
# yay -B resets/merges local Git worktrees, including reviewed recipe edits.
# Build the exact local recipe with makepkg, then let yay install the artifacts.
aur_install_local() {
  local directory=$1 package_lines package
  local -a packages=()
  aur_as_user bash -c 'cd -- "$1"; exec makepkg --cleanbuild --noconfirm' build "$directory" || return
  package_lines=$(aur_as_user bash -c 'cd -- "$1"; exec makepkg --packagelist' list "$directory") || return
  [[ -n $package_lines ]] || { echo 'makepkg returned no package paths.' >&2; return 1; }
  while IFS= read -r package; do packages+=("$package"); done <<< "$package_lines"
  for package in "${packages[@]}"; do
    [[ -f $package && $package == /* ]] || { echo "Missing built package: $package" >&2; return 1; }
  done
  aur_enable_install || return
  aur_yay -U --needed --noconfirm "${packages[@]}"
}
aur_cleanup() {
  rm -f -- "$aur_sudo_file"
}
