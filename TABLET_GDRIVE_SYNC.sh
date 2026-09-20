#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
cd "${TCG_REPO_DIR:-$SCRIPT_DIR}" || exit 1

WAKE_LOCKED=0
cleanup_sync_wrapper() {
  if [ "${WAKE_LOCKED:-0}" = "1" ] && command -v termux-wake-unlock >/dev/null 2>&1; then
    termux-wake-unlock >/dev/null 2>&1 || true
  fi
  WAKE_LOCKED=0
}
trap cleanup_sync_wrapper EXIT INT TERM HUP

if command -v termux-wake-lock >/dev/null 2>&1; then
  if termux-wake-lock >/dev/null 2>&1; then
    WAKE_LOCKED=1
  fi
fi

if [ ! -s "tablet_gdrive_sync_hardening_contextual.py" ]; then
  echo "[HOLD] contextual Drive sync runtime이 없습니다. 최신 main으로 갱신하세요." >&2
  exit 2
fi

# tablet_gdrive_sync_hardening_contextual.py extends tablet_gdrive_sync_hardening.py;
# backup hashing, inflight recovery, launcher-PID checks and receipt semantics stay unchanged.
python tablet_gdrive_sync_hardening_contextual.py "$@"
rc=$?
exit "$rc"
