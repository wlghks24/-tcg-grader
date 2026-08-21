#!/data/data/com.termux/files/usr/bin/bash
set -eu
BOOT_FILE="$HOME/.termux/boot/TCG_AUTO_START.sh"
if [ -f "$BOOT_FILE" ]; then
  rm "$BOOT_FILE"
fi
echo "[OK] Android TCG boot auto-start removed."
