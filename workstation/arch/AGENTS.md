# Workstation provisioning contract

- Maintain one normal workstation convergence path after base installation, for reruns and future updates. arch-install.sh remains a separate fresh-disk installer, never an update entry point.
- Declare desired accounts, permissions, packages and configuration. Package managers own package files and metadata.
- Keep umask and directory creation correct at their source. Do not add recursive permission repair or historical-install detection to normal provisioning.
- Explicit, repeat-safe recovery scripts belong under recovery/ and must never run automatically from bootstrap.
- Unchanged managed inputs must not regenerate boot images, replace working recovery images, create more backups or rewrite configuration.
- Package updates are deliberate. Install packages individually with --needed; run yay/builds as the daily user, never root. Preserve temporary sudo cleanup and isolated agent accounts.
- Validate meaningful second-run behaviour as well as first-run correctness. State clearly which checks were simulated and which require Arch hardware.
