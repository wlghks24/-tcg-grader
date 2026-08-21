#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

PROJECT_DIR="$(pwd)"
BOOT_DIR="$HOME/.termux/boot"
BOOT_FILE="$BOOT_DIR/TCG_AUTO_START.sh"
mkdir -p "$BOOT_DIR"

{
  echo '#!/data/data/com.termux/files/usr/bin/bash'
  echo 'termux-wake-lock >/dev/null 2>&1 || true'
  printf 'cd %q\n' "$PROJECT_DIR"
  printf 'python tcg_updater.py >> %q 2>&1\n' "$PROJECT_DIR/TCG_ANDROID_STARTUP.log"
} > "$BOOT_FILE"
chmod +x "$BOOT_FILE"

echo "[OK] Android boot auto-start installed."
echo "Boot file: $BOOT_FILE"
echo "Log file: $PROJECT_DIR/TCG_ANDROID_STARTUP.log"
echo "Install Termux:Boot from F-Droid and open it once."
