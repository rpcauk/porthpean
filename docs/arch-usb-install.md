# T480s: USB → encrypted Arch base → workstation bootstrap

Chosen values: **daily user `ryan`, hostname `t480s`, admin user `admin`, agent users `codex` and `amp`**. Linux SSD: **1 TB**. Windows: separate **512 GB WWAN SSD, preserve completely**. This replaces the VM-first rollout: install directly on the ThinkPad, using explicit checkpoints. These are instructions to execute yourself; no installation has been executed or hardware-tested here.

Read this on another device while installing. Execute one block at a time and stop on any unexpected output. Do not paste the entire document into a shell. The only values you must discover are USB identity, Linux SSD identity, Wi-Fi interface/SSID if needed, and private passwords. Disk IDs and passwords cannot safely be supplied in advance.

## Guided installer alternative

The public [`arch-install.sh`](https://github.com/rpcauk/porthpean/blob/main/arch-install.sh) automates the live-USB steps through the bootable console base. Boot/connect the Arch USB first, then download and inspect it:

```sh
curl --fail --show-error --location --proto '=https' --tlsv1.2 \
  https://raw.githubusercontent.com/rpcauk/porthpean/main/arch-install.sh \
  -o /root/arch-install.sh
less /root/arch-install.sh
```

Run the single fresh-install flow:

```sh
bash /root/arch-install.sh
```

Run this at the live USB prompt, outside `arch-chroot`, after any current pacstrap has finished. It **always starts from scratch and erases the selected Linux disk**, including any partial installation. There are no resume/continue modes.

It asks for the protected Windows disk (or physical disconnection), target Linux disk by stable identity, hostname, and an exact `ERASE <serial>` confirmation. Before confirmation it shows any partial-install mounts/mapping that must be closed. After confirmation it unmounts only the selected disk's known `/mnt` installation tree, closes `cryptroot` only if its backing partition is on that disk, checks the disk is unused, and then repartitions/formats it.

It refuses a different disk mounted under `/mnt`, unexpected mounts/mappings, active swap, removable/read-only targets or a target used outside the installation tree. If a process keeps the mount busy, it stops without forced/lazy unmounting or killing processes. Exit chroots and finish/stop the current installer yourself, or reboot back into the USB and reconnect, then rerun. Windows is protected by your correct identity selection, not by a guessed device number or capacity.

The script fixes this profile to a 2 GiB Linux ESP, LUKS2/Btrfs subvolumes, UK English/London, two kernels, systemd-boot and unsigned UKIs ready for later signing. It delegates hidden encryption/account prompts to cryptsetup/passwd, creates only admin and emergency root credentials, and leaves reboot/unmount to you. It does not save passwords or set Secure Boot keys. Keep the existing Secure Boot setting disabled until the signing/enrollment follow-up is complete.

After the console base boots, use the separate `install.sh` entry point in section 8 for the daily user/password, desktop and optional AI accounts. No need to repeat the manual commands below when their guided equivalents completed successfully.

Validation is limited to shell parsing and mocked safety-guard tests; no actual disk install has been executed here. The manual steps below remain the reference for inspecting or diagnosing the generated setup.

## 1. What you need

- T480s on AC, backup computer, reliable internet (Ethernet preferred), USB stick of at least 4 GB which can be erased.
- Backups of anything on the 1 TB SSD: this procedure erases it entirely.
- Verified Windows backup and BitLocker recovery key if encryption is enabled. Firmware/Secure Boot changes can trigger recovery. Confirm Windows boots before starting.
- Photograph current firmware boot/security settings. Know how to restore factory Secure Boot keys. Do not clear TPM or delete keys during installation.
- A second ordinary USB stick for this guide/bootstrap and later recovery files is convenient. Writing the Arch ISO makes its filesystem unsuitable for ordinary drag-and-drop storage.
- Ideally remove/disconnect the Windows SSD using the Lenovo service procedure and internal-battery precautions. If it stays installed, identify it independently and never mount or select it in the commands below. If unsure which drive is which, stop.

Final initial layout: Linux disk GPT; 2 GiB ESP; remaining space LUKS2/Btrfs; no on-disk swap. Bootstrap adds up to 4 GiB zram. Hibernation is off. The ESP is unencrypted; user and system data are encrypted. Secure Boot remains temporarily disabled for initial installation, then gets a separately reviewed enrollment step. UKIs are used from the first boot, so later signing does not require redesigning the disk.

## 2. Make the installer USB on the Mac

Open the [official Arch download page](https://archlinux.org/download/) and download the current x86_64 ISO and its PGP signature. At preparation time it lists `archlinux-2026.11.01-x86_64.iso`; use the exact current filename if it changes.

In a Mac terminal, set the path to the ISO you actually downloaded:

```sh
cd ~/Downloads
ISO=archlinux-2026.11.01-x86_64.iso
shasum -a 256 "$ISO"
```

Compare **all** checksum characters with the official HTTPS download page. Also verify its signature using GnuPG (install with `brew install gnupg` if needed). The following signer is the one listed by the official download page at preparation time; recheck there if it changes:

```sh
gpg --auto-key-locate clear,wkd -v --locate-external-key pierre@archlinux.org
gpg --verify "$ISO.sig" "$ISO"
```

Require a good signature from the release signer whose full fingerprint you independently compare with the official release-key information. A checksum from the same random mirror is not independent authentication. Stop if verification fails.

Insert the USB, then inspect:

```sh
diskutil list external physical
```

Identify the **whole USB disk** by capacity/model; do not use a partition such as `disk4s1`. Replace the placeholder below. It intentionally cannot run unchanged:

```sh
USB=/dev/diskREPLACE_WITH_VERIFIED_USB_NUMBER
diskutil info "$USB"
```

The next block erases the selected USB. After personally confirming it is the USB, not a Mac/internal/backup disk:

```sh
diskutil unmountDisk "$USB"
sudo dd if="$ISO" of="${USB/disk/rdisk}" bs=4m
sync
diskutil eject "$USB"
```

On macOS press Ctrl-T for progress; wait for successful completion. Choose **Ignore** if macOS offers to initialize the written disk. Do not initialize it.

## 3. Boot the ThinkPad and connect

Use F1 at startup for firmware settings (Enter then F1 may be necessary). Use UEFI boot, disable legacy/CSM if applicable, and temporarily disable Secure Boot without clearing its keys. Do not change SATA/controller mode or TPM settings. Use F12 to select the USB's UEFI boot entry. Select the normal Arch installation entry.

At the live root prompt:

```sh
loadkeys uk
test -d /sys/firmware/efi/efivars && echo 'UEFI OK'
timedatectl set-ntp true
ip link
```

If `UEFI OK` is absent, reboot correctly before continuing. Ethernet should obtain an address automatically. For Wi-Fi, run `iwctl` and use the actual device and SSID displayed (replace `wlan0` and `YOUR_SSID`):

```text
iwctl
device list
station wlan0 scan
station wlan0 get-networks
station wlan0 connect "YOUR_SSID"
exit
```

Enter the Wi-Fi password only at the prompt. Verify:

```sh
ping -c 3 archlinux.org
timedatectl status
```

## 4. Identify the Linux disk — critical checkpoint

```sh
lsblk -e7 -o NAME,PATH,SIZE,MODEL,SERIAL,TYPE,FSTYPE,MOUNTPOINTS
ls -l /dev/disk/by-id/
```

Find the **1 TB Linux SSD by model AND serial**. The 512 GB Windows SSD is protected. Do not assume `/dev/nvme0n1` is Linux. Set a stable whole-disk identifier, excluding `-part1` etc.:

```sh
DISK=/dev/disk/by-id/REPLACE_WITH_VERIFIED_1TB_SSD_ID
readlink -f "$DISK"
lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS "$DISK"
fdisk -l "$DISK"
swapon --show
```

Stop unless the selected device is the backed-up Linux SSD, no partition on it is mounted, and no target partition is active swap. If live media automounted it or enabled swap, resolve that explicitly first. Record the Windows disk identity separately. **Everything on `$DISK` will be lost in the next section.**

## 5. Partition, encrypt, create Btrfs

Only after approving that exact target, use `fdisk` interactively:

```sh
fdisk "$DISK"
```

Enter these responses, one per prompt:

```text
g
n
1
<Enter: default first sector>
+2G
t
1
n
2
<Enter: default first sector>
<Enter: use remaining disk>
t
2
20
p
```

`1` is EFI System and `20` is Linux filesystem on the expected GPT type menu; **confirm the displayed type names**, because menu numbering can change. Use `t`/`L` to select the named types if numbering differs. Confirm the printed table has exactly a 2 GiB EFI partition and one remaining Linux partition on the 1 TB SSD. Only then type `w`. Type `q` instead if anything is wrong. `<Enter: ...>` means press Enter; do not type those words.

Refresh and verify stable partition paths:

```sh
udevadm settle
ESP="${DISK}-part1"
CRYPT="${DISK}-part2"
lsblk -o NAME,SIZE,TYPE,FSTYPE "$DISK"
test -b "$ESP" && test -b "$CRYPT" && echo 'Partition paths OK'
```

If the partition paths do not exist, discover their exact by-id equivalents; do not improvise a different disk. Format only after verification:

```sh
mkfs.fat -F 32 -n ARCH_EFI "$ESP"
cryptsetup luksFormat --type luks2 "$CRYPT"
cryptsetup open "$CRYPT" cryptroot
mkfs.btrfs -L archroot /dev/mapper/cryptroot
mount /dev/mapper/cryptroot /mnt
for sub in @ @home @snapshots @log @pkg @tmp @state; do
    btrfs subvolume create "/mnt/$sub" || break
done
btrfs subvolume list /mnt
```

Require all seven subvolumes before proceeding. Choose a strong LUKS passphrase, distinct from account passwords, and keep an offline recovery copy. Nothing here uses TPM automatic unlock or discard.

```sh
umount /mnt
mount -o subvol=@,compress=zstd:3 /dev/mapper/cryptroot /mnt
mkdir -p /mnt/{home,.snapshots,var/log,var/cache/pacman/pkg,var/tmp,srv/workstation-state,efi}
mount -o subvol=@home,compress=zstd:3 /dev/mapper/cryptroot /mnt/home
mount -o subvol=@snapshots,compress=zstd:3 /dev/mapper/cryptroot /mnt/.snapshots
mount -o subvol=@log,compress=zstd:3 /dev/mapper/cryptroot /mnt/var/log
mount -o subvol=@pkg,compress=zstd:3 /dev/mapper/cryptroot /mnt/var/cache/pacman/pkg
mount -o subvol=@tmp,compress=zstd:3 /dev/mapper/cryptroot /mnt/var/tmp
mount -o subvol=@state,compress=zstd:3 /dev/mapper/cryptroot /mnt/srv/workstation-state
mount -o umask=0077 "$ESP" /mnt/efi
findmnt -R /mnt
```

Root includes `/var/lib/pacman` and kernel modules so they restore together. Home, logs and explicit persistent state survive root rollback. Snapshots are not backups and ESP files are not in root snapshots.

## 6. Install the base

```sh
pacstrap -K /mnt base linux-lts linux linux-firmware intel-ucode \
  btrfs-progs cryptsetup dosfstools networkmanager sudo git curl \
  neovim less man-db man-pages mkinitcpio efibootmgr systemd-ukify
```

Stop if pacstrap fails; do not chroot into an incomplete installation. Generate fstab exactly once, overwriting the fresh generated file rather than appending duplicates:

```sh
genfstab -U /mnt > /mnt/etc/fstab
cat /mnt/etc/fstab
LUKS_UUID=$(blkid -s UUID -o value "$CRYPT")
printf '%s\n' "$LUKS_UUID" > /mnt/root/install-luks-uuid
arch-chroot /mnt
```

You are now inside the new system as root. Set regional defaults (chosen UK English and London timezone):

```sh
ln -sf /usr/share/zoneinfo/Europe/London /etc/localtime
hwclock --systohc
sed -i 's/^#en_GB.UTF-8 UTF-8/en_GB.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
printf 'LANG=en_GB.UTF-8\n' > /etc/locale.conf
printf 'KEYMAP=uk\n' > /etc/vconsole.conf
printf 't480s\n' > /etc/hostname
cat > /etc/hosts <<'HOSTS'
127.0.0.1 localhost
::1 localhost
127.0.1.1 t480s
HOSTS
systemctl enable NetworkManager systemd-timesyncd
```

Create only the administrator during the manual base install. The bootstrap will later prompt for the daily username/password and optional agent accounts:

```sh
useradd -m -U -G wheel -s /bin/bash admin
chmod 700 /home/admin
passwd admin
passwd
install -m 0440 /dev/null /etc/sudoers.d/10-admin
printf 'admin ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/10-admin
visudo -cf /etc/sudoers
```

The last `passwd` sets a unique emergency root password. The admin sudo rule requires its password. Retain root recovery initially; decide later whether to lock root after testing recovery. Do not add a `%wheel NOPASSWD` rule.

## 7. Build UKIs and install Linux-owned boot files

This uses systemd initramfs unlock; do not mix it with the legacy `encrypt` hook.

```sh
mkdir -p /efi/EFI/Linux
LUKS_UUID=$(cat /root/install-luks-uuid)
printf 'rd.luks.name=%s=cryptroot root=/dev/mapper/cryptroot rootflags=subvol=@ rw\n' "$LUKS_UUID" > /etc/kernel/cmdline
```

Create these **two presets**. They replace the initial generated presets for the two installed kernels:

```sh
cat > /etc/mkinitcpio.d/linux-lts.preset <<'PRESET'
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux-lts"
PRESETS=('default')
default_uki="/efi/EFI/Linux/arch-lts.efi"
PRESET
cat > /etc/mkinitcpio.d/linux.preset <<'PRESET'
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux"
PRESETS=('default')
default_uki="/efi/EFI/Linux/arch-linux.efi"
PRESET
```

`ALL_config` selects the configuration explicitly, so set the required HOOKS in that file rather than a drop-in:

```sh
sed -i 's/^HOOKS=.*/HOOKS=(base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck)/' /etc/mkinitcpio.conf
grep '^HOOKS=' /etc/mkinitcpio.conf
mkinitcpio -P
ls -lh /efi/EFI/Linux/
```

Require both nonempty UKIs and no build errors. Do not reboot on failure. Keep `/boot` inside encrypted root; the ESP is `/efi`.

```sh
bootctl --esp-path=/efi install
mkdir -p /efi/loader/entries
cat > /efi/loader/loader.conf <<'CONF'
default lts.conf
timeout 5
editor no
CONF
cat > /efi/loader/entries/lts.conf <<'CONF'
title Arch Linux LTS
efi /EFI/Linux/arch-lts.efi
CONF
cat > /efi/loader/entries/linux.conf <<'CONF'
title Arch Linux regular kernel
efi /EFI/Linux/arch-linux.efi
CONF
bootctl --esp-path=/efi list
```

Automatic UKI discovery may show additional equivalent entries. `lts.conf` is the explicit default. This step writes firmware boot entries as well as the **Linux ESP only**; Windows must not be mounted. If `bootctl` fails to write NVRAM, stop and inspect its error; do not delete other boot entries.

Final base checks:

```sh
findmnt /efi
cat /etc/kernel/cmdline
cat /etc/fstab
pacman -Q linux-lts linux intel-ucode
visudo -cf /etc/sudoers
systemctl is-enabled NetworkManager
```

Require the ESP mount and root UUIDs to match the Linux disk. Then:

```sh
exit
umount -R /mnt
cryptsetup close cryptroot
reboot
```

Remove installer USB as the machine restarts. Unlock LUKS, boot LTS and log in as `admin`. Test `sudo -v`. The daily account does not exist yet. For Wi-Fi on the installed base, use `nmtui` from an admin/root session to connect. Confirm internet and `uname -r`, then test the regular-kernel entry once before installing the desktop.

**This is the base-install checkpoint.** A working encrypted text-console system is enough to run the bootstrap.

## 8. Get and run the LARBS-style bootstrap

The public distribution repository is [rpcauk/porthpean](https://github.com/rpcauk/porthpean). The maintainer uses `git@github.com:rpcauk/porthpean.git`; new machines use anonymous HTTPS, so no GitHub SSH key is needed during setup. Do not run the existing Mac dotfiles bootstrap on Arch.

Log in as `admin` on the installed system:

```sh
INSTALLER=$(mktemp)
curl --fail --show-error --location --proto '=https' --tlsv1.2 \
  https://raw.githubusercontent.com/rpcauk/porthpean/main/install.sh \
  -o "$INSTALLER"
less "$INSTALLER"
sudo bash "$INSTALLER"
```

Do not execute a failed/empty download. The entry script clones the public repository into a private root-owned directory and prints the exact revision. Review its `workstation/arch/bootstrap`, `site.yml` and managed files from another console, then type `REVIEWED`. Tracking `main` is convenient but mutable; compare/record the revision and later prefer a reviewed pinned release. A trusted first-stage file alone does not authenticate all subsequently fetched code.

The bootstrap asks:

1. Daily username, default `ryan`.
2. Whether to create a dedicated `codex` account.
3. Whether to create a dedicated `amp` account.
4. Confirmation of the displayed plan with `APPLY`.
5. The daily account password through standard `passwd` prompts (hidden, twice). Existing usable passwords are preserved unless you choose to change them.

Passwords are not passed to Ansible or stored in variables, arguments or configuration. Agents have locked passwords and no sudo, not shared copies of the daily/admin password. Declining an optional agent does not delete an account created on an earlier run.

The script creates the daily account, performs a complete official repository upgrade, installs the desktop/tooling and selected agent infrastructure, and enables greetd/firewall for the **next boot**. It does not format disks, enroll firmware keys, log into vendors, start SSH, deploy the Porthpean app or install an AUR helper. Stop on any failure and keep the admin console usable.

Offline transfer is still possible: copy the reviewed `workstation/arch/` directory from the Mac to a second ordinary USB, transfer it to a root-owned directory on Arch and run `bash bootstrap` there. Do not run unreviewed root scripts from a directory writable by another account.

After successful bootstrap, first test `sudo -l -U ryan` as admin/root: the daily account must have no sudo authorization. Then reboot deliberately. At greetd log in as `ryan`. Keys: Super+Enter terminal, Super+D launcher, Super+L lock, Super+Q close, Super+Shift+E exit, Super+H/J/K/semicolon navigation. Keyboard layout is GB. The desktop uses `niri-session` for systemd session integration. PipeWire/WirePlumber use their packaged user activation; do not enable duplicate system-wide audio services.

The firewall file is a fresh standalone workstation ruleset and replaces any prior nftables file with a backup. It denies unsolicited inbound traffic including SSH; later Tailscale/container/network integration needs its own reviewed policy. Use this bootstrap on this fresh base, not on an already network-managed server.

## 9. Install and authenticate the two agents

The bootstrap creates accounts, workspaces and operating guidance, **not** privileged background services. Start each vendor installer as its own account; the included helper downloads the vendor script to a temporary file, shows its checksum and opens it in `less`, then requires `INSTALL` before execution. Inspect additional downloads as part of trusting the vendor installer. This is still network code execution, not a reproducible pinned package.

From an admin root shell, copy the helper into root-owned executable storage:

```sh
# Replace this with the root-owned review copy printed by install.sh:
CHECKOUT=/root/porthpean-install.REPLACE/repo
install -m 0755 "$CHECKOUT/workstation/arch/install-agent" /usr/local/bin/install-workstation-agent
su - codex
install-workstation-agent
exit
su - amp
install-workstation-agent
exit
```

Open a fresh login shell for each account after installation; confirm the binary is in that account's PATH, and inspect `command -v codex` / `command -v amp` plus `--version`. As `codex`, run `codex` and sign in interactively using your own subscription/authentication flow. As `amp`, run `amp login`, then `amp`. Do not copy the Mac's credentials or place API keys in commands, scripts or shared environment files. Both agents contact external providers; dedicated accounts do not make submitted code private/offline. Review provider retention/sharing settings before sending sensitive repositories.

Interactive sessions from an admin shell:

```sh
sudo -iu codex
cd ~/Projects
tmux new-session -A -s codex
# Inside tmux: cd into this account's own clone, then run codex.
```

For Amp use `sudo -iu amp` and `tmux new-session -A -s amp`. Detach with Ctrl-B then D. Do not run both agents against the same writable checkout. Give each a separate clone and branch; review and integrate commits as the human. A root/admin operator can copy patches into the daily user's repository; agents cannot directly read `/home/ryan`.

No SSH listener, Tailscale enrollment, login linger, automatic tmux startup, Codex HTTP wrapper, agent sudo, Docker socket or production kubeconfig is configured. Local tmux sessions may not survive all logout/session-manager policies; keep the operator session while working. Persistent remote use is a later explicit step following the existing dotfiles `docs/codex-homelab.md`, with private-network policy and independently scoped credentials. Do not disable sandbox/approval controls.

## 10. Finish safely after the base and desktop work

These are follow-up setup gates, not features the initial script silently claims to have completed:

- **Secure Boot:** UKIs exist but are initially unsigned. Install/review sbctl, export current enrolled keys, create protected owner keys, then inspect the actual firmware trust configuration. Enroll with the necessary Microsoft/OEM trust only after Windows recovery and firmware recovery are verified. Sign the Linux boot manager, fallback EFI loader and both UKIs; integrate signing into updates and test rejection of unsigned media. Do not run automatic key-enrollment or force/YOLO options. Exact firmware enrollment cannot be supplied safely without checking this T480s's current keys/settings.
- **Backups:** configure Restic only once the private Debian destination and independent second copy are selected; authenticate with dedicated credentials, run the first backup, restore test data, then enable a timer. Do not declare the workstation protected until restoration works.
- **Recovery:** save an encrypted offline LUKS header backup and keys; retain recovery USB. Create root snapshots together with matching boot-image copies before future upgrades. The initial bootstrap installs Restic/Btrfs tooling but does not invent a backup server or claim automatic matched rollback.
- **Kanata:** remapping depends on the actual keyboard and desired layout. Inspect `/dev/input/by-id` and review package provenance before installation; use a dedicated service identity and selected input nodes/uinput. Do not add `ryan` to `input` or grant all agents keyboard access. Stock keyboard works until this is configured.
- **Maintenance:** complete weekly upgrades require approval. No unattended upgrades or reboots. Before upgrades, verify space/backups, take matched root+boot recovery sets and read Arch news. A separate regular kernel is not a complete rollback strategy.

## 11. Checks and rescue

Before adopting as the daily machine: boot both kernels; test daily/admin separation, audio, Wi-Fi reconnect, lock before suspend, repeated resume, TrackPoint/touchpad, display/dock, and backup restore. Check `systemctl --failed`, `systemctl --user --failed`, `wpctl status`, `nft list ruleset` as admin, and `sudo -l -U codex` / `sudo -l -U amp` (both denied). Verify both agent homes are mode 700 and neither has privileged groups. If greetd fails, use Ctrl-Alt-F2 and log into the admin text console.

If boot fails: reinsert installer USB, boot UEFI with the documented temporary Secure Boot setting, reconnect networking only if needed, identify Linux partitions again, then:

```sh
# Set CRYPT and ESP again from verified stable Linux partition identities.
cryptsetup open "$CRYPT" cryptroot
mount -o subvol=@ /dev/mapper/cryptroot /mnt
mount "$ESP" /mnt/efi
arch-chroot /mnt
# Inspect cmdline, fstab, presets and mkinitcpio errors first.
# Rebuild only after correcting the diagnosed issue:
mkinitcpio -P
bootctl --esp-path=/efi list
```

Do not format again to fix a boot failure. For a complete root rollback use the matched root/UKI procedure in the main specification; do not restore a root snapshot while leaving mismatched new boot images/modules. Reconnect Windows, if disconnected, only through the service procedure; test its independent firmware boot and recovery state without mounting its partitions in Arch.

## Sources and limits

Prepared 14 November 2026. Scripts passed shell/Ansible syntax validation only; no Arch install, desktop, agent installer or firmware change was executed. Review Arch's current documentation when using a newer ISO. Arch Wiki full-text access was blocked during preparation; official manual pages were available.

- [Arch downloads, verification and release image](https://archlinux.org/download/)
- [Arch installation guide](https://wiki.archlinux.org/title/Installation_guide)
- [mkinitcpio options](https://man.archlinux.org/man/mkinitcpio.8.en), [configuration precedence](https://man.archlinux.org/man/mkinitcpio.conf.5.en)
- [Niri setup](https://niri-wm.github.io/niri/Getting-Started.html)
- [Codex installation and authentication](https://learn.chatgpt.com/docs/codex/cli)
- [Amp CLI installation and account login](https://ampcode.com/docs/cli)
- [sbctl signing and enrollment considerations](https://man.archlinux.org/man/sbctl.8.en)
