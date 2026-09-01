#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

if [ ! -f "tcg_updater.py" ] || [ ! -f "index.html" ] || [ ! -f "START_TCG_UPDATER_ANDROID.sh" ]; then
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
  printf 'cd %q\n' "$PROJECT_DIR"
  echo 'if [ ! -f START_TCG_UPDATER_ANDROID.sh ]; then echo "[ERROR] START_TCG_UPDATER_ANDROID.sh missing; auto-start stopped."; exit 1; fi'
  echo 'while true; do bash START_TCG_UPDATER_ANDROID.sh >> TCG_ANDROID_STARTUP.log 2>&1; sleep 10; done'
} > "$BOOT_TEMP"
mv -f "$BOOT_TEMP" "$BOOT_FILE"
chmod +x "$BOOT_FILE"

echo "[OK] Android boot auto-start installed (v167 singleton launcher)."
echo "Boot file: $BOOT_FILE"
echo "Log file: $PROJECT_DIR/TCG_ANDROID_STARTUP.log"
echo "Install Termux:Boot from F-Droid and open it once."
