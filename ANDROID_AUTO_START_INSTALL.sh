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
  echo 'LOG=TCG_ANDROID_STARTUP.log'
  echo 'if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt 2097152 ]; then mv -f "$LOG" "$LOG.1"; fi'
  echo 'delay=30'
  echo 'while true; do'
  echo '  bash ANDROID_UPDATE_AND_START.sh >> "$LOG" 2>&1'
  echo '  rc=$?'
  echo "  if pgrep -f '[p]ython.*tcg_updater_v135.py' >/dev/null 2>&1; then exit 0; fi"
  echo '  echo "[WARN] TCG server stopped (rc=$rc); retrying in ${delay}s." >> "$LOG"'
  echo '  sleep "$delay"'
  echo '  if [ "$delay" -lt 300 ]; then delay=$((delay*2)); [ "$delay" -gt 300 ] && delay=300; fi'
  echo 'done'
} > "$BOOT_TEMP"
mv -f "$BOOT_TEMP" "$BOOT_FILE"
chmod +x "$BOOT_FILE"
chmod +x "$PROJECT_DIR/ANDROID_UPDATE_AND_START.sh" "$PROJECT_DIR/START_TCG_UPDATER_ANDROID.sh" 2>/dev/null || true

echo "[OK] Android boot auto-start installed (v181 safe update + singleton supervisor)."
echo "Boot file: $BOOT_FILE"
echo "Log file: $PROJECT_DIR/TCG_ANDROID_STARTUP.log"
echo "At every reboot it checks origin/main and fast-forwards only when tracked files are clean."
echo "Local tracked edits are never reset or overwritten automatically."
echo "Install Termux:Boot from F-Droid and open it once."
