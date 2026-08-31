#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

printf '\n=== 등급사진 수동검증 전용 + 인증번호 앞뒤사진 분류 설치 ===\n'

export TCG_DISABLE_AUTO_GRADER_LOOKUP=1

python -m py_compile \
  tcg_updater_v135.py \
  manual_official_proof.py \
  manual_collection_mode.py \
  graded_photo_manual_pair_queue.py \
  grading_cert_verifier.py \
  runtime_bundle_guard_v143.py \
  test_manual_official_proof.py \
  test_manual_collection_mode.py \
  test_manual_pair_queue.py \
  test_grading_cert_verifier.py

python -m unittest -v \
  test_grading_cert_verifier.py \
  test_manual_collection_mode.py \
  test_manual_pair_queue.py \
  test_manual_official_proof.py \
  test_runtime_bundle_guard_v143.py

python - <<'PY'
import grading_cert_verifier as verifier
import manual_collection_mode as manual_mode
import runtime_bundle_guard_v143 as guard
import graded_photo_manual_pair_queue as pair_queue
status=guard.require_compatible()
contracts=status.get('contracts',{})
mode=manual_mode.status()
assert contracts.get('manual_official_fallback') is True, status
assert contracts.get('manual_proof_raw_calibration') is False, status
assert contracts.get('manual_proof_rejected_bytes_retained') is False, status
assert contracts.get('automatic_grader_lookup_disabled') is True, status
assert contracts.get('manual_registration_auto_lookup_disabled') is True, status
assert contracts.get('certified_front_back_pair_only') is True, status
assert contracts.get('manual_pair_grouped_by_game_and_grader') is True, status
assert verifier.automatic_lookup_disabled() is True
assert mode.get('collector_manual_only') is True, mode
assert mode.get('manual_registration_manual_only') is True, mode
assert mode.get('collector_syncs_manual_pairs') is True, mode
assert str(pair_queue.ANDROID_ROOT) == '/storage/emulated/0/Download/TCG등급학습'
assert '/sdcard' not in str(pair_queue.ANDROID_ROOT)
print('[OK] 자동 등급사 조회 OFF + 인증번호/앞뒤사진 + 게임/등급사 분류 계약 정상')
print('[OK] Android 저장경로는 /sdcard 심볼릭링크 대신 /storage/emulated/0 사용')
PY

if command -v node >/dev/null 2>&1; then
  node --check graded_photo_dashboard.js
  node --check manual_official_verify_bridge.js
else
  echo '[INFO] node 없음 · JS는 브라우저 로드 시 확인합니다.'
fi

pkill -f 'graded_photo_manual_pair_queue.py --watch' 2>/dev/null || true
pkill -f 'python.*tcg_updater_v135.py' 2>/dev/null || true
pkill -f 'python.*tcg_updater.py' 2>/dev/null || true
sleep 2
nohup bash START_TCG_UPDATER_ANDROID.sh > TCG_ANDROID_STARTUP.log 2>&1 &
sleep 7

printf '\n=== 건강검사 ===\n'
HEALTH="$(curl -fsS --max-time 6 http://127.0.0.1:8765/api/v135-health)"
echo "$HEALTH"
printf '%s' "$HEALTH" | grep -q '"manual_official_browser_fallback": true'
printf '%s' "$HEALTH" | grep -q '"manual_official_proof_raw_calibration": false'
printf '%s' "$HEALTH" | grep -q '"runtime_bundle_compatible": true'
printf '%s' "$HEALTH" | grep -q '"ok": true'

printf '\n=== 수동 공식확인 API ===\n'
MANUAL="$(curl -fsS --max-time 6 http://127.0.0.1:8765/api/manual-official-proof-status)"
echo "$MANUAL" | head -c 1600
printf '\n'
printf '%s' "$MANUAL" | grep -q '"manual_screenshot_sets_official_result": false'
printf '%s' "$MANUAL" | grep -q '"manual_screenshot_trains_raw_grade_calibration": false'
printf '%s' "$MANUAL" | grep -q '"rejected_screenshot_bytes_retained": false'
printf '%s' "$MANUAL" | grep -q '"proof_upload_rate_limited": true'

printf '\n=== 앞뒤사진 수동대기 분류기 ===\n'
PAIR_OUTPUT="$(python graded_photo_manual_pair_queue.py 2>&1)" || {
  printf '%s\n' "$PAIR_OUTPUT"
  echo '[오류] 앞뒤사진 수동대기 분류기 실행 실패'
  exit 1
}
printf '%s\n' "$PAIR_OUTPUT"
if ! printf '%s' "$PAIR_OUTPUT" | grep -Fq '/storage/emulated/0/Download/TCG등급학습'; then
  echo '[오류] Android Download 폴더 안전쓰기 검사에 실패했습니다.'
  echo '[조치] Termux에서 termux-setup-storage 실행 → 파일/사진 접근 허용 → 이 설치 스크립트를 다시 실행하세요.'
  echo '[안전] 앱 내부 임시폴더로 조용히 폴백한 상태를 설치완료로 처리하지 않습니다.'
  exit 1
fi

printf '\n[OK] 설치 완료\n'
printf '%s\n' '- PSA/BGS/CGC/TAG/BRG 자동 인증사이트 조회 완전 비활성화'
printf '%s\n' '- 포켓몬/원피스/나루토 중 인증번호 + 앞면 + 뒷면이 모두 확인된 후보만 저장'
printf '%s\n' '- /storage/emulated/0/Download/TCG등급학습/<게임>/<등급사>/수동등록대기/<카드>/ 로 자동 분류'
printf '%s\n' '- /sdcard 심볼릭링크 별칭은 보안 atomic writer와 충돌하므로 사용하지 않음'
printf '%s\n' '- 각 게임/등급사 폴더에 수동등록목록.json 생성'
printf '%s\n' '- 단일사진·인증번호 없음·지원하지 않는 등급사는 자동 저장하지 않음'
printf '%s\n' '- 공식사이트는 사용자가 직접 열어 확인하고 확인화면을 수동등록'
printf '%s\n' '- 수동 확인자료는 RAW 등급 보정학습으로 자동 승격하지 않음'
