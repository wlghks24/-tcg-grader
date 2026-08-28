#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

if [ ! -f "tcg_updater.py" ] || [ ! -f "index.html" ]; then
  echo "[ERROR] Extract the complete program before installing auto-start."
  exit 1
fi
if ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] Python is missing. Run: pkg install python"
  exit 1
fi

PROJECT_DIR="$(pwd)"
BOOT_DIR="$HOME/.termux/boot"
BOOT_FILE="$BOOT_DIR/TCG_AUTO_START.sh"
BOOT_TEMP="$BOOT_FILE.tmp"
umask 077
mkdir -p "$BOOT_DIR"

{
  echo '#!/data/data/com.termux/files/usr/bin/bash'
  echo 'set -u'
  echo 'termux-wake-lock >/dev/null 2>&1 || true'
  printf 'cd %q\n' "$PROJECT_DIR"
  echo 'if ! command -v python >/dev/null 2>&1; then echo "[ERROR] Python missing; auto-start stopped."; exit 1; fi'
  echo 'if [ ! -f tcg_updater.py ] || [ ! -f index.html ]; then echo "[ERROR] Program files missing; auto-start stopped."; exit 1; fi'
  printf 'while true; do python tcg_updater.py >> %q 2>&1; sleep 10; done\n' "$PROJECT_DIR/TCG_ANDROID_STARTUP.log"
} > "$BOOT_TEMP"
mv -f "$BOOT_TEMP" "$BOOT_FILE"
chmod +x "$BOOT_FILE"

echo "[OK] Android boot auto-start installed."
echo "Boot file: $BOOT_FILE"
echo "Log file: $PROJECT_DIR/TCG_ANDROID_STARTUP.log"
echo "Install Termux:Boot from F-Droid and open it once."
