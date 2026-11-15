#!/usr/bin/env bash
# Run from the official Arch USB as root. Passwords exist briefly in memory, never saved.
set +x
set +v
set +a
unset drive_pass
set -euo pipefail
export LC_ALL=C
umask 077
fail() {
  if [[ -n ${install_log:-} ]]; then printf 'STOP: %s\n' "$*" >> "$install_log";
  else printf 'STOP: %s\n' "$*" >&2; fi
  exit 1
}
cancel() {
  unset drive_pass
  if [[ ${installation_started:-false} == true ]]; then
    whiptail --title 'Setup stopped' --msgbox 'Installation is incomplete. You can restart this installer to erase the target and try again.' 10 76 || true
  fi
  exit 0
}
# Return a confirmed secret on stdout only; dialog rendering stays on the terminal.
# Callers must keep xtrace/verbose/allexport disabled and unset the result promptly.
ui_password() {
  local title=$1 first second
  export -n first second
  while true; do
    if ! first=$(whiptail --title "$title" --output-fd 3 \
      --passwordbox 'Enter password:' 10 72 3>&1 1>&2); then return 1; fi
    if [[ -z $first || $first == *$'\n'* || $first == *$'\r'* ]]; then
      unset first
      whiptail --title "$title" --msgbox 'Enter a non-empty, single-line password.' 9 72 >&2 || true
      continue
    fi
    if ! second=$(whiptail --title "$title" --output-fd 3 \
      --passwordbox 'Repeat password:' 10 72 3>&1 1>&2); then unset first; return 1; fi
    if [[ $first == "$second" ]]; then
      printf '%s' "$first"
      unset first second
      return 0
    fi
    unset first second
    whiptail --title "$title" --msgbox 'Passwords did not match. Try again.' 9 72 >&2 || true
  done
}

set_target_password() {
  local account=$1 secret
  export -n secret
  while true; do
    if ! secret=$(ui_password "$account account password"); then return 1; fi
    if printf '%s:%s\n' "$account" "$secret" | run_progress "Setting $account password" arch-chroot /mnt chpasswd; then
      unset secret
      return 0
    fi
    unset secret
    whiptail --title 'Account password' --msgbox 'The password was not accepted. Try another password.' 10 72 >&2 || true
  done
}

run_progress() {
  local stage=$1
  shift
  if [[ -n ${progress_helper:-} ]]; then
    python3 "$progress_helper" --stage "$stage" --log "$install_log" -- "$@" 2>> "$install_log"
  else
    "$@"
  fi
}

format_and_unlock() {
  local partition=$1 status
  if ! printf '%s' "$drive_pass" | run_progress "Encrypting the drive" cryptsetup luksFormat --type luks2 --batch-mode --key-file - "$partition"; then
    unset drive_pass
    return 1
  fi
  while true; do
    if printf '%s' "$drive_pass" | run_progress "Unlocking the drive" cryptsetup open --key-file - "$partition" cryptroot; then
      unset drive_pass
      return 0
    else
      status=$?
    fi
    unset drive_pass
    # Retry a rejected unlock secret, never reformat an existing LUKS header.
    [[ $status == 2 ]] || return "$status"
    whiptail --title 'Drive password' --msgbox 'The password was not accepted. Try again.' 9 72 >&2 || true
    if ! drive_pass=$(ui_password 'Unlock encrypted drive'); then return 1; fi
  done
}

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

write_progress_helper() {
  cat > "$progress_helper" <<'PORTHPEAN_PROGRESS_PY'
#!/usr/bin/env python3
"""Keep noninteractive installer commands behind a whiptail gauge.

The child gets a PTY for output (so pacman emits real progress), but inherits
stdin directly. Password pipes are never echoed to the PTY or recorded.
"""
import argparse
import errno
import fcntl
import os
import re
import selectors
import signal
import struct
import subprocess
import termios
import time

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)')
PACKAGE = re.compile(r'\(\s*(\d+)\s*/\s*(\d+)\)\s+(installing|upgrading|reinstalling|downgrading|removing)\s+(\S+)')
PERCENT = re.compile(r'(\d{1,3})%')


