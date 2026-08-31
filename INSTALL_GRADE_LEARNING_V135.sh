#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"
BASE_URL="https://raw.githubusercontent.com/wlghks24/-tcg-grader/main"
STAMP="$(date +%Y%m%d_%H%M%S)"

backup_if_exists() {
  if [ -f "$1" ]; then
    cp -p "$1" "$1.before_grade_learning_v143_${STAMP}"
  fi
}

# v143: the tablet must update the whole executable collector/recovery bundle.
# Updating only tcg_updater_v135.py left old auto_update_all/auto_repair/search
# modules behind, so already-fixed failures could reappear on the tablet.
PY_RUNTIME_FILES=(
  grading_accuracy_v99.py
  verified_grade_learning_v135.py
  verified_grade_learning_v135_safe.py
  vision_calibration.py
  safe_runtime.py
  server_security_guard.py
  auto_repair_engine.py
  auto_update_all.py
  tcg_updater.py
  tcg_updater_v135.py
  runtime_bundle_guard_v143.py
  update_releases.py
  release_history_backfill.py
  update_market_watch.py
  update_market_prices.py
  market_public_crosscheck.py
  update_promo_events.py
  supplementary_discovery.py
  update_purchase_sources.py
  update_exchange_rates.py
  validate_external_links.py
  graded_photo_multi_source.py
  graded_photo_evidence.py
  detailed_collection_intelligence.py
  grading_cert_verifier.py
  manual_graded_photo_registration.py
  manual_official_proof.py
  library_slab_corpus.py
  IMPORT_GRADED_LEARNING_FILES.py
  multi_channel_agent.py
  search_method_learning.py
  provider_health_learning.py
  provider_segment_learning.py
  adaptive_collection_learner.py
  collection_meta_learning.py
  event_collection_hardening_v139.py
  event_collection_hardening_v140.py
  event_collection_hardening_v141.py
  collection_learning_hardening_v142.py
  event_gap_learning.py
  event_priority_watch.py
  event_quick_watch.py
  social_event_discovery.py
  multi_route_event_discovery.py
  fan_social_learning.py
  auto_pipeline_runner.py
  cross_platform_agent.py
  official_channel_feed_discovery.py
  official_direct_discovery.py
  official_sitemap_discovery.py
  test_event_quick_watch.py
  test_collection_learning_hardening_v142.py
  test_runtime_bundle_guard_v143.py
  test_verified_grade_learning_v135.py
  test_verified_grade_learning_v135_safe.py
)

TEXT_RUNTIME_FILES=(
  START_TCG_UPDATER_ANDROID.sh
  START_GRADED_FILE_LEARNING.sh
  INSTALL_MANUAL_OFFICIAL_FALLBACK.sh
  grade_learning_guard_v135.js
  graded_photo_dashboard.js
  manual_official_verify_bridge.js
)

REFERENCE_FILES=(
  social_source_registry.json
  manual_event_evidence.json
  scenario_learning_profiles.json
)

for name in index.html vision_calibration.json "${PY_RUNTIME_FILES[@]}" "${TEXT_RUNTIME_FILES[@]}" "${REFERENCE_FILES[@]}"; do
  backup_if_exists "$name"
done

# Code/reference runtime only: do not overwrite local candidate/history/learning JSON.
for name in "${PY_RUNTIME_FILES[@]}" "${TEXT_RUNTIME_FILES[@]}" "${REFERENCE_FILES[@]}"; do
  tmp=".${name}.download.tmp"
  rm -f "$tmp"
  curl -L --fail --retry 3 --retry-delay 2 -H 'Cache-Control: no-cache' \
    "${BASE_URL}/${name}?$(date +%s)" -o "$tmp"
  test -s "$tmp"
  mv "$tmp" "$name"
done

python -m py_compile "${PY_RUNTIME_FILES[@]}"

python -m unittest -v \
  test_event_quick_watch.py \
  test_collection_learning_hardening_v142.py \
  test_runtime_bundle_guard_v143.py \
  test_verified_grade_learning_v135.py \
  test_verified_grade_learning_v135_safe.py

# Add the verified-model browser guard without replacing the user's current
# locally patched index.html (iPhone/tablet UI fixes and local changes stay intact).
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

