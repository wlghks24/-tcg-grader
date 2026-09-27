#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${HOME}/.local/state/tcg-grader/scheduled-update"
LOG_DIR="${STATE_DIR}/logs"
STATUS_FILE="${STATE_DIR}/status.env"
BOOT_HEARTBEAT_FILE="${STATE_DIR}/boot-heartbeat.env"
BOOT_LOOP_PID_FILE="${STATE_DIR}/boot-loop.pid"
LOCK_DIR="${STATE_DIR}/lock"
LOCK_PID="${LOCK_DIR}/pid"
BOOT_DIR="${HOME}/.termux/boot"
BOOT_FILE="${BOOT_DIR}/tcg-grader-scheduled-update.sh"
SCHEDULE_HOUR="23"
SCHEDULE_MINUTE="00"
OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"

mkdir -p "$LOG_DIR"

now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
sha() { git -C "$ROOT" rev-parse "$1" 2>/dev/null || printf 'unknown'; }

next_run_kst() {
  python - "$SCHEDULE_HOUR" "$SCHEDULE_MINUTE" <<'PY'
from datetime import datetime, timedelta, timezone
import sys
h = int(sys.argv[1]); m = int(sys.argv[2])
tz = timezone(timedelta(hours=9))
now = datetime.now(tz)
target = now.replace(hour=h, minute=m, second=0, microsecond=0)
if target <= now:
    target += timedelta(days=1)
print(target.strftime('%Y-%m-%dT%H:%M:%S%z'))
PY
}

seconds_until_next_run() {
  python - "$SCHEDULE_HOUR" "$SCHEDULE_MINUTE" <<'PY'
from datetime import datetime, timedelta, timezone
import sys
h = int(sys.argv[1]); m = int(sys.argv[2])
tz = timezone(timedelta(hours=9))
now = datetime.now(tz)
target = now.replace(hour=h, minute=m, second=0, microsecond=0)
if target <= now:
    target += timedelta(days=1)
print(max(1, int((target - now).total_seconds())))
PY
}

termux_boot_state() {
  if command -v cmd >/dev/null 2>&1; then
    if cmd package path com.termux.boot 2>/dev/null | grep -q '^package:'; then
      printf 'detected'
    else
      printf 'not-detected'
    fi
    return 0
  fi
  if command -v pm >/dev/null 2>&1; then
    if pm path com.termux.boot 2>/dev/null | grep -q '^package:'; then
      printf 'detected'
    else
      printf 'not-detected'
    fi
    return 0
  fi
  printf 'unknown'
}

write_status() {
  local result="$1" message="$2" local_sha="$3" remote_sha="$4" tmp
  tmp="${STATUS_FILE}.tmp.$$"
  cat >"$tmp" <<EOF_STATUS
LAST_CHECK=$(now)
RESULT=$result
LOCAL_SHA=$local_sha
REMOTE_SHA=$remote_sha
MESSAGE=$message
EOF_STATUS
  mv "$tmp" "$STATUS_FILE"
}

write_boot_heartbeat() {
  local tmp
  tmp="${BOOT_HEARTBEAT_FILE}.tmp.$$"
  cat >"$tmp" <<EOF_HEARTBEAT
BOOT_LOOP_STARTED_AT=$(now)
BOOT_LOOP_PID=$$
ROOT=$ROOT
UPDATE_SCHEDULE=DAILY_${SCHEDULE_HOUR}:${SCHEDULE_MINUTE}_KST
NEXT_RUN_KST=$(next_run_kst)
EOF_HEARTBEAT
  mv "$tmp" "$BOOT_HEARTBEAT_FILE"
}

cleanup_lock() {
  rm -f "$LOCK_PID" 2>/dev/null || true
  rmdir "$LOCK_DIR" 2>/dev/null || true
}

cleanup_boot_loop_pid() {
  local recorded=""
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then
    recorded="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"
  fi
  if [ "$recorded" = "$$" ]; then
    rm -f "$BOOT_LOOP_PID_FILE" 2>/dev/null || true
  fi
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

start_loop_if_needed() {
  local owner="" loop_log="${LOG_DIR}/boot-loop.log"
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then
    owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"
  fi
  case "$owner" in
    ''|*[!0-9]*) owner="" ;;
  esac
  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    echo "[OK] 예약 업데이트 루프 실행 중(PID $owner)"
    return 0
  fi
  rm -f "$BOOT_LOOP_PID_FILE" 2>/dev/null || true
  nohup bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" boot-loop >>"$loop_log" 2>&1 </dev/null &
  owner=$!
  sleep 1
  if kill -0 "$owner" 2>/dev/null; then
    echo "[OK] 예약 업데이트 루프 자동 시작(PID $owner)"
    return 0
  fi
  echo "[오류] 예약 업데이트 루프 자동 시작 실패. 로그: $loop_log" >&2
  return 7
}

