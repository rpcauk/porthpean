# T480s appearance and applications

This is workstation infrastructure, separate from the Porthpean application. Apply it by rerunning the installed-system `install.sh` as root. Never rerun the disk-erasing `arch-install.sh` to change appearance.

## Design

The desktop uses the VS Code Dark+ palette: background `#1e1e1e`, panels/fields `#252526`, text `#d4d4d4`, border `#3c3c3c`, focus `#007acc`, selection `#094771`. Foot includes the VS Code terminal ANSI palette. GTK 3/4 applications receive matching surfaces and a dark preference; applications that draw their own interfaces can require their own theme settings.

The supplied JPEG is copied unchanged to `/usr/share/backgrounds/porthpean/diogenes.jpg`; swaybg fills the desktop with it. Hyprlock blurs and darkens that file at runtime. The boot menu, graphical drive unlock and ReGreet login instead use a plain dark background and square text fields. They share colours and visual language, but are distinct programs: rEFInd, Plymouth and greetd/ReGreet respectively. rEFInd's selectable entries are rendered as text-box images rather than OS logos. The menu defaults to Arch LTS after five seconds, retains Windows, and adds an Arch LTS recovery image.

The old [arch-dotfiles](https://github.com/rpcauk/arch-dotfiles) informed the bottom bar, compact typography, square geometry, keyboard controls and lock-screen layout. Its old Nord palette, obsolete Hyprland settings, personal credentials and old Citrix connection configuration are not imported.

Waybar has numbered workspaces on the left; network, audio, battery and clock on the right. No status glyphs or icon font is required. Fuzzel appears immediately above the bottom bar, with plain text results, a square border and blue selection. The lock screen shows the current user, password field, time/date, selected MPRIS source and Playing/Paused/Stopped state. It does not expose track titles or permit unauthenticated desktop access.

## Shortcuts

Mod means the Windows/Super key.

| Shortcut | Opens |
| --- | --- |
| Mod+Return | Foot terminal |
| Mod+Space or Mod+D | Application launcher |
| Mod+B | Firefox |
| Mod+E | Thunderbird |
| Mod+G | ChatGPT in Firefox |
| Mod+C | Dedicated Codex account terminal |
| Mod+A | Dedicated Amp account terminal |
| Mod+Shift+C | Codex web |
| Mod+Shift+A | Amp website |
| Mod+W | Workplace Citrix portal in Firefox; downloaded ICA sessions open the native client through XWayland |
| Mod+Shift+L | Lock session |
| Media keys | Playback and volume |

Agent shortcuts ask for the root password through `su`, then drop privileges to the selected dedicated account and attach a tmux session. They keep authentication files separate. Daily package/power sudo permissions are managed independently below. If a CLI has not been installed, its terminal explains how to run `porthpean-install-agent` and authenticate inside that account. No background/public agent service is enabled.

## Citrix Workspace

`install-citrix` uses reviewed AUR revision `77eafb5fd43e2b377b2289864e5cc0298b9464f6`, version `26.04.10.1-1`. The recipe, desktop wrappers, install script, service definitions, dependency metadata and download checksums were inspected. It repackages Citrix binaries, sets CEIP/heartbeat off in its global configuration, and installs but does not enable the vendor service units. The installer does not install USB redirection or App Protection.

`yay` runs as the daily account, retrieving the recipe with `yay -G` and building/installing the corrected local recipe with `yay -Bi`. Official dependencies remain individual pacman transactions. Sudo permits the package installation; no AUR build runs as root. The x86_64 source SHA-256 is `8c0a22cad4a4cda802cb5d3bb09b89779d20f68ba5e454b86485354c557356b5`.

Citrix returned HTTP 403 during download verification in this development environment. The installer first tries the recipe's vendor download. If blocked, its terminal prompts ask for a local Citrix Linux x86_64 version 26.04.10.1 tarball. It checks the same pinned SHA-256 before substituting a local source; checksums are never disabled. A different release needs a new packaging review. The official download page is [Citrix Workspace for Linux](https://www.citrix.com/downloads/workspace-app/linux/workspace-app-for-linux-latest.html).

Citrix is proprietary and is not officially supported on Arch/Wayland. The native ICA launcher forces X11 through Niri's xwayland-satellite. The standalone selfservice UI requires the removed WebKitGTK 4.0/libsoup 2 ABI. Rather than attempting obsolete-library builds, the launcher asks once for your HTTPS workplace portal, opens it in Firefox, and associates downloaded `.ica` files with the native client. The portal URL is saved privately under `~/.config/porthpean/citrix-portal`; no workplace address is committed. Arch's legacy WebKitGTK and libsoup package pages returned 404 during verification, so those packages are deliberately not dependencies. Test your organisation's authentication, certificate trust, ICA launch, clipboard and display scaling. No workplace address, credentials or certificate trust bypass is included. See [Citrix system requirements](https://docs.citrix.com/us/en/citrix-workspace-app-for-linux/system-requirements.html).

## Boot update safety and recovery

`setup-appearance` runs only on installed Arch, requires a mounted Linux ESP and existing installer configuration, compares managed inputs before making changes, checks free space for needed kernel rebuilds, and refuses to rebuild unsigned UKIs with Secure Boot enabled. An unchanged rerun does nothing: no backups, image copies or rebuilds. Menu-only changes do not rebuild kernel images or replace recovery images. For real changes it backs up affected configuration and, when rebuilding, both UKIs under `/root/porthpean-boot-backup.*`. It preserves cryptroot identifiers and puts Plymouth before sd-encrypt. Errors restore the prior boot configuration and images; no firmware entries or Windows files are changed here.

An extra `/efi/EFI/Linux/arch-lts-recovery.efi` retains the image from immediately before the appearance update. Select **Arch LTS recovery** if the new graphical unlock screen fails. Escape in Plymouth exposes diagnostic text. Root can restore a chosen backup, replacing BACKUP with the printed directory:

```sh
cp BACKUP/mkinitcpio.conf /etc/mkinitcpio.conf
cp BACKUP/cmdline /etc/kernel/cmdline
cp BACKUP/arch-lts.efi /efi/EFI/Linux/arch-lts.efi
cp BACKUP/arch-linux.efi /efi/EFI/Linux/arch-linux.efi
cp BACKUP/refind.conf /efi/EFI/refind/refind.conf
cp BACKUP/refind.conf /efi/EFI/BOOT/refind.conf
```

If present, also restore `BACKUP/plymouthd.conf` to `/etc/plymouth/plymouthd.conf`. The backup contains boot configuration, not passwords. Keep the Arch USB for independent recovery.

## Validation before relying on it

Run `workstation/arch/check` as root, then log out/reboot deliberately. Verify both boot choices, drive unlock with a mistyped passphrase then a correct one, graphical login with the daily account, wallpaper/bar/launcher placement, and lock/unlock before testing suspend. Confirm the bar and launcher on an external screen too. Check that agent shortcuts run as their dedicated users and that Citrix works against your workplace.

Local automated checks cover configuration parsing, boot transformations/idempotence, preservation of encryption options and Windows menu entries, deterministic boot assets, package flow, permissions and shell/Ansible syntax. Niri/GTK rendering, Plymouth, firmware, suspend and Citrix connectivity require testing on the ThinkPad; they have not been exercised by the development machine.

## Zsh, tmux and history

The managed daily and agent accounts now use `/bin/zsh`. The shell files adapt Ryan's current Zsh/tmux setup: XDG directories, completion, Git aliases, Ctrl+Space tmux prefix, vi-style pane movement and resize bindings. macOS/Homebrew settings and personal cloud paths are omitted. Existing configuration files are backed up by Ansible before replacement. Root administration continues through the existing root login.

The prompt contains the directory, Git branch and `$` only. The dollar sign is white after success and red after failure. Fast Syntax Highlighting is installed through yay as AUR package `zsh-fast-syntax-highlighting`; its caches are private to the current account. It performs no first-run theme download. fzf uses the Dark+ palette.

Interactive terminals attach to tmux session `home`, as in the existing config. Ctrl+Space followed by `c` creates another shell/window; pane splits also create independent shells. Up/Down recall only commands entered in that shell. **Alt+R** searches that shell's history with fzf. **Ctrl+R** searches all recorded shells for the same account, including closed shells, newest first. Selecting a command puts it into the editing buffer; Enter executes it. History from different Unix accounts is never combined.

Each shell gets its own mode-0600 native history file in a private temporary directory, removed on normal exit. The shell configuration itself remains shared. A locked, mode-0600 JSON-lines journal under `~/.local/state/zsh/history.jsonl` stores shared history without importing other shells' commands into arrow-key recall. Concurrent writes, Unicode and multiline commands are supported. A leading space excludes a command from both histories. Existing personal history and credentials are not copied. A forcibly killed shell can leave a private temporary directory for the OS's normal temporary-file cleanup.

`~/.local/bin/pyre` retains the existing symlink dispatch convention: place `example.py` in `~/.local/bin/lib/` and create `example -> pyre` beside the launcher. A shared `lib/requirements.txt` is optional. Pyre creates a private per-account environment under `~/.cache/pyre/`, locks setup against concurrent invocations and installs requirements only when their checksum changes. It does not reuse the old cross-account `/var/tmp/pyre/venv`. No old script collection is imported.

## Pinned Zoom Citrix plugin

Bootstrap installs **6.4.11 (26350)** after Citrix Workspace in a separate progress stage. The local packaging recipe uses the same official CentOS RPM and SHA-512 as `rpcauk/zoom-citrix-plugin-ms` revision `73c36ac492e93a521f54f3ebfb03adcf965cd2a8`. The downloaded RPM was independently checked against that checksum and its embedded version inspected. Zoom lists this version on its [official VDI downloads page](https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0063810).

`yay -Bi` runs the pinned local recipe as the daily account. Pacman tracks the resulting `zoom-citrix-plugin-ms` package; the vendor RPM's install scripts are not run. Ansible (`zoom.yml`) configures the `ZoomMedia` virtual channel and symlink, preserves other channels and comments, backs up changed `module.ini` files, and validates the exact version and native library dependencies. This integration runs again even when the package is already installed, so a Citrix upgrade can be repaired by rerunning provisioning. The release stays pinned until deliberately changed.

The vendor's broad HID access rule and management-tool autostart are omitted; meeting audio/video works through the existing user session's device access. Special headset button integration may need separate configuration. After updating, close existing Citrix sessions and reconnect. The plugin and the remote workplace's VDI client must be tested together on the ThinkPad; local tests cannot verify optimization inside that remote session. This exact Zoom version is retained for the requested workplace compatibility rather than silently replaced by a newer release.


### Citrix download investigation (15 November 2026)

The AUR `icaclient` master branch was checked directly and still pointed to the reviewed revision `77eafb5fd43e2b377b2289864e5cc0298b9464f6`; switching to yay therefore does not select a newer recipe at this point. Its version is `26.04.10.1`, but its scraper uses Citrix's moving latest-release page. That page now advertises 2608, released 30 October 2026. Citrix's [2604.10 archive page](https://www.citrix.com/downloads/workspace-app/legacy-workspace-app-for-linux/workspace-app-for-linux-2604-10.html) still lists the exact pinned x86_64 tarball checksum. This is a reproducible version/page mismatch in the upstream recipe.

The installer now narrowly patches the reviewed recipe to that version-specific page, preserving all pinned checksums. HTTP errors are retained in the log and stop recipe loading; a missing matching download link has its own explicit error. The fallback prompt no longer asserts that every source failure is a Citrix block and directs browser downloads to the correct archive release. Both latest and archive page requests also returned HTTP 403 from Akamai on the development connection, so automatic downloading cannot be claimed to work everywhere. These responses do not establish the exact error seen on the ThinkPad; its private install log remains the evidence for that machine. No checksum is disabled and no newer binary is silently substituted.


## Daily sudo and yay

The installer now bootstraps `yay` from the reviewed AUR helper recipe (revision `a856562dc26bb1ea060e167983cd22ca6bcac9ec`, yay 13.1.0-1), compiling it as the daily user and installing that first package as root. Subsequent AUR installations use yay as the daily user: `yay -S` for ordinary packages, `yay -G` plus `yay -Bi` for Citrix's corrected reviewed recipe, and `yay -Bi` for the exact Zoom version. Normal setup contains no special handling for earlier unmanaged highlighting checkouts. An existing file-ownership conflict requires the explicit [early-install recovery](../workstation/arch/recovery/README.md) before package installation. Existing dedicated build accounts and old build caches are not deleted.

`/etc/sudoers.d/20-porthpean-daily` grants the selected daily account password-authenticated root execution of `/usr/bin/pacman`, `shutdown`, no-argument `reboot`/`poweroff`/`halt`, and the exact `systemctl reboot`, `poweroff`, `halt` and `suspend` commands. No wheel membership is required. Run `yay -S package` normally, not `sudo yay`; yay calls sudo pacman when needed. Package-management access is administrator-equivalent power, so this allowlist is not a containment boundary for the main account. The isolated agent accounts receive no such permission.

During each automated AUR stage, a serialized temporary rule permits only passwordless pacman for the selected daily user, with noninteractive sudo validation. It is removed on success, failure or a handled interrupt; boot-time tmpfiles cleanup removes a grant left by a forced kill or power loss. The installer does not save the daily password or feed it into yay's logs. Normal usage after setup requires the daily account's password. `check` validates sudo syntax, effective daily package/power permissions, missing agent package permissions and absence of the temporary rule.


### ALPM database permissions and earlier installs

Normal provisioning manages known directory modes and uses umask 022 for system/package creation. Package metadata belongs to pacman: the normal installer checks that the daily user can query local and sync databases, but never recursively changes their contents. The optional [early-install recovery](../workstation/arch/recovery/README.md) repairs metadata modes and the previous unmanaged highlighting layout on affected machines. It is never called automatically during install or update.
