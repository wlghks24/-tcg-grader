#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"
BASE_URL="https://raw.githubusercontent.com/wlghks24/-tcg-grader/main"
STAMP="$(date +%Y%m%d_%H%M%S)"

backup_if_exists() {
  if [ -f "$1" ]; then
    cp -p "$1" "$1.before_grade_learning_v142_${STAMP}"
  fi
}

RUNTIME_FILES=(
  START_TCG_UPDATER_ANDROID.sh
  grading_accuracy_v99.py
  verified_grade_learning_v135.py
  verified_grade_learning_v135_safe.py
  tcg_updater_v135.py
  grade_learning_guard_v135.js
  event_collection_hardening_v139.py
  event_collection_hardening_v140.py
  event_collection_hardening_v141.py
  collection_learning_hardening_v142.py
  event_gap_learning.py
  event_priority_watch.py
  event_quick_watch.py
  social_event_discovery.py
  multi_route_event_discovery.py
  adaptive_collection_learner.py
  fan_social_learning.py
  auto_pipeline_runner.py
  test_event_quick_watch.py
  test_collection_learning_hardening_v142.py
  test_verified_grade_learning_v135.py
  test_verified_grade_learning_v135_safe.py
)

for name in index.html vision_calibration.json "${RUNTIME_FILES[@]}"; do
  backup_if_exists "$name"
done

# Code/runtime only: do not overwrite local learned candidate/history JSON.
for name in "${RUNTIME_FILES[@]}"; do
  tmp=".${name}.download.tmp"
  rm -f "$tmp"
  curl -L --fail --retry 3 --retry-delay 2 -H 'Cache-Control: no-cache' \
    "${BASE_URL}/${name}?$(date +%s)" -o "$tmp"
  test -s "$tmp"
  mv "$tmp" "$name"
done

python -m py_compile \
  grading_accuracy_v99.py \
  verified_grade_learning_v135.py \
  verified_grade_learning_v135_safe.py \
  tcg_updater_v135.py \
  event_collection_hardening_v139.py \
  event_collection_hardening_v140.py \
  event_collection_hardening_v141.py \
  collection_learning_hardening_v142.py \
  event_gap_learning.py \
  event_priority_watch.py \
  event_quick_watch.py \
  social_event_discovery.py \
  multi_route_event_discovery.py \
  adaptive_collection_learner.py \
  fan_social_learning.py \
  auto_pipeline_runner.py \
  test_event_quick_watch.py \
  test_collection_learning_hardening_v142.py \
  test_verified_grade_learning_v135.py \
  test_verified_grade_learning_v135_safe.py

python -m unittest -v \
  test_event_quick_watch.py \
  test_collection_learning_hardening_v142.py \
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

python - <<'PY'
import collection_learning_hardening_v142 as h
import event_priority_watch, event_quick_watch
status=h.apply()
assert int(status.get('patch') or 0) == 142, status
assert event_priority_watch.hardening.PATCH_ID == 142
assert event_quick_watch.hardening.PATCH_ID == 142
assert status.get('verified_reward_term_learning') is True
assert status.get('unique_evidence_host_counting') is True
assert status.get('strict_official_social_url_match') is True
assert status.get('fan_reuse_requires_corroboration_or_watch') is True
assert float(status.get('official_reward_learning_weight') or 0) == 1.35
assert float(status.get('cross_checked_reward_learning_weight') or 0) == 0.90
assert float(status.get('unverified_reward_learning_weight', -1)) == 0.0
assert float(status.get('unverified_payload_learning_weight', -1)) == 0.0
assert float(status.get('unverified_search_host_term_learning_weight', -1)) == 0.0
print('[OK] v142 자료수집·행사 검증학습 연결 정상')
PY

if command -v node >/dev/null 2>&1; then
  node --check grade_learning_guard_v135.js
else
  echo "[INFO] node 없음 · JS 문법검사는 브라우저 로드/서버 정적검사에서 확인"
fi

