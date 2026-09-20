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

if [ ! -s "tablet_gdrive_sync_perf_v262.py" ]; then
  echo "[HOLD] v262 Drive sync runtime이 없습니다. 최신 main으로 갱신하세요." >&2
  exit 2
fi

# v262 wraps the contextual + hardened sync stack. It only bounds manifest
# discovery/health checks/history retention; SHA-256, exact-17-output gates,
# inflight rollback, launcher-PID checks and receipt semantics remain unchanged.
python tablet_gdrive_sync_perf_v262.py "$@"
rc=$?
exit "$rc"
