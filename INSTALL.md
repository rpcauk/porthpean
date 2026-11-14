# Porthpean workstation setup

Opinionated Arch Linux workstation configuration for a ThinkPad T480s, with a small reusable core. This public repository distributes the installer until a dedicated website exists. The Porthpean application and workstation infrastructure remain separate.

Start with [USB preparation and encrypted base installation](docs/arch-usb-install.md). That base stage creates only the password-protected `root` account. [`arch-install.sh`](arch-install.sh) guides a fresh live-USB installation. It always erases the explicitly confirmed Linux disk, including a partial installation; no resume modes. It can safely unmount its known partial-install tree and close its target encryption mapping before formatting, and stops if they are busy or unrelated. Run `arch-install.sh` only from the Arch live USB. Run the desktop bootstrap below only from the installed base. Neither is intended for an existing server.

From the public `main` branch, from the installed base as `root`:

```sh
INSTALLER=$(mktemp)
curl --fail --show-error --location --proto '=https' --tlsv1.2 \
  https://raw.githubusercontent.com/rpcauk/porthpean/main/install.sh \
  -o "$INSTALLER"
less "$INSTALLER"
bash "$INSTALLER"
```

Review the installer and repository in advance; the entry script prints the checkout revision. Do not pipe downloads directly into a shell; `main` is mutable, not a signed release.

Whiptail dialogs ask for a daily username (default `ryan`) and optional dedicated `codex`/`amp` accounts. Hidden whiptail boxes collect and confirm all installer passwords; secrets go to system tools through stdin, not command arguments or files. The daily and agent accounts have no sudo. Vendor CLI installation and authentication remain separate interactive steps.

## Scope

- Reusable: account prompts, package/file convergence, isolated optional agent accounts, checks and explicit confirmation.
- Opinionated: Arch/systemd, Niri desktop, official package list, root for administration, manual upgrades and private-network access.
- Personal profile: GB keyboard defaults for `t480s`; chosen hostname and disk design in the manual guide.
- Local only: disk identity, passwords, provider credentials, backup destination/keys and signing keys. Never commit these.

Do not build a distro-independent installer or plugin system before there is another actual machine/use case. Profiles hold defaults; they are not secrets or permission grants. The post-boot desktop bootstrap never chooses or formats a disk. The separate live-USB installer always performs a fresh installation after the selected-disk erase confirmation.

[Bootstrap details and remaining setup](workstation/arch/README.md).

Validation: shell/Ansible syntax, local rendering and mocked installer safety-guard tests only. A hardware install has not been run. Secure Boot enrollment, Restic destination/restore testing and Kanata configuration require machine-specific follow-up.

During setup, whiptail shows the current stage and elapsed time. Package downloads/installation use real pacman percentages; installation identifies the package and transaction position. Commands run behind the dialog, with a private output log and an error-log viewer on failure. Password input is never included in that log.

The base installer installs a five-second rEFInd menu: Arch Linux LTS is always the default, with the regular kernel and detected Windows installation selectable. Windows EFI partitions are inspected read-only. Firmware registration runs outside the chroot and must match the new Linux ESP and lead BootOrder before completion. systemd-boot remains available as a recovery loader. Secure Boot remains a separate signing/enrollment step covering rEFInd and both UKIs. An existing failed boot should be repaired in place: **do not rerun the fresh installer**, which erases the selected disk.
