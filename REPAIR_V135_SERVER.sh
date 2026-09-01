#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

export TCG_DISABLE_AUTO_GRADER_LOOKUP=1
PORT=8765
HEALTH_URL="http://127.0.0.1:${PORT}/api/v135-health"
DASHBOARD_URL="http://127.0.0.1:${PORT}/graded_photo_dashboard.js"
PID_FILE=".tcg_v135.pid"
LOCK_DIR=".repair_v135.lock"
NO_BOOT_UPDATE=0
[ "${1:-}" = "--no-boot-update" ] && NO_BOOT_UPDATE=1

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "[오류] 다른 TCG 서버 복구 작업이 이미 실행 중입니다. 10초 후 다시 실행하세요."
  exit 1
fi
cleanup_lock(){ rmdir "$LOCK_DIR" 2>/dev/null || true; }
trap cleanup_lock EXIT INT TERM

echo "=== TCG v135 서버 복구 + v155 RAW학습 ==="

health_now(){ curl -sS --max-time 2 "$HEALTH_URL" 2>/dev/null || true; }
health_is_current(){
  payload="$1"
  printf '%s' "$payload" | grep -q '"runtime": "tcg-updater-v135-verified-learning"' \
    && printf '%s' "$payload" | grep -q '"ok": true' \
    && printf '%s' "$payload" | grep -q '"manual_dual_photo_ui": true' \
    && printf '%s' "$payload" | grep -q '"manual_dual_photo_bridge_inline": true'
}
port_is_open(){
  python - "$PORT" <<'PY' >/dev/null 2>&1
import socket, sys
p=int(sys.argv[1])
s=socket.socket(); s.settimeout(0.35)
try:
    s.connect(('127.0.0.1', p))
except OSError:
    raise SystemExit(1)
finally:
    s.close()
PY
}
kill_pidfile_server(){
  [ -f "$PID_FILE" ] || return 0
  pid="$(tr -cd '0-9' < "$PID_FILE" 2>/dev/null || true)"
  [ -n "$pid" ] || { rm -f "$PID_FILE"; return 0; }
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    return 0
  fi
  cmd="$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
  case "$cmd" in
    *tcg_updater_v135.py*|*tcg_updater.py*)
      echo "[INFO] 이전 PID 파일 서버 종료: $pid"
      kill "$pid" 2>/dev/null || true
      for _ in 1 2 3 4 5; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
      done
      if kill -0 "$pid" 2>/dev/null; then
        echo "[INFO] 이전 PID 서버 강제 종료: $pid"
        kill -9 "$pid" 2>/dev/null || true
        sleep 1
      fi
      ;;
    *)
      echo "[안내] PID 파일 $pid 는 현재 TCG 서버가 아니어서 종료하지 않습니다."
      ;;
  esac
  rm -f "$PID_FILE"
}
stop_known_servers(){
  kill_pidfile_server
  pkill -f '[h]ttp\.server.*8765' 2>/dev/null || true
  pkill -f '[t]cg_updater_v135\.py' 2>/dev/null || true
  pkill -f '[t]cg_updater\.py' 2>/dev/null || true
  python release_tcg_port.py 2>/dev/null || true
}

stop_known_servers

REUSE_EXISTING=0
for attempt in 1 2 3 4 5 6 7 8; do
  if ! port_is_open; then
    break
  fi
  HEALTH="$(health_now)"
  if health_is_current "$HEALTH"; then
    REUSE_EXISTING=1
    echo "[OK] 다른 최신 v135 서버가 이미 정상 실행 중 · 재사용"
    break
  fi
  [ "$attempt" -eq 4 ] && stop_known_servers
  sleep 1
done

if [ "$REUSE_EXISTING" -eq 0 ] && port_is_open; then
  echo "[복구] 8765 포트가 남아 있어 마지막 강제 정리를 수행합니다."
  kill_pidfile_server
  pkill -9 -f '[h]ttp\.server.*8765' 2>/dev/null || true
  pkill -9 -f '[t]cg_updater_v135\.py' 2>/dev/null || true
  pkill -9 -f '[t]cg_updater\.py' 2>/dev/null || true
  python release_tcg_port.py 2>/dev/null || true
  sleep 2
fi

if [ "$REUSE_EXISTING" -eq 0 ] && port_is_open; then
  HEALTH="$(health_now)"
  if health_is_current "$HEALTH"; then
    REUSE_EXISTING=1
    echo "[OK] 정리 중 최신 v135 서버가 준비되어 재사용"
  else
    echo "[오류] 8765 포트를 비우지 못했습니다. 임의 프로세스를 종료하지 않고 중단합니다."
    echo "[응답] ${HEALTH:-없음}"
    ps -A -o PID,ARGS 2>/dev/null | grep -E 'tcg_updater|http\.server|8765' | grep -v grep || true
    exit 1
  fi
fi

pkill -f '[g]raded_photo_manual_pair_queue\.py --watch' 2>/dev/null || true
nohup python graded_photo_manual_pair_queue.py --watch --interval 60 \
  > TCG_MANUAL_PAIR_QUEUE.log 2>&1 &

