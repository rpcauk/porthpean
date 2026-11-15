# Arch workstation bootstrap

Read [the base installation guide](../../docs/arch-usb-install.md) first. The manual install sets the `root` password without creating a separate admin user. The old Mac dotfiles bootstrap must not run on Arch.

Distribution: `https://github.com/rpcauk/porthpean`; maintainer Git remote: `git@github.com:rpcauk/porthpean.git`. [The public entry point](../../INSTALL.md) downloads a reviewable checkout rather than requiring a GitHub key.

From a reviewed root-owned checkout, as root:

```sh
bash bootstrap
```

Whiptail dialogs select the daily username (`ryan` by default) and optional `codex`/`amp` accounts. Hidden whiptail password boxes collect and confirm the daily password, which goes to chpasswd through stdin; existing passwords are retained unless changed explicitly. Mismatched or rejected passwords retry in place; Cancel exits. Passwords stay briefly in non-exported shell memory and are unset after use. No password/hash enters Ansible variables, command arguments or saved configuration. Tracing is disabled; shell memory wiping cannot be guaranteed. The script performs an approved complete upgrade, then applies `site.yml` with `profiles/t480s.yml`.

The reusable core handles accounts and convergence. The current profile specifies GB keyboard defaults. Packages and desktop choices remain deliberately opinionated. No disk identities, credentials, homelab hostnames or secrets belong in a public profile.

Ansible manages files/services with backups. Agent passwords are locked and supplementary groups removed; homes are private. Unselected existing agents are not deleted. `/etc/porthpean-workstation.json` records non-secret choices for `check`. Re-running can upgrade packages, so do so only in an approved maintenance window.

`install-agent` is a separate unprivileged helper for reviewing/running each vendor installer. No agent daemon, SSH server, remote-control API, sudo rule, linger or unattended task is enabled. Vendor login is interactive under the corresponding account.

Remaining machine-specific work: Secure Boot trust/signing automation, verified Restic destination/credentials/retention, Kanata keymap/device restrictions, remote access if wanted. This bootstrap does not claim those are completed.

Validation performed on the Mac: shell parsing, Ansible syntax and local configuration rendering. No target-machine execution has been done.

During setup, whiptail shows the current stage and elapsed time. Package downloads/installation use real pacman percentages; installation identifies the package and transaction position. Commands run behind the dialog, with a private output log and an error-log viewer on failure. Password input is never included in that log.

## Installer permission repairs and audit

Both base installation and the desktop bootstrap enforce a shared, non-recursive policy for known system directories. This repairs early installations whose `/etc` or pacman cache parents were mode 0700. `/`, `/etc`, `/home`, `/var`, cache parents, `/var/log` and `/srv` use 0755; `/var/tmp` uses 1777; `/root`, snapshots and workstation state remain 0700. Private user homes and download child directories are never recursively changed. Unexpected owners and symlinks stop the repair. Pacman's actual `alpm` account must be able to traverse its cache before provisioning continues; downloading as root or disabling the sandbox is not a workaround.

The standalone base installer embeds the same permissions policy, checked for equality in tests. Progress commands disable systemd/Git/general pagers so a hidden pager cannot stall setup. The `check` script now fails on unexpected home/system modes, unavailable D-Bus/NetworkManager or inaccessible pacman cache.

Validation covers temporary-directory permission repair/idempotence, preservation of private children, symlink rejection, simulated firmware/menu setup, progress subprocesses, password handling and disk guards, plus shell and Ansible syntax. It does not emulate Arch package transactions, firmware, the graphical session or Secure Boot. Run the workstation `check` as root after provisioning, then test both boot choices and desktop login on hardware. Vendor-agent installation/authentication, backup destination/restore, Kanata and Secure Boot enrollment remain explicit follow-up work.

Desktop provisioning performs one approved complete system upgrade, then installs setup tools and each requested desktop package in separate transactions (`--needed` skips installed packages). Dependencies are still resolved by pacman. Ansible runs separately for accounts, desktop files, service configuration, validation, service enablement, and completion recording. A failed stage stops before later stages; rerunning converges existing configuration and packages. No disk formatting occurs here.

The progress display contains short stage/package labels, elapsed time and real percentages rather than raw CLI output. Detailed output remains in the private error log. All progress subprocesses use `C.UTF-8`, including Ansible; the bootstrap checks UTF-8 before provisioning. This fixes the earlier runner's forced `LC_ALL=C`.

Package-by-package installation now uses one persistent gauge across the package list, retains the real console TERM instead of forcing xterm, and limits progress redraws. Kernel upgrades that remove the running kernel's module tree cause a reboot checkpoint before continuing. Provisioning explicitly loads `nf_tables` before firewall validation and still refuses to enable the firewall if validation fails.
