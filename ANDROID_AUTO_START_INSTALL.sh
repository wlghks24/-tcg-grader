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

# Termux needs executable permission locally, but GitHub Contents API commonly
# materializes shell files as 100644. Do not let chmod-only mode changes appear
# as source-code edits and block later safe updates.
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git config --local core.fileMode false >/dev/null 2>&1 || true
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
  echo "healthy() { python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen(\"http://127.0.0.1:8765/api/v135-health\",timeout=3)); raise SystemExit(0 if d.get(\"ok\") else 1)' >/dev/null 2>&1; }"
  echo 'rotate_log() { if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt 2097152 ]; then mv -f "$LOG" "$LOG.1"; fi; }'
  echo 'delay=30'
  echo 'while true; do'
  echo '  rotate_log'
  echo '  if healthy; then delay=30; sleep 60; continue; fi'
  echo '  bash ANDROID_UPDATE_AND_START.sh >> "$LOG" 2>&1'
  echo '  rc=$?'
  echo '  if healthy; then delay=30; sleep 60; continue; fi'
  echo '  echo "[WARN] TCG server stopped or failed health check (rc=$rc); retrying in ${delay}s." >> "$LOG"'
  echo '  sleep "$delay"'
  echo '  if [ "$delay" -lt 300 ]; then delay=$((delay*2)); [ "$delay" -gt 300 ] && delay=300; fi'
  echo 'done'
} > "$BOOT_TEMP"
mv -f "$BOOT_TEMP" "$BOOT_FILE"
chmod +x "$BOOT_FILE"
chmod +x "$PROJECT_DIR/ANDROID_UPDATE_AND_START.sh" "$PROJECT_DIR/START_TCG_UPDATER_ANDROID.sh" 2>/dev/null || true

echo "[OK] Android boot auto-start installed (v183 health-supervised safe updater)."
echo "Boot file: $BOOT_FILE"
echo "Log file: $PROJECT_DIR/TCG_ANDROID_STARTUP.log"
echo "At reboot it checks origin/main before startup; while healthy it only checks local /api/v135-health every 60 seconds."
echo "Collector-written runtime JSON is preserved; code/config edits are never reset or overwritten automatically."
echo "Termux chmod-only permission changes are ignored by Git so they cannot block safe updates."
echo "Install Termux:Boot from F-Droid and open it once."