# 검증완료 슬랩은 공식검증 이후 card-only ROI로만 RAW 학습에 전달한다.
if [ -f verified_slab_raw_learning_v155.py ]; then
  python verified_slab_raw_learning_v155.py --sync > TCG_VERIFIED_SLAB_RAW_LEARNING.log 2>&1 || true
  pkill -f '[v]erified_slab_raw_learning_v155\.py --watch' 2>/dev/null || true
  nohup python verified_slab_raw_learning_v155.py --watch --interval 30 \
    >> TCG_VERIFIED_SLAB_RAW_LEARNING.log 2>&1 &
  printf '%s\n' "$!" > .verified_slab_raw_learning.pid
fi

SERVER_PID=""
if [ "$REUSE_EXISTING" -eq 0 ]; then
  nohup env TCG_DISABLE_AUTO_GRADER_LOOKUP=1 python tcg_updater_v135.py \
    > TCG_ANDROID_STARTUP.log 2>&1 &
  SERVER_PID=$!
  printf '%s\n' "$SERVER_PID" > "$PID_FILE"
  echo "[INFO] v135 시작 PID: $SERVER_PID"
fi

HEALTH=""
READY=0
for attempt in $(seq 1 20); do
  sleep 1
  HEALTH="$(health_now)"
  if health_is_current "$HEALTH"; then
    READY=1
    break
  fi
  if [ -n "$SERVER_PID" ] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
    HEALTH="$(health_now)"
    if health_is_current "$HEALTH"; then
      READY=1
      break
    fi
    echo "[오류] v135 프로세스가 준비 전에 종료되었습니다."
    tail -n 100 TCG_ANDROID_STARTUP.log 2>/dev/null || true
    exit 1
  fi
done

if [ "$READY" -ne 1 ]; then
  echo "[오류] v135 건강검사 준비 실패"
  echo "[응답] ${HEALTH:-없음}"
  echo "=== 최근 서버 로그 ==="
  tail -n 100 TCG_ANDROID_STARTUP.log 2>/dev/null || true
  exit 1
fi

echo "[OK] v135 건강검사 정상"
echo "$HEALTH"

DASHBOARD="$(curl -fsS --max-time 6 "${DASHBOARD_URL}?v=155&check=$(date +%s)")"
if [ ! -f graded_photo_existing_revalidation_v159.py ]; then
  echo "[오류] 기존 후보 전체 재검증 v159 모듈이 없습니다."
  exit 1
fi
if ! printf '%s' "$DASHBOARD" | grep -q 'gpdManualBackPhoto'; then
  echo "[오류] 브라우저용 대시보드에 뒷면 사진 입력 UI가 전달되지 않습니다."
  exit 1
fi
if ! printf '%s' "$DASHBOARD" | grep -q '앞면 + 뒷면 8구역 등록하기'; then
  echo "[오류] 앞면+뒷면 8구역 등록 UI가 실제 대시보드 응답에 포함되지 않았습니다."
  exit 1
fi
if ! printf '%s' "$DASHBOARD" | grep -q '총 8구역 정밀검사'; then
  echo "[오류] 8구역 정밀검사 UI가 실제 대시보드 응답에 포함되지 않았습니다."
  exit 1
fi
if ! printf '%s' "$DASHBOARD" | grep -q '기존 등록사진·후보 전체 재검증'; then
  echo "[오류] 기존 등록사진·후보 전체 재검증 버튼이 실제 대시보드 응답에 포함되지 않았습니다."
  exit 1
fi
if ! printf '%s' "$DASHBOARD" | grep -q '/api/run-existing-photo-revalidation'; then
  echo "[오류] 기존 등록사진 재검증 API 호출 코드가 실제 대시보드 응답에 포함되지 않았습니다."
  exit 1
fi
if ! printf '%s' "$DASHBOARD" | grep -q 'verifiedSlabRawLearning:true'; then
  echo "[오류] 공식검증 슬랩 RAW학습 v155 브리지가 실제 대시보드 응답에 포함되지 않았습니다."
  exit 1
fi
echo "[OK] 앞면+뒷면 8구역 UI + 기존사진·후보 전체 재검증 + 공식검증 RAW학습 실전달 확인"

if [ "$NO_BOOT_UPDATE" -eq 0 ]; then
  mkdir -p "$HOME/.termux/boot"
  cat > "$HOME/.termux/boot/start-tcg.sh" <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
sleep 20
cd "$HOME/-tcg-grader" || exit 1
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true
nohup bash "$HOME/-tcg-grader/REPAIR_V135_SERVER.sh" --no-boot-update \
  >> "$HOME/-tcg-grader/TCG_ANDROID_BOOT.log" 2>&1 &
EOF
  chmod +x "$HOME/.termux/boot/start-tcg.sh"
  echo "[OK] Termux:Boot도 v135 + v155 RAW학습 복구 런처로 갱신"
fi

echo "[완료] http://127.0.0.1:${PORT}/index.html"
