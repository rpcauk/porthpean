#!/usr/bin/env bash
# Run from the official Arch USB as root. No passwords are stored by this script.
set -euo pipefail
export LC_ALL=C
umask 077
fail() { printf 'STOP: %s\n' "$*" >&2; exit 1; }
confirm() {
  local expected=$1 answer
  read -r -p "Type '$expected' to continue: " answer
  [[ $answer == "$expected" ]] || fail 'Confirmation did not match. Nothing further will run.'
}
whole_disk() {
  local given=$1 resolved
  [[ $given == /dev/disk/by-id/* && $given != *-part[0-9]* ]] || fail 'Use a whole-disk /dev/disk/by-id/ identity, not a partition.'
  resolved=$(readlink -f -- "$given")
  [[ -b $resolved && $(lsblk -dnro TYPE "$resolved") == disk ]] || fail 'Not a whole block disk.'
  printf '%s\n' "$resolved"
}
unused_disk() {
  local disk=$1 mounts types
  mounts=$(lsblk -nrpo MOUNTPOINTS "$disk")
  [[ ! $mounts =~ [^[:space:]] ]] || fail "Target or descendant is mounted/active swap: $disk"
  types=$(lsblk -nro TYPE "$disk")
  [[ ! $types =~ (crypt|lvm|raid|md) ]] || fail 'Target has an active mapped/RAID descendant; resolve it manually.'
  [[ $(lsblk -dnro RO "$disk") == 0 && $(lsblk -dnro RM "$disk") == 0 ]] || fail 'Refusing a read-only or removable installation target.'
}

same_install_disk() {
  local rootpart=$1 efipart=$2 parent
  [[ $(lsblk -dnro TYPE "$rootpart") == part && $(lsblk -dnro TYPE "$efipart") == part ]] || fail 'Expected root and ESP to be disk partitions.'
  parent=$(lsblk -dnro PKNAME "$rootpart")
  [[ -n $parent && $(lsblk -dnro PKNAME "$efipart") == "$parent" ]] || fail 'ESP and encrypted root are on different disks; refusing possible Windows ESP.'
  printf '%s\n' "$parent"
}

main() {
trap 'printf "Stopped at line %s. Do not reboot blindly or restart in fresh-install mode. Inspect the error; mounted filesystems are left in place.\n" "$LINENO" >&2' ERR

# These checks run before any mutation, including prompts which could mislead on another OS.
[[ $EUID == 0 ]] || fail 'Run as root from the Arch USB.'
[[ -t 0 && -t 1 ]] || fail 'Download, inspect and run interactively; do not pipe into bash.'
[[ $(uname -m) == x86_64 && -f /etc/arch-release && -d /run/archiso ]] || fail 'Requires the Arch x86_64 live USB, not an installed OS or chroot.'
[[ -d /sys/firmware/efi/efivars ]] || fail 'Boot the USB in UEFI mode.'
for tool in lsblk findmnt cryptsetup sfdisk udevadm mount umount blkid btrfs mkfs.fat mkfs.btrfs pacstrap genfstab arch-chroot curl flock; do
  command -v "$tool" >/dev/null || fail "Missing live-media tool: $tool"
done
exec 9>/run/porthpean-arch-install.lock
flock -n 9 || fail 'Another instance is running.'
[[ $# -le 1 ]] || fail 'Usage: bash arch-install.sh [--continue]'
mode=${1:-}
if [[ -z $mode ]]; then
  echo '1: FRESH install — erase a selected disk, then install the base.'
  echo '2: CONTINUE from stage 6 — validate /mnt and install/configure base; NO formatting.'
  read -r -p 'Choose 1 or 2 (no default): ' choice
  case "$choice" in 1) mode=--fresh ;; 2) mode=--continue ;; *) fail 'Choose 1 or 2.' ;; esac
fi
[[ $mode == --fresh || $mode == --continue ]] || fail 'Unknown mode.'
read -r -p 'Hostname [t480s]: ' host
host=${host:-t480s}
[[ ${#host} -le 63 && $host =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || fail 'Use a hostname of 1–63 lowercase letters/digits/hyphens, without leading/trailing hyphen.'
echo 'Profile: UK console keyboard, en_GB.UTF-8, Europe/London, admin account.'
echo 'Desktop/daily user and optional Codex/Amp accounts are configured after reboot.'
loadkeys uk
timedatectl set-ntp true
if ! curl --fail --silent --show-error --head --connect-timeout 15 https://archlinux.org/ >/dev/null; then
  echo 'Connect Ethernet or use iwctl in another console, then rerun. No disk changes have been made.'
  exit 1
fi
lsblk -e7 -o NAME,PATH,SIZE,MODEL,SERIAL,TYPE,FSTYPE,MOUNTPOINTS


if [[ $mode == --fresh ]]; then
  mountpoint -q /mnt && fail '/mnt is already mounted. Use --continue to preserve the stage-6 layout.'
  [[ ! -e /dev/mapper/cryptroot ]] || fail 'cryptroot is already open. Inspect it; do not restart a fresh install.'
  read -r -p 'Protected Windows whole-disk by-id path, or DISCONNECTED if physically removed: ' protected
  if [[ $protected != DISCONNECTED ]]; then
    protected=$(whole_disk "$protected")
    echo 'Protected Windows disk:'
    lsblk -dn -o PATH,SIZE,MODEL,SERIAL "$protected"
  fi
  read -r -p 'Linux whole-disk /dev/disk/by-id/... to ERASE: ' disk_id
  disk=$(whole_disk "$disk_id")
  [[ $disk != "$protected" ]] || fail 'Linux target is the protected Windows disk.'
  unused_disk "$disk"
  serial=$(lsblk -dnro SERIAL "$disk")
  serial=${serial## }; serial=${serial%% }
  [[ -n $serial ]] || fail 'No hardware serial reported. Resolve disk identity manually.'
  [[ $(blockdev --getsize64 "$disk") -ge 34359738368 ]] || fail 'Target is smaller than 32 GiB.'
  echo 'EXACT ERASE TARGET:'
  lsblk -o PATH,SIZE,MODEL,SERIAL,TYPE,FSTYPE,MOUNTPOINTS "$disk"
  echo 'Plan: erase this disk; GPT; 2 GiB EFI partition; remaining LUKS2 + Btrfs.'
  echo 'All existing data on this target is lost. The protected Windows disk is not used.'
  echo 'Confirm that backups/Windows recovery keys exist and disk model/serial are correct.'
  confirm "ERASE $serial"
  # Recheck immediately before the first destructive operation.
  [[ $(readlink -f -- "$disk_id") == "$disk" && $(lsblk -dnro SERIAL "$disk") == "$serial" ]] || fail 'Disk identity changed.'
  unused_disk "$disk"
  sfdisk --lock --wipe always --wipe-partitions always "$disk" <<'LAYOUT'
label: gpt
size=2GiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="ARCH_EFI"
type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="ARCH_LUKS"
LAYOUT
  udevadm settle
  esp=$(lsblk -nrpo PATH,PARTN "$disk" | awk '$2 == 1 {print $1}')
  crypt=$(lsblk -nrpo PATH,PARTN "$disk" | awk '$2 == 2 {print $1}')
  [[ -b $esp && -b $crypt ]] || fail 'Could not identify the two new partitions.'
  mkfs.fat -F 32 -n ARCH_EFI "$esp"
  echo 'Set the DRIVE passphrase at cryptsetup prompts; then enter it again to unlock.'
  cryptsetup luksFormat --type luks2 --verify-passphrase "$crypt"
  cryptsetup open "$crypt" cryptroot
  mkfs.btrfs -L archroot /dev/mapper/cryptroot
  mount /dev/mapper/cryptroot /mnt
  for sub in @ @home @snapshots @log @pkg @tmp @state; do btrfs subvolume create "/mnt/$sub"; done
  umount /mnt
  mount -o subvol=@,compress=zstd:3 /dev/mapper/cryptroot /mnt
  for pair in '@home:home' '@snapshots:.snapshots' '@log:var/log' '@pkg:var/cache/pacman/pkg' '@tmp:var/tmp' '@state:srv/workstation-state'; do
    sub=${pair%%:*}; path=${pair#*:}
    mkdir -p "/mnt/$path"
    mount -o "subvol=$sub,compress=zstd:3" /dev/mapper/cryptroot "/mnt/$path"
  done
  mkdir -p /mnt/efi
  mount -o umask=0077 "$esp" /mnt/efi
fi

# Shared strict validation. Continue mode reaches here without calling partition/format/open commands.
mountpoint -q /mnt || fail '/mnt is not mounted; follow stage 5 first.'
[[ $(findmnt -nr -M /mnt -o FSTYPE) == btrfs && $(findmnt -nr -M /mnt -o FSROOT) == /@ ]] || fail 'Expected /mnt to be Btrfs subvolume @.'
[[ -b /dev/mapper/cryptroot ]] || fail 'Expected the existing cryptroot mapping.'
rootdev=$(findmnt -nr -M /mnt -o SOURCE)
rootdev=${rootdev%%\[*}
[[ $(readlink -f "$rootdev") == "$(readlink -f /dev/mapper/cryptroot)" ]] || fail '/mnt is not on cryptroot.'
crypt=$(cryptsetup status cryptroot | awk '$1 == "device:" {print $2}')
[[ -b $crypt ]] || fail 'Cannot discover the LUKS backing partition.'
cryptsetup isLuks --type luks2 "$crypt" || fail 'Expected LUKS2.'
[[ $(btrfs filesystem show /mnt | awk '/Total devices/ {print $3}') == 1 ]] || fail 'Only a single-device Btrfs layout is supported.'
for pair in '@home:home' '@snapshots:.snapshots' '@log:var/log' '@pkg:var/cache/pacman/pkg' '@tmp:var/tmp' '@state:srv/workstation-state'; do
  sub=${pair%%:*}; path=${pair#*:}
  mountpoint -q "/mnt/$path" || fail "Missing stage-5 mount: /mnt/$path"
  [[ $(findmnt -nr -M "/mnt/$path" -o FSROOT) == "/$sub" ]] || fail "Wrong subvolume at $path"
  source=$(findmnt -nr -M "/mnt/$path" -o SOURCE); source=${source%%\[*}
  [[ $(readlink -f "$source") == "$(readlink -f /dev/mapper/cryptroot)" ]] || fail "Wrong filesystem at $path"
done
mountpoint -q /mnt/efi || fail 'Linux ESP must be mounted at /mnt/efi.'
[[ $(findmnt -nr -M /mnt/efi -o FSTYPE) == vfat ]] || fail 'Expected FAT Linux ESP.'
esp=$(findmnt -nr -M /mnt/efi -o SOURCE)
parent=$(same_install_disk "$crypt" "$esp")
[[ $(lsblk -dnro PARTTYPE "$esp") == c12a7328-f81f-11d2-ba4b-00a0c93ec93b ]] || fail 'Expected GPT EFI partition type.'
targets=$(findmnt -rn -R -M /mnt -o TARGET)
while IFS= read -r target; do
  case "$target" in /mnt|/mnt/home|/mnt/.snapshots|/mnt/var/log|/mnt/var/cache/pacman/pkg|/mnt/var/tmp|/mnt/srv/workstation-state|/mnt/efi) ;;
    *) fail "Unexpected target mount $target. Finish/stop any active pacstrap/chroot first." ;;
  esac
  [[ ,$(findmnt -nr -M "$target" -o OPTIONS), == *,rw,* ]] || fail "Read-only target mount $target"
done <<< "$targets"
[[ ! -e /mnt/root/porthpean-base-complete ]] || fail 'Base installation already marked complete; use installed-system bootstrap after reboot.'
findmnt -R /mnt
lsblk -o PATH,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS "/dev/$parent"
printf 'Install/configure base at /mnt; hostname %s; admin + emergency root passwords will be requested.\n' "$host"
echo 'No formatting occurs after this point. Existing fstab/configuration may be replaced with backups.'
echo 'Leave any current pacstrap/chroot before continuing. Keep AC power and internet connected.'
confirm INSTALL-BASE
pacstrap -K /mnt base linux-lts linux linux-firmware intel-ucode \
  btrfs-progs cryptsetup dosfstools networkmanager sudo git curl \
  neovim less man-db man-pages mkinitcpio efibootmgr systemd-ukify
[[ -e /mnt/etc/fstab ]] && cp -a /mnt/etc/fstab "/mnt/etc/fstab.before-porthpean.$(date +%s)"
genfstab -U /mnt > /mnt/etc/fstab
chmod 0644 /mnt/etc/fstab
luks_uuid=$(blkid -s UUID -o value "$crypt")
[[ $luks_uuid =~ ^[0-9a-fA-F-]{36}$ ]] || fail 'Missing/invalid LUKS UUID.'
arch-chroot /mnt /bin/bash -s -- "$host" "$luks_uuid" <<'CHROOT'
set -euo pipefail
umask 022
host=$1
luks_uuid=$2
# Preserve overwritten base configuration; this contains no newly collected secrets.
backup=/root/porthpean-base-backup.$(date +%s)
mkdir -m 0700 -p "$backup"
for file in /etc/hostname /etc/hosts /etc/locale.conf /etc/vconsole.conf /etc/kernel/cmdline /etc/mkinitcpio.conf /etc/mkinitcpio.d/linux.preset /etc/mkinitcpio.d/linux-lts.preset /efi/loader/loader.conf; do
  [[ ! -f $file ]] || cp --parents -a "$file" "$backup/"
done
ln -sf /usr/share/zoneinfo/Europe/London /etc/localtime
hwclock --systohc
sed -i 's/^#en_GB.UTF-8 UTF-8/en_GB.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
printf 'LANG=en_GB.UTF-8\n' > /etc/locale.conf
printf 'KEYMAP=uk\n' > /etc/vconsole.conf
printf '%s\n' "$host" > /etc/hostname
printf '127.0.0.1 localhost\n::1 localhost\n127.0.1.1 %s\n' "$host" > /etc/hosts
systemctl enable NetworkManager systemd-timesyncd
if ! id admin >/dev/null 2>&1; then
  useradd -m -U -G wheel -s /bin/bash admin
else
  [[ $(id -u admin) -ge 1000 && $(getent passwd admin | cut -d: -f6) == /home/admin ]] || exit 1
fi
chmod 700 /home/admin
echo 'Set ADMIN account password (not the disk passphrase):'
passwd admin </dev/tty
echo 'Set a separate emergency ROOT password:'
passwd root </dev/tty
mkdir -p /etc/sudoers.d
printf 'admin ALL=(ALL:ALL) ALL\n' > /etc/sudoers.d/10-admin
chmod 0440 /etc/sudoers.d/10-admin
visudo -cf /etc/sudoers
mkdir -p /etc/kernel /efi/EFI/Linux
printf 'rd.luks.name=%s=cryptroot root=/dev/mapper/cryptroot rootflags=subvol=@ rw\n' "$luks_uuid" > /etc/kernel/cmdline
sed -i 's/^HOOKS=.*/HOOKS=(base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck)/' /etc/mkinitcpio.conf
grep -qx 'HOOKS=(base systemd autodetect microcode modconf kms keyboard sd-vconsole block sd-encrypt filesystems fsck)' /etc/mkinitcpio.conf
for kernel in linux-lts linux; do
  case "$kernel" in linux-lts) image=arch-lts ;; linux) image=arch-linux ;; esac
  cat > "/etc/mkinitcpio.d/$kernel.preset" <<PRESET
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-$kernel"
PRESETS=('default')
default_uki="/efi/EFI/Linux/$image.efi"
PRESET
done
mkinitcpio -P
[[ -s /efi/EFI/Linux/arch-lts.efi && -s /efi/EFI/Linux/arch-linux.efi ]]
bootctl --esp-path=/efi install
mkdir -p /efi/loader/entries
printf 'default lts.conf\ntimeout 5\neditor no\n' > /efi/loader/loader.conf
printf 'title Arch Linux LTS\nefi /EFI/Linux/arch-lts.efi\n' > /efi/loader/entries/lts.conf
printf 'title Arch Linux regular kernel\nefi /EFI/Linux/arch-linux.efi\n' > /efi/loader/entries/linux.conf
bootctl --esp-path=/efi list
pacman -Q linux-lts linux intel-ucode
systemctl is-enabled NetworkManager
printf 'Completed %s\n' "$(date -Iseconds)" > /root/porthpean-base-complete
CHROOT
printf '\nBase installed. No reboot/unmount is automatic. Review errors above and /mnt/etc/fstab.\n'
echo 'Secure Boot remains in its existing state; signed-key enrollment is not performed.'
echo 'When satisfied: umount -R /mnt; cryptsetup close cryptroot; reboot'
echo 'After reboot: log in as admin, check networking, then follow INSTALL.md for the daily user/desktop/agents.'

}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
