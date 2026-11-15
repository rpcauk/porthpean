# Explicit recovery for earlier installations

This directory is separate from normal provisioning. Fresh installs and future updates must not call these scripts. The base installer creates system/package state with umask 022; normal convergence manages only named directories and declared configuration. Pacman owns its database metadata.

`early-installer-layout` is for affected machines created by the early installer versions. Run it once, as root on the installed Arch system, from a reviewed checkout:

```bash
bash workstation/arch/recovery/early-installer-layout
bash workstation/arch/bootstrap
```

It applies the normal directory policy, then repairs public installed-package metadata and public repository database file modes. It leaves locks, private downloads, symlink targets and unrelated state alone. It also moves the exact earlier unmanaged Fast Syntax Highlighting checkout into a private backup so its AUR package can own that location. A different unmanaged checkout stops for review rather than being moved.

This recovery does not rebuild the pacman database, remove locks, delete previous accounts or change disks/boot files. Rerunning it after completion makes no further metadata changes or highlighting backups. It is not a general database-corruption repair. If ordinary package queries still fail afterward, investigate the actual error separately.