def clean(line):
    return ''.join(c for c in ANSI.sub('', line) if c.isprintable() or c == '\t').strip()


def progress(line, stage):
    line = clean(line)
    percent = PERCENT.search(line)
    package = PACKAGE.search(line)
    if package:
        index, total, action, name = package.groups()
        return min(int(percent[1]), 100) if percent else 0, f'{stage}\n{action.capitalize()} {name} ({index}/{total})'
    if percent:
        label = line.split('[', 1)[0].strip()
        return min(int(percent[1]), 100), f'{stage}\n{label[:160]}'
    return None, f'{stage}\n{line[:180]}' if line else stage


def frame(percent, message):
    # Never allow command output to terminate/inject the whiptail gauge protocol.
    message = '\n'.join(row for row in message.splitlines() if row.strip() != 'XXX')
    return f'XXX\n{max(0, min(percent, 100))}\n{message}\nXXX\n'.encode()


def run_command(command, stage, log_path, *, terminal=None, stdin=None, gauge_command=None):
    owned_terminal = terminal is None
    if terminal is None:
        terminal = open('/dev/tty', 'wb', buffering=0)
    gauge_command = gauge_command or ['whiptail', '--title', 'Porthpean installation', '--gauge', stage, '12', '78', '0']
    descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.fchmod(descriptor, 0o600)
    master, slave = os.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
    gauge = None
    child = None
    started = time.monotonic()
    percent = 0
    message = stage
    pending = ''
    last_update = 0.0
    last_frame = None
    last_package = None
    selector = selectors.DefaultSelector()

    def emit(done=False):
        nonlocal last_update, last_frame
        elapsed = int(time.monotonic() - started)
        value = 100 if done else percent
        text = (stage + '\nComplete' if done else message) + f'\nElapsed {elapsed // 60:02d}:{elapsed % 60:02d}'
        payload = frame(value, text)
        if payload != last_frame:
            try:
                gauge.stdin.write(payload)
                gauge.stdin.flush()
            except (BrokenPipeError, OSError):
                # Do not interrupt a package transaction because the display closed.
                pass
            last_frame = payload
        last_update = time.monotonic()

    def consume(line, log):
        nonlocal percent, message, last_package
        line = clean(line)
        if not line:
            return
        log.write(line + '\n')
        value, message = progress(line, stage)
        percent = 0 if value is None else value
        package = PACKAGE.search(line)
        if package and package.groups() != last_package:
            last_package = package.groups()
            emit()

    try:
        with os.fdopen(descriptor, 'a', encoding='utf-8', buffering=1) as log:
            log.write(f'\n=== {stage} ===\n')
            gauge = subprocess.Popen(gauge_command, stdin=subprocess.PIPE, stdout=terminal, stderr=terminal)
            env = dict(os.environ, LC_ALL='C', TERM='xterm', COLUMNS='100', LINES='30')
            # argv is passed directly, never converted into shell text.
            child = subprocess.Popen(command, stdin=stdin, stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)
            slave = -1
            selector.register(master, selectors.EVENT_READ)
            emit()
            eof = False
            while not eof:
                for key, _ in selector.select(timeout=0.2):
                    try:
                        data = os.read(key.fd, 65536)
                    except OSError as exc:
                        if exc.errno != errno.EIO:
                            raise
                        data = b''
                    if not data:
                        eof = True
                        break
                    pending += data.decode('utf-8', errors='replace').replace('\r', '\n')
                    while '\n' in pending:
                        line, pending = pending.split('\n', 1)
                        consume(line, log)
                        if time.monotonic() - last_update >= 0.08:
                            emit()
                if time.monotonic() - last_update >= 0.5:
                    emit()
            if pending:
                consume(pending, log)
            status = child.wait()
            log.write(f'=== Exit status: {status} ===\n')
            if status == 0:
                emit(done=True)
            return status if status >= 0 else 128 - status
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        if gauge is not None:
            try:
                gauge.stdin.close()
            except (BrokenPipeError, OSError):
                pass
            try:
                gauge.wait(timeout=3)
            except subprocess.TimeoutExpired:
                gauge.terminate()
                gauge.wait()
        selector.close()
        os.close(master)
        if slave >= 0:
            os.close(slave)
        if owned_terminal:
            terminal.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True)
    parser.add_argument('--log', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('command required')
    return run_command(command, args.stage, args.log)


if __name__ == '__main__':
    raise SystemExit(main())
PORTHPEAN_PROGRESS_PY
}

