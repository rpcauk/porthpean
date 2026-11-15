# Explicit recovery only: early installs created private package metadata.
recover_legacy_pacman_metadata() {
  # Package metadata is public. Do not touch cache downloads, db.lck or other state.
  python3 - "${1:-/}" <<'PACMAN_METADATA'
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
        if stat.S_IMODE(info.st_mode) != 0o755:
            path.chmod(0o755)
    elif stat.S_ISREG(info.st_mode):
        if stat.S_IMODE(info.st_mode) != 0o644:
            path.chmod(0o644)
    else:
        raise SystemExit(f'Unexpected file type in pacman database: {path}')
PACMAN_METADATA
}
