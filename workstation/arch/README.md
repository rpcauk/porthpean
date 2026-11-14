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
