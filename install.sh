#!/usr/bin/env bash
# Download this file, read it, then run with sudo from the installed Arch base.
set -euo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo after reviewing this file.' >&2; exit 1; }
[[ -t 0 && -t 1 ]] || { echo 'Download and run interactively; do not pipe curl into a shell.'; exit 1; }
source /etc/os-release
[[ $ID == arch && $(uname -m) == x86_64 ]] || { echo 'Requires installed Arch Linux x86_64.'; exit 1; }
getent passwd admin >/dev/null || { echo 'Create admin first using the base install guide.'; exit 1; }
command -v git >/dev/null || { echo 'Install git as part of the base install first.'; exit 1; }
repo=https://github.com/rpcauk/porthpean.git
checkout=$(mktemp -d /root/porthpean-install.XXXXXXXX)
git clone --depth 1 --branch main -- "$repo" "$checkout/repo"
revision=$(git -C "$checkout/repo" rev-parse HEAD)
printf 'Source: %s\nRevision: %s\nLocal review copy: %s/repo\n' "$repo" "$revision" "$checkout"
echo 'Review workstation/arch/bootstrap, site.yml and files before executing.'
echo 'This tracks mutable main, not a signed release. Record/independently verify the revision.'
read -r -p 'Type REVIEWED after reviewing the local checkout (another console is available): ' answer
[[ $answer == REVIEWED ]] || exit 1
exec bash "$checkout/repo/workstation/arch/bootstrap"
