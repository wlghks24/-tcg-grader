#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${HOME}/.local/state/tcg-grader/scheduled-update"
LOG_DIR="${STATE_DIR}/logs"
STATUS_FILE="${STATE_DIR}/status.env"
LOCK_DIR="${STATE_DIR}/lock"
BOOT_DIR="${HOME}/.termux/boot"
BOOT_FILE="${BOOT_DIR}/tcg-grader-scheduled-update.sh"
INTERVAL_HOURS="${TCG_UPDATE_INTERVAL_HOURS:-24}"

mkdir -p "$LOG_DIR"

now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
sha() { git -C "$ROOT" rev-parse "$1" 2>/dev/null || printf 'unknown'; }
write_status() {
  local result="$1" message="$2" local_sha="$3" remote_sha="$4"
  cat >"$STATUS_FILE" <<EOF
LAST_CHECK=$(now)
RESULT=$result
LOCAL_SHA=$local_sha
REMOTE_SHA=$remote_sha
MESSAGE=$message
EOF
}

acquire_lock() {
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM HUP
    return 0
  fi
  echo "[안내] 예약 업데이트가 이미 실행 중입니다."
  exit 0
}

run_update() {
  acquire_lock
  cd "$ROOT"
  local before remote log rc after
  before="$(sha HEAD)"
  log="${LOG_DIR}/update-$(date '+%Y%m%d-%H%M%S').log"
  echo "[$(now)] 예약 업데이트 확인 시작" | tee -a "$log"

  if ! git fetch --prune origin main >>"$log" 2>&1; then
    write_status "FETCH_FAILED" "원격 main 확인 실패; 현재 정상 버전 유지" "$before" "unknown"
    echo "[경고] 원격 확인 실패. 현재 버전을 유지합니다."
    return 1
  fi
  remote="$(sha origin/main)"
  if [ "$before" = "$remote" ]; then
    write_status "UP_TO_DATE" "이미 최신 main" "$before" "$remote"
    echo "[OK] 이미 최신 main입니다: ${before:0:12}"
    return 0
  fi

  echo "[안내] 새 main 감지: ${before:0:12} -> ${remote:0:12}" | tee -a "$log"
  set +e
  bash "$ROOT/ANDROID_UPDATE_AND_START.sh" >>"$log" 2>&1
  rc=$?
  set -e
  after="$(sha HEAD)"
  if [ "$rc" -eq 0 ] && [ "$after" = "$remote" ]; then
    write_status "UPDATED" "검증된 main 업데이트 및 시작 성공" "$after" "$remote"
    echo "[OK] 최신 검증본으로 업데이트했습니다: ${after:0:12}"
    return 0
  fi
  write_status "UPDATE_FAILED" "안전 업데이트 실패; 로그 확인 필요" "$after" "$remote"
  echo "[경고] 안전 업데이트가 완료되지 않았습니다. 로그: $log" >&2
  return "$rc"
}

install_schedule() {
  case "$INTERVAL_HOURS" in
    ''|*[!0-9]*) echo "[오류] TCG_UPDATE_INTERVAL_HOURS는 정수여야 합니다." >&2; exit 2 ;;
  esac
  if [ "$INTERVAL_HOURS" -lt 1 ] || [ "$INTERVAL_HOURS" -gt 168 ]; then
    echo "[오류] 예약 간격은 1~168시간만 허용합니다." >&2; exit 2
  fi
  mkdir -p "$BOOT_DIR"
  cat >"$BOOT_FILE" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -u
ROOT=$(printf '%q' "$ROOT")
INTERVAL=$INTERVAL_HOURS
sleep 30
while true; do
  bash "\$ROOT/TABLET_SCHEDULED_UPDATE.sh" run || true
  sleep "\$((INTERVAL*3600))"
done
EOF
  chmod 700 "$BOOT_FILE"
  echo "[OK] 태블릿 예약 업데이트 설치: 부팅 후 30초, 이후 ${INTERVAL_HOURS}시간마다 확인"
  echo "[안내] Termux:Boot이 설치/허용되어 있어야 부팅 시 자동 시작됩니다."
}

remove_schedule() {
  rm -f "$BOOT_FILE"
  echo "[OK] 태블릿 예약 업데이트를 제거했습니다."
}

show_status() {
  echo "현재 HEAD: $(sha HEAD)"
  if [ -f "$STATUS_FILE" ]; then
    cat "$STATUS_FILE"
  else
    echo "예약 업데이트 실행 기록이 없습니다."
  fi
  if [ -f "$BOOT_FILE" ]; then
    echo "SCHEDULE=installed (${INTERVAL_HOURS}h default/configured at install)"
  else
    echo "SCHEDULE=not-installed"
  fi
}

case "${1:-status}" in
  run|now) run_update ;;
  install) install_schedule ;;
  remove|uninstall) remove_schedule ;;
  status) show_status ;;
  *) echo "사용법: bash TABLET_SCHEDULED_UPDATE.sh [install|run|status|remove]" >&2; exit 2 ;;
esac
