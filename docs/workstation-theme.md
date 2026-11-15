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

Agent shortcuts ask for the root password through `su`, then drop privileges to the selected dedicated account and attach a tmux session. They do not grant the daily account sudo or share authentication files. If a CLI has not been installed, its terminal explains how to run `porthpean-install-agent` and authenticate inside that account. No background/public agent service is enabled.

## Citrix Workspace

`install-citrix` uses reviewed AUR revision `77eafb5fd43e2b377b2289864e5cc0298b9464f6`, version `26.04.10.1-1`. The recipe, desktop wrappers, install script, service definitions, dependency metadata and download checksums were inspected. It repackages Citrix binaries, sets CEIP/heartbeat off in its global configuration, and installs but does not enable the vendor service units. The installer does not install USB redirection or App Protection.

A locked, unprivileged `porthpean-build` account runs makepkg with no sudo or automatic dependency escalation. Root installs the reviewed dependencies and resulting package. The x86_64 source SHA-256 is `8c0a22cad4a4cda802cb5d3bb09b89779d20f68ba5e454b86485354c557356b5`.

Citrix returned HTTP 403 during download verification in this development environment. The installer first tries the recipe's vendor download. If blocked, its whiptail dialogs ask for a local Citrix Linux x86_64 version 26.04.10.1 tarball. It checks the same pinned SHA-256 before substituting a local source; checksums are never disabled. A different release needs a new packaging review. The official download page is [Citrix Workspace for Linux](https://www.citrix.com/downloads/workspace-app/linux/workspace-app-for-linux-latest.html).

Citrix is proprietary and is not officially supported on Arch/Wayland. The native ICA launcher forces X11 through Niri's xwayland-satellite. The standalone selfservice UI requires the removed WebKitGTK 4.0/libsoup 2 ABI. Rather than attempting obsolete-library builds, the launcher asks once for your HTTPS workplace portal, opens it in Firefox, and associates downloaded `.ica` files with the native client. The portal URL is saved privately under `~/.config/porthpean/citrix-portal`; no workplace address is committed. Arch's legacy WebKitGTK and libsoup package pages returned 404 during verification, so those packages are deliberately not dependencies. Test your organisation's authentication, certificate trust, ICA launch, clipboard and display scaling. No workplace address, credentials or certificate trust bypass is included. See [Citrix system requirements](https://docs.citrix.com/us/en/citrix-workspace-app-for-linux/system-requirements.html).

## Boot update safety and recovery

`setup-appearance` runs only on installed Arch, requires a mounted Linux ESP and existing installer configuration, checks free space, and refuses to rebuild unsigned UKIs with Secure Boot enabled. It backs up the kernel command line, initramfs configuration, Plymouth selection, boot menu and both UKIs under `/root/porthpean-boot-backup.*`. It preserves cryptroot identifiers and puts Plymouth before sd-encrypt. Errors restore the prior boot configuration and images; no firmware entries or Windows files are changed here.

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