# Rebuild residual vision calibration only from registry-gated rows.
python - <<'PY'
import json
import verified_grade_learning_v135_safe as learning
learning.rebuild_safe_vision_calibration()
audit=learning.audit()
print('[OK] v135 registry-gated vision calibration rebuilt')
print(json.dumps({
  'verified_registry_entries':audit.get('verified_registry_entries',0),
  'verified_training_rows':audit.get('verified_training_rows',0),
  'vision_profiles':audit.get('vision_profiles',0),
  'audit':audit.get('audit',{}),
},ensure_ascii=False))
PY

# v143 performs semantic compatibility checks instead of trusting filenames.
python - <<'PY'
import json
import collection_learning_hardening_v142 as learning_guard
import runtime_bundle_guard_v143 as bundle_guard
import event_priority_watch, event_quick_watch
status=learning_guard.apply()
bundle=bundle_guard.require_compatible()
assert int(status.get('patch') or 0) == 142, status
assert int(bundle.get('patch') or 0) == 143, bundle
assert bundle.get('missing_file_count') == 0, bundle
assert bundle.get('issue_count') == 0, bundle
assert bundle.get('contracts',{}).get('manual_official_fallback') is True, bundle
assert bundle.get('contracts',{}).get('manual_proof_raw_calibration') is False, bundle
assert bundle.get('contracts',{}).get('manual_proof_rejected_bytes_retained') is False, bundle
assert event_priority_watch.hardening.PATCH_ID == 142
assert event_quick_watch.hardening.PATCH_ID == 142
assert status.get('verified_reward_term_learning') is True
assert status.get('unique_evidence_host_counting') is True
assert status.get('strict_official_social_url_match') is True
assert status.get('fan_reuse_requires_corrob​​oration_or_watch', status.get('fan_reuse_requires_corroboration_or_watch')) is True
assert float(status.get('official_reward_learning_weight') or 0) == 1.35
assert float(status.get('cross_checked_reward_learning_weight') or 0) == 0.90
assert float(status.get('unverified_reward_learning_weight', -1)) == 0.0
assert float(status.get('unverified_payload_learning_weight', -1)) == 0.0
assert float(status.get('unverified_search_host_term_learning_weight', -1)) == 0.0
print('[OK] v143 전체 런타임 + v142 자료수집 자가학습 + 수동 공식확인 계약 정상')
print(json.dumps(bundle,ensure_ascii=False))
PY

if command -v node >/dev/null 2>&1; then
  node --check grade_learning_guard_v135.js
  node --check graded_photo_dashboard.js
  node --check manual_official_verify_bridge.js
else
  echo "[INFO] node 없음 · JS 문법검사는 브라우저 로드/서버 정적검사에서 확인"
fi

echo "=== v143 설치 검증 ==="
grep -n 'grade_learning_guard_v135.js' index.html | head -1
grep -n 'tcg_updater_v135.py' START_TCG_UPDATER_ANDROID.sh | head -1
grep -n 'runtime_bundle_guard_v143.py' START_TCG_UPDATER_ANDROID.sh | head -1
grep -n 'collection_learning_hardening_v142.py' START_TCG_UPDATER_ANDROID.sh | head -1
grep -n 'collection_learning_hardening_v142' auto_pipeline_runner.py | head -1
test -s manual_official_proof.py
test -s manual_official_verify_bridge.js
test -s IMPORT_GRADED_LEARNING_FILES.py
test -s START_GRADED_FILE_LEARNING.sh

echo "=== 서버 재시작 ==="
pkill -f 'python.*tcg_updater_v135.py' 2>/dev/null || true
pkill -f 'python.*tcg_updater.py' 2>/dev/null || true
sleep 2
nohup bash START_TCG_UPDATER_ANDROID.sh > TCG_ANDROID_STARTUP.log 2>&1 &
sleep 5

HEALTH="$(curl -s --max-time 5 http://127.0.0.1:8765/api/v135-health || true)"
MODEL="$(curl -s --max-time 5 http://127.0.0.1:8765/api/learning-model-status || true)"
AUDIT="$(curl -s --max-time 5 http://127.0.0.1:8765/api/grade-learning-audit || true)"
MANUAL="$(curl -s --max-time 5 http://127.0.0.1:8765/api/manual-official-proof-status || true)"

echo "HEALTH: $HEALTH"
echo "MODEL: $MODEL"
echo "AUDIT: $AUDIT"
echo "MANUAL: $MANUAL"

