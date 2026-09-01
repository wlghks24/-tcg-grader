#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

if [ ! -f "tcg_updater.py" ] || [ ! -f "index.html" ] || [ ! -f "START_TCG_UPDATER_ANDROID.sh" ] || [ ! -f "ANDROID_UPDATE_AND_START.sh" ]; then
  echo "[ERROR] Extract/pull the complete program before installing auto-start."
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
  printf 'cd %q\n' "$PROJECT_DIR"
  echo 'if [ ! -f ANDROID_UPDATE_AND_START.sh ]; then echo "[ERROR] ANDROID_UPDATE_AND_START.sh missing; auto-start stopped."; exit 1; fi'
  echo 'while true; do bash ANDROID_UPDATE_AND_START.sh >> TCG_ANDROID_STARTUP.log 2>&1; sleep 10; done'
} > "$BOOT_TEMP"
mv -f "$BOOT_TEMP" "$BOOT_FILE"
chmod +x "$BOOT_FILE"
chmod +x "$PROJECT_DIR/ANDROID_UPDATE_AND_START.sh" "$PROJECT_DIR/START_TCG_UPDATER_ANDROID.sh" 2>/dev/null || true

echo "[OK] Android boot auto-start installed (v176 safe update + singleton launcher)."
echo "Boot file: $BOOT_FILE"
echo "Log file: $PROJECT_DIR/TCG_ANDROID_STARTUP.log"
echo "At every reboot it checks origin/main and fast-forwards only when tracked files are clean."
echo "Local tracked edits are never reset or overwritten automatically."
echo "Install Termux:Boot from F-Droid and open it once."
