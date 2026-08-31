#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

# v136 hotfix: pin the corrected grading_accuracy_v99.py to the immutable
# commit that fixes the 10-sample cross-validation strength-boundary bug.
PINNED_COMMIT="2de487546062c4664e91ec5926dcdffaea7bc56f"
RAW="https://raw.githubusercontent.com/wlghks24/-tcg-grader/${PINNED_COMMIT}/grading_accuracy_v99.py"
STAMP="$(date +%Y%m%d_%H%M%S)"

if [ -f grading_accuracy_v99.py ]; then
  cp -p grading_accuracy_v99.py "grading_accuracy_v99.py.before_v136_${STAMP}"
fi

tmp=".grading_accuracy_v99.py.v136.tmp"
rm -f "$tmp"
curl -L --fail --retry 4 --retry-delay 2 -H 'Cache-Control: no-cache' "${RAW}?$(date +%s)" -o "$tmp"
test -s "$tmp"

# Refuse installation if a proxy/CDN returned the pre-fix source.
grep -q '_candidate(rows:list\[dict\[str,Any\]\],evidence_n:int|None=None)' "$tmp"
grep -q 'corr=_candidate(train,evidence_n=n)' "$tmp"
mv "$tmp" grading_accuracy_v99.py

python -m py_compile grading_accuracy_v99.py verified_grade_learning_v135.py verified_grade_learning_v135_safe.py tcg_updater_v135.py

# Direct regression check for the exact failure seen on the tablet.
python - <<'PY'
from grading_accuracy_v99 import train_company_calibration
rows=[{
    'company':'PSA','actual':9.0,'raw_pred':10.0,
    'card_id':f'independent-{i}','certification_id':f'900000{i:02d}'
} for i in range(10)]
psa=train_company_calibration(rows)['PSA']
print('[V136] boundary model:', psa)
assert psa['n']==10
assert psa['unique_cards']==10
assert psa['enabled'] is True
assert psa['correction'] < 0
assert psa['correction'] >= -0.75
print('[OK] v136 10건 경계 교차검증 직접 회귀검사 통과')
PY

python -m unittest -v test_verified_grade_learning_v135.py test_verified_grade_learning_v135_safe.py

# Preserve the locally patched index.html; only make sure the v135 browser gate exists.
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
print('[OK] browser verified-learning guard:', text.count('grade_learning_guard_v135.js'))
PY

# Rebuild vision residual calibration only from registry-gated verified rows.
python - <<'PY'
import json
import verified_grade_learning_v135_safe as learning
result=learning.rebuild_safe_vision_calibration()
audit=learning.audit()
print('[OK] registry-gated vision calibration rebuilt')
print(json.dumps({
  'verified_registry_entries':audit.get('verified_registry_entries',0),
  'verified_training_rows':audit.get('verified_training_rows',0),
  'vision_profiles':audit.get('vision_profiles',0),
  'policy':audit.get('policy',{}),
},ensure_ascii=False))
PY

# Verify startup script is the v135 server launcher before restarting.
if ! grep -q 'tcg_updater_v135.py' START_TCG_UPDATER_ANDROID.sh; then
  echo '[ERROR] START_TCG_UPDATER_ANDROID.sh가 v135 서버를 가리키지 않습니다.' >&2
  exit 1
fi

echo '=== 서버 재시작 ==='
pkill -f 'python.*tcg_updater_v135.py' 2>/dev/null || true
pkill -f 'python.*tcg_updater.py' 2>/dev/null || true
sleep 2
nohup bash START_TCG_UPDATER_ANDROID.sh > TCG_ANDROID_STARTUP.log 2>&1 &
sleep 6

python - <<'PY'
import json, urllib.request
urls=(
 'http://127.0.0.1:8765/api/health',
 'http://127.0.0.1:8765/api/learning-model-status',
 'http://127.0.0.1:8765/api/grade-learning-audit',
)
for url in urls:
    with urllib.request.urlopen(url,timeout=6) as r:
        data=json.loads(r.read().decode('utf-8'))
        assert data.get('ok') is True,(url,data)
        print(url, 'OK')
print('[OK] v136 서버 API 3종 정상')
PY

echo '[OK] v136 hotfix 완료'
echo '- 10건 경계 교차검증 회귀오류 수정'
echo '- 12개 v135/v135-safe 테스트 통과 필요'
echo '- 공식 인증 레지스트리 + RAW 원시예측 게이트 유지'
echo '- 상향보정 금지 / 최대 하향보정 -0.75 유지'
echo '- 기존 사진/백업은 변경하지 않음'
