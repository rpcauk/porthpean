#!/usr/bin/env bash
# Run from the official Arch USB as root. No passwords are stored by this script.
set -euo pipefail
export LC_ALL=C
umask 077
fail() { printf 'STOP: %s\n' "$*" >&2; exit 1; }
cancel() { echo 'Cancelled.'; exit 0; }
ui_input() {
  whiptail --backtitle 'Porthpean - Arch Linux' --title "$1" --output-fd 3 \
    --inputbox "$2" 10 72 "$3" 3>&1 1>&2
}
select_disk() {
  local records path type ro removable description
  local -a options=()
  records=$(lsblk -dnrpo PATH,TYPE,RO,RM) || return 1
  while read -r path type ro removable; do
    [[ $type == disk && $ro == 0 && $removable == 0 ]] || continue
    description=$(lsblk -dn -o SIZE,MODEL "$path") || return 1
    options+=("$path" "$description")
  done <<< "$records"
  [[ ${#options[@]} -gt 0 ]] || fail 'No writable internal disks found.'
  whiptail --backtitle 'Porthpean - Arch Linux' --title 'Install disk' --output-fd 3 \
    --menu 'Select the disk for Arch Linux.' 18 78 8 "${options[@]}" 3>&1 1>&2
}
confirm_erase() {
  local disk=$1 description
  description=$(lsblk -dn -o SIZE,MODEL "$disk") || return 1
  whiptail --backtitle 'Porthpean - Arch Linux' --title 'Erase disk' --defaultno \
    --yes-button 'Erase and install' --no-button 'Cancel' \
    --yesno "$disk - $description\n\nAll partitions and data on this disk will be erased." 12 78
}
is_block_device() { [[ -b $1 ]]; }

whole_disk() {
  local given=$1 resolved
  [[ $given == /dev/* ]] || fail 'Enter a whole-disk path such as /dev/sda or /dev/nvme0n1.'
  resolved=$(readlink -f -- "$given")
  is_block_device "$resolved" || fail 'Not a block device.'
  [[ $(lsblk -dnro TYPE "$resolved") == disk ]] || fail 'Select the whole disk, not a partition (for example /dev/sda, not /dev/sda1).'
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
  [[ -n $parent && $(lsblk -dnro PKNAME "$efipart") == "$parent" ]] || fail 'ESP and encrypted root are on different disks.'
  printf '%s\n' "$parent"
}

cryptroot_open() { [[ -e /dev/mapper/cryptroot ]]; }

source_on_disk() {
  local source=${1%%\[*} disk=$2 path paths canonical candidate
  [[ $source == /dev/* ]] || return 1
  canonical=$(readlink -f -- "$source") || return 1
  [[ -n $canonical ]] || return 1
  paths=$(lsblk -nrpo PATH "$disk") || return 1
  while IFS= read -r path; do
    candidate=$(readlink -f -- "$path") || return 1
    [[ -n $candidate && $canonical == "$candidate" ]] && return 0
  done <<< "$paths"
  return 1
}

plan_partial_cleanup() {
  local disk=$1 source target records paths path type backing mounts
  cleanup_mounted=false
  cleanup_mapping=false
  [[ $(lsblk -dnro RO "$disk") == 0 && $(lsblk -dnro RM "$disk") == 0 ]] || fail 'Refusing a read-only or removable target.'
  mounts=$(lsblk -nrpo MOUNTPOINTS "$disk")
  [[ $mounts != *'[SWAP]'* ]] || fail 'Target has active swap; disable it manually or reboot the USB first.'
  paths=$(lsblk -nrpo PATH,TYPE "$disk")
  while read -r path type; do
    case "$type" in
      disk|part) ;;
      crypt) [[ $(readlink -f -- "$path") == "$(readlink -f /dev/mapper/cryptroot)" ]] || fail 'Unexpected encrypted mapping; reboot the USB or inspect manually.' ;;
      *) fail "Unsupported active target device: $path ($type)" ;;
    esac
  done <<< "$paths"
  if cryptroot_open; then
    backing=$(cryptsetup status cryptroot | awk '$1 == "device:" {print $2}')
    source_on_disk "$backing" "$disk" || fail 'cryptroot belongs to another disk; it will not be closed.'
    cleanup_mapping=true
  fi
  records=$(findmnt -rn -o SOURCE,TARGET)
  while read -r source target; do
    if [[ $target == /mnt || $target == /mnt/* ]] || source_on_disk "$source" "$disk"; then
      case "$target" in
        /mnt|/mnt/home|/mnt/.snapshots|/mnt/var/log|/mnt/var/cache/pacman/pkg|/mnt/var/tmp|/mnt/srv/workstation-state|/mnt/efi) ;;
        *) fail "Target is in use at $target. Exit chroots/stop installers or reboot the USB first." ;;
      esac
      source_on_disk "$source" "$disk" || fail "Mount $target is not on the selected Linux disk; refusing cleanup."
      cleanup_mounted=true
    fi
  done <<< "$records"
  if [[ $cleanup_mounted == true ]]; then
    mountpoint -q /mnt || fail 'Orphaned child mounts below /mnt; inspect manually or reboot the USB.'
    echo 'Partial installation mounts to unmount before erasure:'
    findmnt -R /mnt
  fi
  [[ $cleanup_mapping == false ]] || echo 'Partial encryption mapping to close: cryptroot (on selected target only).'
}

clear_partial_install() {
  local disk=$1
  # Revalidate the entire cleanup plan immediately before touching mounts.
  plan_partial_cleanup "$disk"
  cd /
  if [[ $cleanup_mounted == true ]]; then
    umount -R /mnt || fail 'Target is busy. No forced/lazy unmount used. Exit other sessions/installers or reboot the USB.'
  fi
  if [[ $cleanup_mapping == true ]]; then
    cryptsetup close cryptroot || fail 'cryptroot is busy; inspect it or reboot the USB before retrying.'
  fi
  unused_disk "$disk"
}

main() {
trap 'printf "Stopped at line %s. Inspect the error; mounted filesystems are left in place. Rerunning this installer starts over and ERASES the selected disk after confirmation.\n" "$LINENO" >&2' ERR

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
[[ $# == 0 ]] || fail 'Usage: bash arch-install.sh (always a fresh install; no resume modes)'
loadkeys uk
timedatectl set-ntp true
if ! curl --fail --silent --show-error --head --connect-timeout 15 https://archlinux.org/ >/dev/null; then
  echo 'Connect Ethernet or use iwctl in another console, then rerun. No disk changes have been made.'
  exit 1
fi
# Install only the dialog dependency into the disposable live USB if needed.
if ! command -v whiptail >/dev/null; then
  pacman -Sy --needed --noconfirm libnewt
fi
if ! host=$(ui_input 'Hostname' 'Name this computer:' t480s); then cancel; fi
[[ ${#host} -le 63 && $host =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || fail 'Use a hostname of 1–63 lowercase letters/digits/hyphens, without leading/trailing hyphen.'
if ! disk_id=$(select_disk); then cancel; fi
disk=$(whole_disk "$disk_id")
plan_partial_cleanup "$disk"
serial=$(lsblk -dnro SERIAL "$disk")
serial=${serial## }; serial=${serial%% }
[[ -n $serial ]] || fail 'No hardware serial reported. Resolve disk identity manually.'
[[ $(blockdev --getsize64 "$disk") -ge 34359738368 ]] || fail 'Target is smaller than 32 GiB.'
if ! confirm_erase "$disk"; then cancel; fi
# Recheck immediately before the first destructive operation.
[[ $(readlink -f -- "$disk_id") == "$disk" && $(lsblk -dnro SERIAL "$disk") == "$serial" ]] || fail 'Disk identity changed.'
clear_partial_install "$disk"
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
cryptsetup luksFormat --type luks2 --batch-mode --verify-passphrase "$crypt"
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

# Verify the new layout before installing packages or boot files.
mountpoint -q /mnt || fail '/mnt did not mount successfully.'
[[ $(findmnt -nr -M /mnt -o FSTYPE) == btrfs && $(findmnt -nr -M /mnt -o FSROOT) == /@ ]] || fail 'Expected /mnt to be Btrfs subvolume @.'
[[ -b /dev/mapper/cryptroot ]] || fail 'Expected the new cryptroot mapping.'
rootdev=$(findmnt -nr -M /mnt -o SOURCE)
rootdev=${rootdev%%\[*}
[[ $(readlink -f "$rootdev") == "$(readlink -f /dev/mapper/cryptroot)" ]] || fail '/mnt is not on cryptroot.'
crypt=$(cryptsetup status cryptroot | awk '$1 == "device:" {print $2}')
[[ -b $crypt ]] || fail 'Cannot discover the LUKS backing partition.'
cryptsetup isLuks --type luks2 "$crypt" || fail 'Expected LUKS2.'
[[ $(btrfs filesystem show /mnt | awk '/Total devices/ {print $3}') == 1 ]] || fail 'Only a single-device Btrfs layout is supported.'
for pair in '@home:home' '@snapshots:.snapshots' '@log:var/log' '@pkg:var/cache/pacman/pkg' '@tmp:var/tmp' '@state:srv/workstation-state'; do
  sub=${pair%%:*}; path=${pair#*:}
  mountpoint -q "/mnt/$path" || fail "Missing install mount: /mnt/$path"
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
findmnt -R /mnt
lsblk -o PATH,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS "/dev/$parent"
printf 'Install/configure base at /mnt; hostname %s; admin + emergency root passwords will be requested.\n' "$host"
echo 'Fresh layout created. Installing the base; keep AC power and internet connected.'
pacstrap -K /mnt base linux-lts linux linux-firmware intel-ucode \
  btrfs-progs cryptsetup dosfstools networkmanager sudo git curl \
  neovim less libnewt man-db man-pages mkinitcpio efibootmgr systemd-ukify
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
