# Known directory modes; only public pacman database metadata is repaired recursively.
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
0755 /var/lib
0755 /var/lib/pacman
0755 /var/lib/pacman/local
0755 /var/lib/pacman/sync
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
  # Package metadata is public. Do not touch cache downloads, db.lck or other state.
  python3 - "$root" <<'PACMAN_METADATA'
import os
from pathlib import Path
import stat
import pwd
import sys

root = Path(sys.argv[1] or '/')
owner = root.stat().st_uid
local = root / 'var/lib/pacman/local'
paths = []
for directory, subdirs, files in os.walk(local, followlinks=False):
    paths += [(Path(directory) / name, {owner}) for name in subdirs + files]
sync_owners = {owner}
try:
    sync_owners.add(pwd.getpwnam('alpm').pw_uid)
except KeyError:
    pass
# Sync downloads use private download-* staging directories: never descend into them.
for path in (root / 'var/lib/pacman/sync').iterdir():
    if path.name.endswith(('.db', '.db.sig', '.files', '.files.sig')):
        paths.append((path, sync_owners))
for path, owners in paths:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode):
        continue
    if info.st_uid not in owners:
        raise SystemExit(f'Unexpected owner in pacman database: {path}')
    if stat.S_ISDIR(info.st_mode):
        path.chmod(0o755)
    elif stat.S_ISREG(info.st_mode):
        path.chmod(0o644)
    else:
        raise SystemExit(f'Unexpected file type in pacman database: {path}')
PACMAN_METADATA
}