install_schedule() {
  mkdir -p "$BOOT_DIR"
  cat >"$BOOT_FILE" <<EOF_BOOT
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT=$(printf '%q' "$ROOT")
exec bash "\$ROOT/TABLET_SCHEDULED_UPDATE.sh" boot-loop
EOF_BOOT
  chmod 700 "$BOOT_FILE"
  if [ ! -x "$BOOT_FILE" ] || ! grep -Fq 'TABLET_SCHEDULED_UPDATE.sh" boot-loop' "$BOOT_FILE"; then
    echo "[오류] 태블릿 예약 업데이트 부팅 스크립트 설치 검증 실패" >&2
    return 6
  fi
  echo "[OK] 태블릿 기능 업데이트 예약 설치: 매일 ${SCHEDULE_HOUR}:${SCHEDULE_MINUTE} KST 확인"
  start_loop_if_needed
  echo "[안내] 즉시 동기화가 필요할 때만: bash main update-now"
}

ensure_schedule() {
  local boot_state
  if [ ! -x "$BOOT_FILE" ] || ! grep -Fq 'TABLET_SCHEDULED_UPDATE.sh" boot-loop' "$BOOT_FILE" 2>/dev/null; then
    echo "[안내] 예약 업데이트 부팅 스크립트가 없거나 구형이라 자동 복구합니다."
    install_schedule
  else
    start_loop_if_needed
  fi
  boot_state="$(termux_boot_state)"
  case "$boot_state" in
    detected)
      echo "[OK] Termux:Boot 감지 · 매일 23:00 KST 기능 업데이트 확인 준비 완료"
      return 0
      ;;
    not-detected)
      echo "[경고] Termux:Boot 앱을 감지하지 못했습니다. 현재 세션 루프는 실행하지만 재부팅 후 자동 main 확인은 HOLD입니다." >&2
      return 5
      ;;
    *)
      echo "[경고] Termux:Boot 설치 상태를 판별할 수 없습니다. 현재 세션 루프는 실행하지만 재부팅 후 자동 main 확인은 REVIEW_PENDING입니다." >&2
      return 5
      ;;
  esac
}

boot_loop() {
  local owner="" wait_seconds next_target
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then
    owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"
  fi
  case "$owner" in
    ''|*[!0-9]*) owner="" ;;
  esac
  if [ -n "$owner" ] && [ "$owner" != "$$" ] && kill -0 "$owner" 2>/dev/null; then
    echo "[안내] 예약 업데이트 루프가 이미 실행 중입니다(PID $owner)."
    return 0
  fi
  printf '%s\n' "$$" >"$BOOT_LOOP_PID_FILE"
  trap cleanup_boot_loop_pid EXIT INT TERM HUP
  write_boot_heartbeat
  while true; do
    wait_seconds="$(seconds_until_next_run)" || {
      echo "[경고] 다음 23:00 KST 계산 실패; 60초 후 재시도" >&2
      sleep 60
      continue
    }
    next_target="$(next_run_kst)" || next_target="unknown"
    echo "[$(now)] 다음 기능 업데이트 확인: ${next_target} (KST)"
    sleep "$wait_seconds" || true
    bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" run || true
    write_boot_heartbeat
  done
}

remove_schedule() {
  local owner=""
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then
    owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"
  fi
  case "$owner" in
    ''|*[!0-9]*) owner="" ;;
  esac
  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    kill "$owner" 2>/dev/null || true
  fi
  rm -f "$BOOT_LOOP_PID_FILE" "$BOOT_FILE"
  echo "[OK] 태블릿 예약 업데이트를 제거했습니다."
}

show_status() {
  local boot_state loop_state="not-running" owner=""
  boot_state="$(termux_boot_state)"
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then
    owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"
  fi
  case "$owner" in
    ''|*[!0-9]*) owner="" ;;
  esac
  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    loop_state="running:$owner"
  fi
  echo "현재 HEAD: $(sha HEAD)"
  if [ -f "$STATUS_FILE" ]; then
    cat "$STATUS_FILE"
  else
    echo "예약 업데이트 실행 기록이 없습니다."
  fi
  if [ -x "$BOOT_FILE" ] && grep -Fq 'TABLET_SCHEDULED_UPDATE.sh" boot-loop' "$BOOT_FILE" 2>/dev/null; then
    echo "SCHEDULE=installed"
  else
    echo "SCHEDULE=not-installed"
  fi
  echo "UPDATE_SCHEDULE=DAILY_${SCHEDULE_HOUR}:${SCHEDULE_MINUTE}_KST"
  echo "NEXT_RUN_KST=$(next_run_kst 2>/dev/null || echo unknown)"
  echo "BOOT_LOOP=$loop_state"
  echo "TERMUX_BOOT=$boot_state"
  if [ -f "$BOOT_HEARTBEAT_FILE" ]; then
    cat "$BOOT_HEARTBEAT_FILE"
  else
    echo "BOOT_LOOP_HEARTBEAT=not-seen"
  fi
}

case "${1:-status}" in
  run|now) run_update ;;
  install) install_schedule ;;
  ensure) ensure_schedule ;;
  boot-loop) boot_loop ;;
  remove|uninstall) remove_schedule ;;
  status) show_status ;;
  *) echo "사용법: bash TABLET_SCHEDULED_UPDATE.sh [install|ensure|run|status|remove]" >&2; exit 2 ;;
esac