echo "=== v142 설치 검증 ==="
grep -n 'grade_learning_guard_v135.js' index.html | head -1
grep -n 'tcg_updater_v135.py' START_TCG_UPDATER_ANDROID.sh | head -1
grep -n 'collection_learning_hardening_v142.py' START_TCG_UPDATER_ANDROID.sh | head -1
grep -n 'collection_learning_hardening_v142' auto_pipeline_runner.py | head -1

echo "=== 서버 재시작 ==="
pkill -f 'python.*tcg_updater_v135.py' 2>/dev/null || true
pkill -f 'python.*tcg_updater.py' 2>/dev/null || true
sleep 2
nohup bash START_TCG_UPDATER_ANDROID.sh > TCG_ANDROID_STARTUP.log 2>&1 &
sleep 5

HEALTH="$(curl -s --max-time 5 http://127.0.0.1:8765/api/v135-health || true)"
MODEL="$(curl -s --max-time 5 http://127.0.0.1:8765/api/learning-model-status || true)"
AUDIT="$(curl -s --max-time 5 http://127.0.0.1:8765/api/grade-learning-audit || true)"

echo "HEALTH: $HEALTH"
echo "MODEL: $MODEL"
echo "AUDIT: $AUDIT"

python - <<'PY'
import json, urllib.request
checks=(
 ('http://127.0.0.1:8765/api/v135-health','v142'),
 ('http://127.0.0.1:8765/api/learning-model-status',None),
 ('http://127.0.0.1:8765/api/grade-learning-audit',None),
)
for url, marker in checks:
    with urllib.request.urlopen(url,timeout=5) as r:
        data=json.loads(r.read().decode('utf-8'))
    assert data.get('ok') is True, (url,data)
    if marker:
        assert int(data.get('patch') or 0) >= 142, data
        assert int(data.get('event_collection_patch') or 0) >= 142, data
        assert data.get('verified_reward_term_learning') is True, data
        assert data.get('unique_evidence_host_counting') is True, data
        assert data.get('strict_official_social_url_match') is True, data
        assert data.get('fan_reuse_requires_corroboration_or_watch') is True, data
        assert float(data.get('unverified_reward_learning_weight', -1)) == 0.0, data
        assert float(data.get('unverified_payload_learning_weight', -1)) == 0.0, data
        assert float(data.get('unverified_search_host_term_learning_weight', -1)) == 0.0, data
print('[OK] v142 서버 API + 자료수집 자가학습 보안 정상')
PY

echo "[OK] v142 등급측정 + 자료수집/행사 검증학습 업그레이드 설치 완료"
echo "- 포켓몬/원피스/나루토 카드·프로모·한정판·콜라보 증정은 기존 행사 범위 밖이어도 후보 수집"
echo "- 같은 출처의 중복 경로는 독립 출처 수를 부풀리지 않음"
echo "- 공식 검증 증정정보 검색앵커 가중치 +1.35"
echo "- 독립 2곳 이상 교차검증 증정정보 검색앵커 가중치 +0.90"
echo "- 미검증 커뮤니티/SNS/검색 후보의 지속 host·검색어 학습 가중치 0.00"
echo "- 공식 SNS는 실제 계정 URL이 일치할 때만 공식 힌트 인정 · 제목의 계정명 언급만으로 공식 처리 금지"
echo "- 팬 계정 자동 재탐색은 교차확인 또는 명시적 watch 등록 후에만 허용"
echo "- 일반 판매 글은 증정 행동이 없으면 giveaway 학습에서 제외"
echo "- 사용자 체크박스만으로는 등급 학습하지 않음"
echo "- PSA/BGS/CGC/TAG/BRG 공식 인증조회 성공자료만 로컬 검증레지스트리에 저장"
echo "- 공식 레지스트리 company+인증번호+실제등급이 정확히 일치해야 보정 학습 가능"
echo "- RAW 원시예측(raw_pred) 필수 · 슬랩/마켓 사진은 RAW 보정에서 제외"
echo "- 회사별 분리 · 카드단위 교차검증 · 오차 개선 시에만 하향보정 · 상향보정 금지"
echo "- 비전 잔차보정도 v135 레지스트리 통과 행만 사용"
echo "- 과거 eBay 격리사진/백업사진은 이동·삭제·학습하지 않음"
echo "- 현재 사진 원본/백업 폴더는 변경하지 않음"
