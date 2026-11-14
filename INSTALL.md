# Porthpean workstation setup

Opinionated Arch Linux workstation configuration for a ThinkPad T480s, with a small reusable core. This public repository distributes the installer until a dedicated website exists. The Porthpean application and workstation infrastructure remain separate.

Start with [USB preparation and encrypted base installation](docs/arch-usb-install.md). That base stage creates only a password-protected `admin` account. [`arch-install.sh`](arch-install.sh) can guide the live-USB installation; use its `--continue` mode if the stage-5 filesystems are already mounted. Fresh mode erases the explicitly confirmed Linux disk. Run `arch-install.sh` only from the Arch live USB. Run the desktop bootstrap below only from the installed base. Neither is intended for an existing server.

From the public `main` branch, from the installed base as `admin`:

```sh
INSTALLER=$(mktemp)
curl --fail --show-error --location --proto '=https' --tlsv1.2 \
  https://raw.githubusercontent.com/rpcauk/porthpean/main/install.sh \
  -o "$INSTALLER"
less "$INSTALLER"
sudo bash "$INSTALLER"
```

Review the downloaded repository/revision too before accepting `REVIEWED`. No `curl | sudo bash`; `main` is mutable, not a signed release.

The bootstrap prompts for a daily username (default `ryan`), a hidden daily-account password, and whether to create separate locked-password `codex` and `amp` accounts. The daily and agent accounts have no sudo. Vendor CLI installation and authentication remain separate interactive steps.

## Scope

- Reusable: account prompts, package/file convergence, isolated optional agent accounts, checks and explicit confirmation.
- Opinionated: Arch/systemd, Niri desktop, official package list, separate administrator, manual upgrades and private-network access.
- Personal profile: GB keyboard defaults for `t480s`; chosen hostname and disk design in the manual guide.
- Local only: disk identity, passwords, provider credentials, backup destination/keys and signing keys. Never commit these.

Do not build a distro-independent installer or plugin system before there is another actual machine/use case. Profiles hold defaults; they are not secrets or permission grants. The post-boot desktop bootstrap never chooses or formats a disk. The separate live-USB installer formats only in explicitly selected fresh mode after disk/serial confirmation.

[Bootstrap details and remaining setup](workstation/arch/README.md).

Validation: shell/Ansible syntax, local rendering and mocked installer safety-guard tests only. A hardware install has not been run. Secure Boot enrollment, Restic destination/restore testing and Kanata configuration require machine-specific follow-up.
