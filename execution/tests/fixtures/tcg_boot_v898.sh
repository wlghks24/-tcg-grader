#!/data/data/com.termux/files/usr/bin/bash
set -u
cd /data/data/com.termux/files/home/-tcg-grader
for f in ANDROID_UPDATE_AND_START.sh tablet_runtime_probe.py; do [ -s "$f" ] || { echo "[ERROR] $f missing; auto-start stopped."; exit 1; }; done
LOG=TCG_ANDROID_STARTUP.log
STATE=unknown
stamp() { date "+%Y-%m-%dT%H:%M:%S%z" 2>/dev/null || date; }
healthy() { python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen("http://127.0.0.1:8765/api/v135-health",timeout=3)); raise SystemExit(0 if d.get("ok") else 1)' >/dev/null 2>&1; }
diagnose() { printf "[%s] " "$(stamp)" >> "$LOG"; python tablet_runtime_probe.py >> "$LOG" 2>&1 || true; }
rotate_log() { if [ -f "$LOG" ] && [ "$(wc -c < "$LOG" 2>/dev/null || echo 0)" -gt 2097152 ]; then mv -f "$LOG" "$LOG.1"; fi; }
delay=30
echo "[$(stamp)] Termux:Boot supervisor started." >> "$LOG"
diagnose
while true; do
  rotate_log
  if healthy; then
    if [ "$STATE" != healthy ]; then echo "[$(stamp)] [OK] local /api/v135-health recovered." >> "$LOG"; diagnose; fi
    STATE=healthy; delay=30; sleep 60; continue
  fi
  if [ "$STATE" != unhealthy ]; then echo "[$(stamp)] [WARN] local health failed; recovery starts." >> "$LOG"; diagnose; fi
  STATE=unhealthy
  bash ANDROID_UPDATE_AND_START.sh >> "$LOG" 2>&1
  rc=$?
  if healthy; then STATE=healthy; echo "[$(stamp)] [OK] recovery succeeded (rc=$rc)." >> "$LOG"; diagnose; delay=30; sleep 60; continue; fi
  echo "[$(stamp)] [WARN] TCG server stopped or failed health check (rc=$rc); retrying in ${delay}s." >> "$LOG"
  diagnose
  sleep "$delay"
  if [ "$delay" -lt 300 ]; then delay=$((delay*2)); [ "$delay" -gt 300 ] && delay=300; fi
done
