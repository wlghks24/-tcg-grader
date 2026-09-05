#!/data/data/com.termux/files/usr/bin/bash
set -eu
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
cd "$SCRIPT_DIR"

for required in tablet_runtime_probe.py tcg_updater_v135.py ANDROID_UPDATE_AND_START.sh START_TCG_UPDATER_ANDROID.sh; do
  [ -s "$required" ] || { echo "[ERROR] missing runtime file: $required"; exit 10; }
done
command -v python >/dev/null 2>&1 || { echo "[ERROR] python missing"; exit 11; }
python tablet_runtime_probe.py --self-test >/dev/null

REPORT="TCG_TABLET_RUNTIME_REPORT.json"
TMP="${REPORT}.tmp.$$"
python tablet_runtime_probe.py --require-health > "$TMP" || {
  rc=$?
  cat "$TMP" 2>/dev/null || true
  rm -f "$TMP" 2>/dev/null || true
  echo "[ERROR] local /api/v135-health is not healthy."
  echo "[FIX] bash ANDROID_UPDATE_AND_START.sh"
  exit "$rc"
}
mv -f "$TMP" "$REPORT"
cat "$REPORT"

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  local_head="$(git rev-parse HEAD)"
  if git rev-parse origin/main >/dev/null 2>&1; then
    remote_head="$(git rev-parse origin/main)"
    if [ "$local_head" != "$remote_head" ]; then
      echo "[ERROR] tablet HEAD differs from origin/main."
      exit 20
    fi
  fi
fi

BOOT_FILE="$HOME/.termux/boot/TCG_AUTO_START.sh"
if [ -f "$BOOT_FILE" ]; then
  grep -Fq 'api/v135-health' "$BOOT_FILE" || { echo "[ERROR] boot supervisor uses obsolete health route."; exit 21; }
  grep -Fq 'tablet_runtime_probe.py' "$BOOT_FILE" || { echo "[ERROR] boot supervisor lacks runtime diagnostics."; exit 22; }
  echo "[OK] Termux:Boot supervisor contract verified."
else
  echo "[WARN] Termux:Boot supervisor is not installed. Run: bash ANDROID_AUTO_START_INSTALL.sh"
fi

echo "[OK] Tablet local runtime verified."
echo "[INFO] Test one access_candidates URL from iPhone/PC on the same network or via Tailscale."
