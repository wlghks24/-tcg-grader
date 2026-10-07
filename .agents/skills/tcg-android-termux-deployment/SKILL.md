---
name: tcg-android-termux-deployment
description: Safely install, update, verify, and recover the TCG Grader tablet runtime on Android and Termux without inventing device state or bypassing runtime guards.
version: "1.0.0"
---

# TCG Grader Android / Termux Deployment

Use this skill for Lenovo/Android tablet setup, Termux installation, boot startup, runtime updates, local server launch, storage permissions, and device-side verification.

## Deployment flow
1. Identify the exact target: Android version, Termux source/version, repository ref, runtime entrypoint, storage path, and whether Termux:Boot is installed.
2. Perform a read-only preflight before mutation: available storage, Python version, Git status, required commands, current commit, expected runtime manifest, and occupied ports.
3. Update only from a reviewed Git ref or verified package. Do not replace the runtime from arbitrary downloaded scripts or chat-generated shell.
4. Preserve local data/state before source replacement. Source truth and runtime state must remain separate.
5. Run repository-native checks after update: tablet runtime manifest, Python compile, Android/Termux guard, and the exact launch command.
6. Start the local server only after verification passes, then confirm the listening address and HTTP health endpoint from the device.
7. Reboot validation is separate evidence. Termux:Boot presence does not prove that startup succeeded after reboot.
8. If deployment fails, keep last-known-good files and report the exact failing command/error instead of destructive reset.

## Android safety
- Never claim APK/Termux installation or physical readback without device-side output.
- Do not request root for functions that work in normal Termux.
- Respect Android background, battery, storage, and network restrictions.
- Keep secrets out of shell history and screenshots.
- Use bounded process counts and tablet-friendly CPU/memory/storage budgets.
- Updates must remain rollback-capable and fail closed on incomplete integrity checks.
