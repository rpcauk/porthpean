# Known workstation directory modes only; never recurse into data or pacman downloads.
repair_system_permissions() {
  local root=${1%/} path mode
  while read -r mode path; do
    [[ -d $root$path && ! -L $root$path ]] || { echo "Expected real system directory: $root$path" >&2; return 1; }
    [[ $(stat -c %u "$root$path") == 0 ]] || { echo "Unexpected owner: $root$path" >&2; return 1; }
    chmod "$mode" "$root$path" || return 1
    [[ $(stat -c %a "$root$path") == "${mode#0}" ]] || return 1
  done <<'MODES'
0755 /
0755 /etc
0755 /home
0755 /var
0755 /var/cache
0755 /var/cache/pacman
0755 /var/cache/pacman/pkg
0755 /var/log
0755 /srv
1777 /var/tmp
0700 /root
0700 /.snapshots
0700 /srv/workstation-state
MODES
}
