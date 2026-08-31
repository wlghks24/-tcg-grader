#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"
BASE_URL="https://raw.githubusercontent.com/wlghks24/-tcg-grader/main"
STAMP="$(date +%Y%m%d_%H%M%S)"

FILES=(
  grading_accuracy_v99.py
  verified_grade_learning_v135.py
  verified_grade_learning_v135_safe.py
  tcg_updater_v135.py
  START_TCG_UPDATER_ANDROID.sh
  test_verified_grade_learning_v135.py
  test_verified_grade_learning_v135_safe.py
)

for name in "${FILES[@]}"; do
  if [ -f "$name" ]; then cp -p "$name" "$name.before_v137_${STAMP}"; fi
  tmp=".${name}.v137.tmp"
  rm -f "$tmp"
  curl -L --fail --retry 4 --retry-delay 2 -H 'Cache-Control: no-cache' \
    "${BASE_URL}/${name}?$(date +%s%N)" -o "$tmp"
  test -s "$tmp"
  mv "$tmp" "$name"
done

python -m py_compile \
  grading_accuracy_v99.py \
  verified_grade_learning_v135.py \
  verified_grade_learning_v135_safe.py \
  tcg_updater_v135.py \
  test_verified_grade_learning_v135.py \
  test_verified_grade_learning_v135_safe.py

python -m unittest -v test_verified_grade_learning_v135.py test_verified_grade_learning_v135_safe.py

grep -q "RUNTIME_PATCH = 137" tcg_updater_v135.py
grep -q "exec python tcg_updater_v135.py" START_TCG_UPDATER_ANDROID.sh
grep -q "구버전 서버로 폴백하지 않습니다" START_TCG_UPDATER_ANDROID.sh

echo "[OK] v137 파일/테스트 검증 완료"
echo "=== 기존 8765 서버 완전 종료 ==="

# Stop stale launch shells first so they cannot keep an old runtime alive.
pkill -TERM -f '[S]TART_TCG_UPDATER_ANDROID.sh' 2>/dev/null || true
pkill -TERM -f '[p]ython(3)? .*tcg_updater(_v135)?\.py' 2>/dev/null || true
sleep 2
pkill -KILL -f '[p]ython(3)? .*tcg_updater(_v135)?\.py' 2>/dev/null || true
sleep 2

# Fail closed if something else still owns the old TCG endpoint.
if curl -sS --max-time 2 http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
  echo "[ERROR] 8765 포트의 기존 서버가 아직 살아 있습니다. 새 서버를 덮어쓰지 않습니다." >&2
  echo "--- 관련 프로세스 ---" >&2
  ps -A -o pid,args 2>/dev/null | grep -E '[t]cg_updater|[8]765' >&2 || true
  exit 1
fi

echo "[OK] 기존 서버 종료 확인"

echo "=== v137 안전서버 직접 시작 ==="
nohup python tcg_updater_v135.py > TCG_ANDROID_STARTUP.log 2>&1 &
SERVER_PID=$!
echo "$SERVER_PID" > .tcg_server_v137.pid

READY=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "[ERROR] v137 서버 프로세스가 시작 중 종료됐습니다." >&2
    tail -80 TCG_ANDROID_STARTUP.log >&2 || true
    exit 1
  fi
  if curl -fsS --max-time 2 http://127.0.0.1:8765/api/v135-health > .v137_health.json 2>/dev/null; then
    READY=1
    break
  fi
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "[ERROR] v135 전용 health endpoint가 열리지 않았습니다." >&2
  echo "--- startup log ---" >&2
  tail -100 TCG_ANDROID_STARTUP.log >&2 || true
  exit 1
fi

python - <<'PY'
import json, urllib.request
checks = (
    ('http://127.0.0.1:8765/api/v135-health', 'runtime'),
    ('http://127.0.0.1:8765/api/learning-model-status', None),
    ('http://127.0.0.1:8765/api/grade-learning-audit', None),
)
for url, marker in checks:
    with urllib.request.urlopen(url, timeout=6) as r:
        data=json.loads(r.read().decode('utf-8'))
    assert data.get('ok') is True, (url, data)
    if marker:
        assert data.get('runtime') == 'tcg-updater-v135-verified-learning', data
        assert int(data.get('patch') or 0) >= 137, data
    print(url, 'OK')
print('[OK] v137 전용 런타임 + 학습 API 3종 정상')
PY

echo "=== v137 완료 ==="
echo "[OK] 구버전 서버 폴백 제거"
echo "[OK] v135 verified-learning 서버를 8765에 직접 실행"
echo "[OK] 12개 등급학습 테스트 통과"
echo "[OK] /api/v135-health 로 실제 실행 서버 식별"
echo "[OK] learning-model-status / grade-learning-audit 정상"
echo "[INFO] 서버 PID: $SERVER_PID"
echo "[INFO] 재부팅 후에도 START_TCG_UPDATER_ANDROID.sh는 v135 안전서버만 실행"