# Run outside arch-chroot: firmware variables must be written from the live host.
configure_boot_menu() {
  local disk=$1 esp=$2 root=$3 guid candidate type probe windows_guid='' records number
  guid=$(blkid -s PARTUUID -o value "$esp")
  [[ $guid =~ ^[0-9a-fA-F-]{36}$ ]] || fail 'Missing EFI partition GUID.'
  mkdir -p "$root/efi/EFI/refind"
  cp "$root/usr/share/refind/refind_x64.efi" "$root/efi/EFI/refind/refind_x64.efi"
  # Only inspect other EFI partitions, read-only; never copy or modify Windows files.
  probe=$(mktemp -d /run/porthpean-esp.XXXXXXXX)
  while read -r candidate type; do
    [[ $(printf '%s' "$type" | tr '[:upper:]' '[:lower:]') == c12a7328-f81f-11d2-ba4b-00a0c93ec93b && $candidate != "$esp" ]] || continue
    if mount -o ro,nosuid,nodev,noexec "$candidate" "$probe"; then
      if [[ -f $probe/EFI/Microsoft/Boot/bootmgfw.efi ]]; then
        [[ -z $windows_guid ]] || { umount "$probe"; fail 'Multiple Windows EFI partitions found; inspect before reboot.'; }
        windows_guid=$(blkid -s PARTUUID -o value "$candidate")
        [[ $windows_guid =~ ^[0-9a-fA-F-]{36}$ ]] || { umount "$probe"; fail 'Invalid Windows EFI partition GUID.'; }
      fi
      umount "$probe"
    else
      fail "Cannot inspect EFI partition $candidate; boot menu is incomplete."
    fi
  done < <(lsblk -rpn -o PATH,PARTTYPE)
  rmdir "$probe"
  cat > "$root/efi/EFI/refind/refind.conf" <<CONF
timeout 5
default_selection "Arch Linux LTS"
scanfor manual
textonly
menuentry "Arch Linux LTS" {
    volume $guid
    loader /EFI/Linux/arch-lts.efi
}
menuentry "Arch Linux" {
    volume $guid
    loader /EFI/Linux/arch-linux.efi
}
CONF
  if [[ -n $windows_guid ]]; then
    cat >> "$root/efi/EFI/refind/refind.conf" <<CONF
menuentry "Windows" {
    volume $windows_guid
    loader /EFI/Microsoft/Boot/bootmgfw.efi
}
CONF
  fi
  # Keep systemd-boot as a recovery loader; fallback boot uses the same main menu.
  cp "$root/efi/EFI/refind/refind_x64.efi" "$root/efi/EFI/BOOT/BOOTX64.EFI"
  cp "$root/efi/EFI/refind/refind.conf" "$root/efi/EFI/BOOT/refind.conf"
  efibootmgr --create --disk "$disk" --part 1 --label 'Arch Linux' \
    --loader '\EFI\refind\refind_x64.efi'
  records=$(efibootmgr -v)
  number=$(printf '%s\n' "$records" | awk -v guid="$guid" '
    tolower($0) ~ tolower(guid) && /\\EFI\\refind\\refind_x64.efi/ && /^Boot[0-9A-Fa-f]{4}\*/ {print substr($1,5,4); exit}')
  [[ -n $number ]] || fail 'No active firmware entry matches the new EFI partition and rEFInd loader.'
  [[ $(printf '%s\n' "$records" | sed -n 's/^BootOrder: //p' | cut -d, -f1) == "$number" ]] || fail 'Arch firmware entry is not first in BootOrder.'
  printf '%s\n' "$records"
}

main() {
trap 'status=$?; unset drive_pass; if [[ $status != 0 && -n ${install_log:-} ]] && command -v whiptail >/dev/null; then whiptail --title "Installation stopped - log" --scrolltext --textbox "$install_log" 22 78 >/dev/tty 2>&1 || true; fi' EXIT
trap 'printf "Stopped at line %s; target filesystems left in place.\n" "$LINENO" >>"${install_log:-/dev/stderr}"' ERR

# These checks run before any mutation, including prompts which could mislead on another OS.
[[ $EUID == 0 ]] || fail 'Run as root from the Arch USB.'
[[ -t 0 && -t 1 ]] || fail 'Download, inspect and run interactively; do not pipe into bash.'
[[ $(uname -m) == x86_64 && -f /etc/arch-release && -d /run/archiso ]] || fail 'Requires the Arch x86_64 live USB, not an installed OS or chroot.'
[[ -d /sys/firmware/efi/efivars ]] || fail 'Boot the USB in UEFI mode.'
for tool in lsblk findmnt cryptsetup sfdisk udevadm mount umount blkid btrfs mkfs.fat mkfs.btrfs pacstrap genfstab arch-chroot curl flock python3 efibootmgr; do
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
progress_dir=$(mktemp -d /run/porthpean-install.XXXXXXXX)
install_log="$progress_dir/install.log"
: > "$install_log"
progress_helper="$progress_dir/progress.py"
write_progress_helper
# Install only the dialog dependency into the disposable live USB if needed.
if ! command -v whiptail >/dev/null; then
  pacman -Sy --needed --noconfirm libnewt >> "$install_log" 2>&1
fi
if ! host=$(ui_input 'Hostname' 'Name this computer:' t480s); then cancel; fi
[[ ${#host} -le 63 && $host =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || fail 'Use a hostname of 1–63 lowercase letters/digits/hyphens, without leading/trailing hyphen.'
if ! disk_id=$(select_disk); then cancel; fi
disk=$(whole_disk "$disk_id")
plan_partial_cleanup "$disk" >> "$install_log" 2>&1
serial=$(lsblk -dnro SERIAL "$disk")
serial=${serial## }; serial=${serial%% }
[[ -n $serial ]] || fail 'No hardware serial reported. Resolve disk identity manually.'
[[ $(blockdev --getsize64 "$disk") -ge 34359738368 ]] || fail 'Target is smaller than 32 GiB.'
if ! drive_pass=$(ui_password 'Drive encryption passphrase'); then cancel; fi
if ! confirm_erase "$disk"; then cancel; fi
installation_started=true
# Recheck immediately before the first destructive operation.
[[ $(readlink -f -- "$disk_id") == "$disk" && $(lsblk -dnro SERIAL "$disk") == "$serial" ]] || fail 'Disk identity changed.'
clear_partial_install "$disk" >> "$install_log" 2>&1
run_progress "Creating disk partitions" sfdisk --lock --wipe always --wipe-partitions always "$disk" <<'LAYOUT'
label: gpt
size=2GiB, type=C12A7328-F81F-11D2-BA4B-00A0C93EC93B, name="ARCH_EFI"
type=0FC63DAF-8483-4772-8E79-3D69D8477DE4, name="ARCH_LUKS"
LAYOUT
udevadm settle
esp=$(lsblk -nrpo PATH,PARTN "$disk" | awk '$2 == 1 {print $1}')
crypt=$(lsblk -nrpo PATH,PARTN "$disk" | awk '$2 == 2 {print $1}')
[[ -b $esp && -b $crypt ]] || fail 'Could not identify the two new partitions.'
run_progress "Creating EFI filesystem" mkfs.fat -F 32 -n ARCH_EFI "$esp"
format_and_unlock "$crypt"
# System directories and package hooks need normal traversal permissions.
# The private progress directory/log already exist with restrictive permissions.
umask 022
run_progress "Creating encrypted Btrfs filesystem" mkfs.btrfs -L archroot /dev/mapper/cryptroot
mount /dev/mapper/cryptroot /mnt 2>> "$install_log"
for sub in @ @home @snapshots @log @pkg @tmp @state; do btrfs subvolume create "/mnt/$sub" >> "$install_log" 2>&1; done
umount /mnt 2>> "$install_log"
mount -o subvol=@,compress=zstd:3 /dev/mapper/cryptroot /mnt 2>> "$install_log"
for pair in '@home:home' '@snapshots:.snapshots' '@log:var/log' '@pkg:var/cache/pacman/pkg' '@tmp:var/tmp' '@state:srv/workstation-state'; do
  sub=${pair%%:*}; path=${pair#*:}
  mkdir -p "/mnt/$path"
  mount -o "subvol=$sub,compress=zstd:3" /dev/mapper/cryptroot "/mnt/$path" 2>> "$install_log"
done
# Btrfs subvolume defaults are not a substitute for explicit directory modes.
chmod 0755 /mnt /mnt/home /mnt/var /mnt/var/log /mnt/var/cache /mnt/var/cache/pacman /mnt/var/cache/pacman/pkg /mnt/srv
chmod 1777 /mnt/var/tmp
chmod 0700 /mnt/.snapshots /mnt/srv/workstation-state
mkdir -p /mnt/efi
mount -o umask=0077 "$esp" /mnt/efi 2>> "$install_log"

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
run_progress "Installing the Arch base" pacstrap -K /mnt base linux-lts linux linux-firmware intel-ucode \
  btrfs-progs cryptsetup dosfstools networkmanager git curl \
  neovim less libnewt python man-db man-pages mkinitcpio efibootmgr systemd-ukify refind
umask 077
# Verify the installed configuration directory is traversable by services.
[[ $(stat -c %a /mnt/etc) == 755 ]] || fail 'Expected /etc permissions 755 after base installation.'
[[ -e /mnt/etc/fstab ]] && cp -a /mnt/etc/fstab "/mnt/etc/fstab.before-porthpean.$(date +%s)"
genfstab -U /mnt > /mnt/etc/fstab
chmod 0644 /mnt/etc/fstab
luks_uuid=$(blkid -s UUID -o value "$crypt")
[[ $luks_uuid =~ ^[0-9a-fA-F-]{36}$ ]] || fail 'Missing/invalid LUKS UUID.'
run_progress "Configuring the system and generating boot images" arch-chroot /mnt /bin/bash -s -- "$host" "$luks_uuid" <<'CHROOT'
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
chmod 0700 /root
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
bootctl --esp-path=/efi --no-variables install
mkdir -p /efi/loader/entries
printf 'default lts.conf\ntimeout 5\neditor no\n' > /efi/loader/loader.conf
printf 'title Arch Linux LTS\nefi /EFI/Linux/arch-lts.efi\n' > /efi/loader/entries/lts.conf
printf 'title Arch Linux regular kernel\nefi /EFI/Linux/arch-linux.efi\n' > /efi/loader/entries/linux.conf
bootctl --no-pager --esp-path=/efi list
pacman -Q linux-lts linux intel-ucode
systemctl is-enabled NetworkManager
CHROOT
export -f configure_boot_menu fail
run_progress "Installing and verifying the boot menu" bash -euo pipefail -c 'configure_boot_menu "$@"' boot-menu "$disk" "$esp" /mnt
if ! set_target_password root; then cancel; fi
printf 'Completed %s\n' "$(date -Iseconds)" > /mnt/root/porthpean-base-complete
cp "$install_log" /mnt/root/porthpean-install.log
installation_started=false
if whiptail --title 'Base installation complete' --defaultno --yesno 'Base installed. After reboot, log in as root and run the workstation bootstrap.\n\nReboot now? Remove the USB when the computer restarts.' 12 76; then
  cd /
  umount -R /mnt 2>> "$install_log"
  cryptsetup close cryptroot
  reboot
fi

}
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
