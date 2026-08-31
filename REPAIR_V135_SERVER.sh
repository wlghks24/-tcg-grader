#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

export TCG_DISABLE_AUTO_GRADER_LOOKUP=1
PORT=8765
HEALTH_URL="http://127.0.0.1:${PORT}/api/v135-health"
NO_BOOT_UPDATE=0
[ "${1:-}" = "--no-boot-update" ] && NO_BOOT_UPDATE=1

echo "=== TCG v135 서버 복구 ==="

# Android에서는 /proc 소켓 소유자 조회가 제한될 수 있어 release_tcg_port.py만으로
# 예전 http.server가 남는 경우가 있다. 먼저 알려진 TCG/정적서버 패턴을 정리하고,
# 가능한 경우 실제 LISTEN 소켓 소유자도 함께 종료한다.
pkill -f 'python(3)? .*http\.server.*8765' 2>/dev/null || true
pkill -f 'python(3)?.*tcg_updater_v135\.py' 2>/dev/null || true
pkill -f 'python(3)?.*tcg_updater\.py' 2>/dev/null || true
python release_tcg_port.py 2>/dev/null || true
sleep 2

# 등급사진 게임별 수동대기 감시도 새 서버와 함께 한 개만 유지한다.
pkill -f 'graded_photo_manual_pair_queue\.py --watch' 2>/dev/null || true
nohup python graded_photo_manual_pair_queue.py --watch --interval 60 \
  > TCG_MANUAL_PAIR_QUEUE.log 2>&1 &

# 래퍼를 직접 실행해 구형 tcg_updater.py/http.server가 8765를 다시 차지할 여지를 줄인다.
nohup env TCG_DISABLE_AUTO_GRADER_LOOKUP=1 python tcg_updater_v135.py \
  > TCG_ANDROID_STARTUP.log 2>&1 &
SERVER_PID=$!
printf '%s\n' "$SERVER_PID" > .tcg_v135.pid

echo "[INFO] v135 시작 PID: $SERVER_PID"

HEALTH=""
READY=0
for attempt in $(seq 1 20); do
  sleep 1
  HEALTH="$(curl -sS --max-time 2 "$HEALTH_URL" 2>/dev/null || true)"
  if printf '%s' "$HEALTH" | grep -q '"runtime": "tcg-updater-v135-verified-learning"' \
     && printf '%s' "$HEALTH" | grep -q '"ok": true'; then
    READY=1
    break
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "[오류] v135 프로세스가 준비 전에 종료되었습니다."
    tail -n 80 TCG_ANDROID_STARTUP.log 2>/dev/null || true
    exit 1
  fi
  if [ "$attempt" -eq 6 ]; then
    # 404가 계속되면 다른 프로세스가 포트를 선점한 것이다. 한 번 더 강하게 정리 후 재시작.
    if curl -s -o /dev/null -w '%{http_code}' --max-time 2 "$HEALTH_URL" 2>/dev/null | grep -q '^404$'; then
      echo "[복구] 8765에서 구형 서버 404 감지 · 포트 재정리 후 v135 재시작"
      kill "$SERVER_PID" 2>/dev/null || true
      sleep 1
      pkill -9 -f 'python(3)? .*http\.server.*8765' 2>/dev/null || true
      pkill -9 -f 'python(3)?.*tcg_updater_v135\.py' 2>/dev/null || true
      pkill -9 -f 'python(3)?.*tcg_updater\.py' 2>/dev/null || true
      python release_tcg_port.py 2>/dev/null || true
      sleep 2
      nohup env TCG_DISABLE_AUTO_GRADER_LOOKUP=1 python tcg_updater_v135.py \
        > TCG_ANDROID_STARTUP.log 2>&1 &
      SERVER_PID=$!
      printf '%s\n' "$SERVER_PID" > .tcg_v135.pid
    fi
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

# 사용자가 이미 Termux:Boot를 쓰는 경우 다음 재부팅부터도 동일한 복구 경로를 사용한다.
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
  echo "[OK] Termux:Boot도 v135 복구 런처로 갱신"
fi

echo "[완료] http://127.0.0.1:${PORT}/index.html"
