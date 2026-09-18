#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${HOME}/.local/state/tcg-grader/scheduled-update"
LOG_DIR="${STATE_DIR}/logs"
STATUS_FILE="${STATE_DIR}/status.env"
LOCK_DIR="${STATE_DIR}/lock"
LOCK_PID="${LOCK_DIR}/pid"
BOOT_DIR="${HOME}/.termux/boot"
BOOT_FILE="${BOOT_DIR}/tcg-grader-scheduled-update.sh"
INTERVAL_HOURS="${TCG_UPDATE_INTERVAL_HOURS:-24}"
OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"

mkdir -p "$LOG_DIR"

now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
sha() { git -C "$ROOT" rev-parse "$1" 2>/dev/null || printf 'unknown'; }

write_status() {
  local result="$1" message="$2" local_sha="$3" remote_sha="$4" tmp
  tmp="${STATUS_FILE}.tmp.$$"
  cat >"$tmp" <<EOF
LAST_CHECK=$(now)
RESULT=$result
LOCAL_SHA=$local_sha
REMOTE_SHA=$remote_sha
MESSAGE=$message
EOF
  mv "$tmp" "$STATUS_FILE"
}

cleanup_lock() {
  rm -f "$LOCK_PID" 2>/dev/null || true
  rmdir "$LOCK_DIR" 2>/dev/null || true
}

acquire_lock() {
  local owner=""
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" >"$LOCK_PID"
    trap cleanup_lock EXIT INT TERM HUP
    return 0
  fi
  if [ -r "$LOCK_PID" ]; then
    owner="$(cat "$LOCK_PID" 2>/dev/null || true)"
  fi
  case "$owner" in
    ''|*[!0-9]*) owner="" ;;
  esac
  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    echo "[안내] 예약 업데이트가 이미 실행 중입니다(PID $owner)."
    exit 0
  fi
  rm -f "$LOCK_PID" 2>/dev/null || true
  if ! rmdir "$LOCK_DIR" 2>/dev/null; then
    echo "[오류] 오래된 예약 업데이트 잠금을 안전하게 복구하지 못했습니다." >&2
    exit 3
  fi
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[오류] 예약 업데이트 잠금을 만들 수 없습니다." >&2
    exit 3
  fi
  printf '%s\n' "$$" >"$LOCK_PID"
  trap cleanup_lock EXIT INT TERM HUP
}

run_update() {
  acquire_lock
  cd "$ROOT"
  local before remote_before remote_after log rc after
  before="$(sha HEAD)"
  log="${LOG_DIR}/update-$(date '+%Y%m%d-%H%M%S').log"
  echo "[$(now)] 예약 업데이트 확인 시작" | tee -a "$log"

  # A raw-URL fetch plus --prune can delete refs/remotes/origin/main itself.
  # Fetch only the explicit canonical main ref so a prior deleted ref is rebuilt.
  if ! git fetch "$OFFICIAL_HTTPS" refs/heads/main:refs/remotes/origin/main >>"$log" 2>&1; then
    write_status "FETCH_FAILED" "공식 main 확인 실패; 현재 정상 버전 유지" "$before" "unknown"
    echo "[경고] 공식 main 확인 실패. 현재 버전을 유지합니다."
    return 1
  fi

  remote_before="$(sha origin/main)"
  if [ "$before" = "$remote_before" ]; then
    write_status "UP_TO_DATE" "이미 최신 main" "$before" "$remote_before"
    echo "[OK] 이미 최신 main입니다: ${before:0:12}"
    return 0
  fi

  echo "[안내] 새 main 감지: ${before:0:12} -> ${remote_before:0:12}" | tee -a "$log"
  set +e
  TCG_UPDATE_ONLY=1 bash "$ROOT/ANDROID_UPDATE_AND_START.sh" >>"$log" 2>&1
  rc=$?
  set -e

  after="$(sha HEAD)"
  remote_after="$(sha origin/main)"

  if [ "$rc" -eq 0 ] && [ "$after" = "$remote_after" ]; then
    if [ "$remote_before" != "$remote_after" ]; then
      write_status "UPDATED" "업데이트 중 main 전진 감지; 최종 검증본까지 반영" "$after" "$remote_after"
    else
      write_status "UPDATED" "검증된 main 코드 업데이트 성공; 실행 중 서버는 다음 재시작부터 새 코드 사용" "$after" "$remote_after"
    fi
    echo "[OK] 최신 검증본으로 업데이트했습니다: ${after:0:12}"
    return 0
  fi

  if [ "$rc" -eq 0 ]; then
    write_status "POSTCHECK_MISMATCH" "업데이터 종료 후 HEAD와 검증된 origin/main 불일치" "$after" "$remote_after"
    echo "[경고] 업데이트 후 일치 검증 실패. 로그: $log" >&2
    return 4
  fi

  write_status "UPDATE_FAILED" "안전 업데이트 실패; 현재 상태와 로그 확인 필요" "$after" "$remote_after"
  echo "[경고] 안전 업데이트가 완료되지 않았습니다. 로그: $log" >&2
  return "$rc"
}

install_schedule() {
  case "$INTERVAL_HOURS" in
    ''|*[!0-9]*) echo "[오류] TCG_UPDATE_INTERVAL_HOURS는 정수여야 합니다." >&2; exit 2 ;;
  esac
  if [ "$INTERVAL_HOURS" -lt 1 ] || [ "$INTERVAL_HOURS" -gt 168 ]; then
    echo "[오류] 예약 간격은 1~168시간만 허용합니다." >&2
    exit 2
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
  echo "[안내] 설치 직후 확인하려면: bash main update-now"
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
    echo "SCHEDULE=installed"
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