python - <<'PY'
import json, urllib.request
checks=(
 ('http://127.0.0.1:8765/api/v135-health','health'),
 ('http://127.0.0.1:8765/api/learning-model-status',None),
 ('http://127.0.0.1:8765/api/grade-learning-audit',None),
 ('http://127.0.0.1:8765/api/manual-official-proof-status','manual'),
)
for url, marker in checks:
    with urllib.request.urlopen(url,timeout=5) as r:
        data=json.loads(r.read().decode('utf-8'))
    assert data.get('ok') is True, (url,data)
    if marker == 'health':
        assert int(data.get('patch') or 0) >= 143, data
        assert int(data.get('runtime_bundle_patch') or 0) >= 143, data
        assert int(data.get('event_collection_patch') or 0) >= 142, data
        assert data.get('runtime_bundle_compatible') is True, data
        assert data.get('search_timeout_circuit_breaker') is True, data
        assert data.get('graded_photo_preflight_allowlisted') is True, data
        assert data.get('verified_reward_term_learning') is True, data
        assert data.get('unique_evidence_host_counting') is True, data
        assert data.get('strict_official_social_url_match') is True, data
        assert data.get('fan_reuse_requires_corroboration_or_watch') is True, data
        assert data.get('manual_official_browser_fallback') is True, data
        assert data.get('manual_official_proof_raw_calibration') is False, data
        assert float(data.get('unverified_reward_learning_weight', -1)) == 0.0, data
        assert float(data.get('unverified_payload_learning_weight', -1)) == 0.0, data
        assert float(data.get('unverified_search_host_term_learning_weight', -1)) == 0.0, data
    if marker == 'manual':
        policy=data.get('policy',{})
        assert policy.get('manual_screenshot_sets_official_result') is False, data
        assert policy.get('manual_screenshot_trains_raw_grade_calibration') is False, data
        assert policy.get('rejected_screenshot_bytes_retained') is False, data
        assert policy.get('proof_upload_rate_limited') is True, data
print('[OK] v143 서버 API + 전체 런타임 + 자료수집/등급사진 수동검증 보안 정상')
PY

echo "[OK] v143 등급측정 + 전체 자료수집/오류복구/행사 검증학습 업그레이드 설치 완료"
echo "- 업데이트 래퍼만 새 버전이고 실제 수집기가 구버전인 혼합 설치를 시작 전에 차단"
echo "- eBay/Amazon 공개검색은 search_exact 경로로 timeout/403/429를 학습하고 불량 경로를 임시 cooldown"
echo "- 같은 검색경로의 반복 timeout을 매 상품마다 무한 반복하지 않고 정상 대체 경로를 우선"
echo "- graded_photo_candidates.json은 자동복구 안전목록/필수 구조 계약을 확인한 뒤 실행"
echo "- 등급사진 수동등록·공식사이트 직접확인·등급완료 파일학습 모듈도 전체 런타임 번들에 포함"
echo "- 수동 공식확인 불일치 캡처 원본은 보존하지 않고 OCR/해시 감사정보만 유지"
echo "- 정상 수동 참고등록은 이후 잘못된 캡처 업로드로 덮어쓰지 않음"
echo "- 수동 공식확인 캡처는 공식검증/RAW 보정학습으로 자동 승격하지 않음"
echo "- 출시 페이지 파서 0건은 입력값 오류가 아니라 원출처 구조변경으로 진단"
echo "- 시장가격/행사/환율은 비정상 신규 결과를 격리하고 기존 검증자료를 유지"
echo "- 포켓몬/원피스/나루토 카드·프로모·한정판·콜라보 증정은 기존 행사 범위 밖이어도 후보 수집"
echo "- 같은 출처의 중복 경로는 독립 출처 수를 부풀리지 않음"
echo "- 미검증 커뮤니티/SNS/검색 후보의 지속 host·검색어 학습 가중치 0.00"
echo "- 공식 SNS는 실제 계정 URL이 일치할 때만 공식 힌트 인정"
echo "- 사용자 체크박스만으로는 등급 학습하지 않음"
echo "- PSA/BGS/CGC/TAG/BRG 공식 인증조회 성공자료만 로컬 검증레지스트리에 저장"
echo "- 기존 로컬 후보/수집이력/학습 JSON은 덮어쓰지 않음"
