#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

for required in tcg_updater.py tcg_updater_v135.py index.html START_TCG_UPDATER_ANDROID.sh ANDROID_UPDATE_AND_START.sh VERIFY_TABLET_FINAL.sh tablet_runtime_probe.py; do
  if [ ! -s "$required" ]; then
    echo "[ERROR] Missing required runtime file: $required"
    echo "[ERROR] Extract/pull the complete program before installing auto-start."
    exit 1
  fi
done
if ! command -v python >/dev/null 2>&1; then
  echo "[ERROR] Python is missing. Run: pkg install python"
  exit 1
fi
python tablet_runtime_probe.py --self-test >/dev/null || {
  echo "[ERROR] tablet_runtime_probe.py self-test failed."
  exit 1
}

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
  echo 'for f in ANDROID_UPDATE_AND_START.sh tablet_runtime_probe.py; do [ -s "$f" ] || { echo "[ERROR] $f missing; auto-start stopped."; exit 1; }; done'
  echo 'LOG=TCG_ANDROID_STARTUP.log'
  echo 'STATE=unknown'
  echo 'stamp() { date "+%Y-%m-%dT%H:%M:%S%z" 2>/dev/null || date; }'
  echo "healthy() { python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen(\"http://127.0.0.1:8765/api/v135-health\",timeout=3)); raise SystemExit(0 if d.get(\"ok\") else 1)' >/dev/null 2>&1; }"
  echo 'diagnose() { printf "[%s] " "$(stamp)" >> "$LOG"; python tablet_runtime_probe.py >> "$LOG" 2>&1 || true; }'
  echo 'rotate_log() { if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt 2097152 ]; then mv -f "$LOG" "$LOG.1"; fi; }'
  echo 'delay=30'
  echo 'echo "[$(stamp)] Termux:Boot supervisor started." >> "$LOG"'
  echo 'diagnose'
  echo 'while true; do'
  echo '  rotate_log'
  echo '  if healthy; then'
  echo '    if [ "$STATE" != healthy ]; then echo "[$(stamp)] [OK] local /api/v135-health recovered." >> "$LOG"; diagnose; fi'
  echo '    STATE=healthy; delay=30; sleep 60; continue'
  echo '  fi'
  echo '  if [ "$STATE" != unhealthy ]; then echo "[$(stamp)] [WARN] local health failed; recovery starts." >> "$LOG"; diagnose; fi'
  echo '  STATE=unhealthy'
  echo '  bash ANDROID_UPDATE_AND_START.sh >> "$LOG" 2>&1'
  echo '  rc=$?'
  echo '  if healthy; then STATE=healthy; echo "[$(stamp)] [OK] recovery succeeded (rc=$rc)." >> "$LOG"; diagnose; delay=30; sleep 60; continue; fi'
  echo '  echo "[$(stamp)] [WARN] TCG server stopped or failed health check (rc=$rc); retrying in ${delay}s." >> "$LOG"'
  echo '  diagnose'
  echo '  sleep "$delay"'
  echo '  if [ "$delay" -lt 300 ]; then delay=$((delay*2)); [ "$delay" -gt 300 ] && delay=300; fi'
  echo 'done'
} > "$BOOT_TEMP"
mv -f "$BOOT_TEMP" "$BOOT_FILE"
chmod +x "$BOOT_FILE"
chmod +x "$PROJECT_DIR/ANDROID_UPDATE_AND_START.sh" "$PROJECT_DIR/START_TCG_UPDATER_ANDROID.sh" 2>/dev/null || true

echo "[OK] Android boot auto-start installed (health-supervised safe updater)."
echo "Boot file: $BOOT_FILE"
echo "Log file: $PROJECT_DIR/TCG_ANDROID_STARTUP.log"
echo "At reboot it checks origin/main before startup; while healthy it checks local /api/v135-health every 60 seconds."
echo "On state changes/failures it logs Git SHA, local health, LAN candidates and Tailscale candidate when available."
echo "Collector-written runtime JSON is preserved; code/config edits are never reset or overwritten automatically."
echo "Termux chmod-only permission changes are ignored by Git so they cannot block safe updates."
echo "Install Termux:Boot from F-Droid and open it once."
