#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"
BASE_URL="https://raw.githubusercontent.com/wlghks24/-tcg-grader/main"
STAMP="$(date +%Y%m%d_%H%M%S)"

backup_if_exists() {
  if [ -f "$1" ]; then
    cp -p "$1" "$1.before_grade_learning_v135_${STAMP}"
  fi
}

for name in \
  index.html \
  START_TCG_UPDATER_ANDROID.sh \
  vision_calibration.json \
  verified_grade_learning_v135.py \
  verified_grade_learning_v135_safe.py \
  tcg_updater_v135.py \
  grade_learning_guard_v135.js \
  test_verified_grade_learning_v135.py \
  test_verified_grade_learning_v135_safe.py; do
  backup_if_exists "$name"
done

for name in \
  START_TCG_UPDATER_ANDROID.sh \
  verified_grade_learning_v135.py \
  verified_grade_learning_v135_safe.py \
  tcg_updater_v135.py \
  grade_learning_guard_v135.js \
  test_verified_grade_learning_v135.py \
  test_verified_grade_learning_v135_safe.py; do
  tmp=".${name}.download.tmp"
  rm -f "$tmp"
  curl -L --fail --retry 3 --retry-delay 2 -H 'Cache-Control: no-cache' \
    "${BASE_URL}/${name}?$(date +%s)" -o "$tmp"
  test -s "$tmp"
  mv "$tmp" "$name"
done

python -m py_compile \
  verified_grade_learning_v135.py \
  verified_grade_learning_v135_safe.py \
  tcg_updater_v135.py \
  test_verified_grade_learning_v135.py \
  test_verified_grade_learning_v135_safe.py

python -m unittest -v \
  test_verified_grade_learning_v135.py \
  test_verified_grade_learning_v135_safe.py

# Add the verified-model browser guard without replacing the user's current
# locally patched index.html (iPhone contrast fixes and other local changes stay intact).
python - <<'PY'
from pathlib import Path
p=Path('index.html')
text=p.read_text(encoding='utf-8')
tag='<script src="./grade_learning_guard_v135.js?v=135"></script>'
if 'grade_learning_guard_v135.js' not in text:
    if '</body>' in text:
        text=text.replace('</body>',tag+'\n</body>',1)
    elif '</html>' in text:
        text=text.replace('</html>',tag+'\n</html>',1)
    else:
        text += '\n'+tag+'\n'
    p.write_text(text,encoding='utf-8')
print('[OK] index v135 guard:', text.count('grade_learning_guard_v135.js'))
PY

# Rebuild the residual vision calibration once from registry-gated rows only.
# This is parameters-only; no photo is deleted or moved.
python - <<'PY'
import json
import verified_grade_learning_v135_safe as learning
result=learning.rebuild_safe_vision_calibration()
audit=learning.audit()
print('[OK] v135 registry-gated vision calibration rebuilt')
print(json.dumps({
  'verified_registry_entries':audit.get('verified_registry_entries',0),
  'verified_training_rows':audit.get('verified_training_rows',0),
  'vision_profiles':audit.get('vision_profiles',0),
  'audit':audit.get('audit',{}),
},ensure_ascii=False))
PY

if command -v node >/dev/null 2>&1; then
  node --check grade_learning_guard_v135.js
else
  echo "[INFO] node 없음 · JS 문법검사는 브라우저 로드/서버 정적검사에서 확인"
fi

echo "=== v135 설치 검증 ==="
grep -n 'grade_learning_guard_v135.js' index.html | head -1
grep -n 'tcg_updater_v135.py' START_TCG_UPDATER_ANDROID.sh | head -1

echo "=== 서버 재시작 ==="
pkill -f 'python.*tcg_updater_v135.py' 2>/dev/null || true
pkill -f 'python.*tcg_updater.py' 2>/dev/null || true
sleep 2
nohup bash START_TCG_UPDATER_ANDROID.sh > TCG_ANDROID_STARTUP.log 2>&1 &
sleep 5

HEALTH="$(curl -s --max-time 5 http://127.0.0.1:8765/api/health || true)"
MODEL="$(curl -s --max-time 5 http://127.0.0.1:8765/api/learning-model-status || true)"
AUDIT="$(curl -s --max-time 5 http://127.0.0.1:8765/api/grade-learning-audit || true)"

echo "HEALTH: $HEALTH"
echo "MODEL: $MODEL"
echo "AUDIT: $AUDIT"

python - <<'PY'
import json, urllib.request
for url in ('http://127.0.0.1:8765/api/health','http://127.0.0.1:8765/api/learning-model-status','http://127.0.0.1:8765/api/grade-learning-audit'):
    with urllib.request.urlopen(url,timeout=5) as r:
        data=json.loads(r.read().decode('utf-8'))
        assert data.get('ok') is True, (url,data)
print('[OK] v135 서버 API 3종 정상')
PY

echo "[OK] v135 등급측정 검증학습 업그레이드 설치 완료"
echo "- 사용자 체크박스만으로는 학습하지 않음"
echo "- PSA/BGS/CGC/TAG/BRG 공식 인증조회 성공자료만 로컬 검증레지스트리에 저장"
echo "- 공식 레지스트리 company+인증번호+실제등급이 정확히 일치해야 보정 학습 가능"
echo "- RAW 원시예측(raw_pred) 필수 · 슬랩/마켓 사진은 RAW 보정에서 제외"
echo "- 회사별 분리 · 카드단위 교차검증 · 오차 개선 시에만 하향보정 · 상향보정 금지"
echo "- 비전 잔차보정도 v135 레지스트리 통과 행만 사용"
echo "- 과거 eBay 격리사진/백업사진은 이동·삭제·학습하지 않음"
echo "- 현재 사진 원본/백업 폴더는 변경하지 않음"
