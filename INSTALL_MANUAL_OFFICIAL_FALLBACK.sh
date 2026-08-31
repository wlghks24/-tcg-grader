#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

printf '\n=== 등급사진 수동검증 전용 + 앞뒤사진 2장 + OCR v147 설치 ===\n'

export TCG_DISABLE_AUTO_GRADER_LOOKUP=1

python -m py_compile \
  tcg_updater_v135.py \
  manual_official_proof.py \
  manual_collection_mode.py \
  manual_dual_photo_registration.py \
  ocr_accuracy_boost_v147.py \
  public_ocr_accuracy_boost_v147.py \
  graded_photo_manual_pair_queue.py \
  grading_cert_verifier.py \
  runtime_bundle_guard_v143.py \
  test_manual_official_proof.py \
  test_manual_collection_mode.py \
  test_manual_pair_queue.py \
  test_grading_cert_verifier.py \
  test_ocr_accuracy_boost_v147.py

python -m unittest -v \
  test_ocr_accuracy_boost_v147.py \
  test_grading_cert_verifier.py \
  test_manual_collection_mode.py \
  test_manual_pair_queue.py \
  test_manual_official_proof.py \
  test_runtime_bundle_guard_v143.py

python - <<'PY'
import grading_cert_verifier as verifier
import manual_collection_mode as manual_mode
import manual_dual_photo_registration as dual_photo
import ocr_accuracy_boost_v147 as ocr_boost
import public_ocr_accuracy_boost_v147 as public_ocr
import runtime_bundle_guard_v143 as guard
import graded_photo_manual_pair_queue as pair_queue
status=guard.require_compatible()
contracts=status.get('contracts',{})
mode=manual_mode.status()
dual=dual_photo.status()
ocr=ocr_boost.status()
public=public_ocr.status()
assert contracts.get('manual_official_fallback') is True, status
assert contracts.get('manual_proof_raw_calibration') is False, status
assert contracts.get('manual_proof_rejected_bytes_retained') is False, status
assert contracts.get('automatic_grader_lookup_disabled') is True, status
assert contracts.get('manual_registration_auto_lookup_disabled') is True, status
assert contracts.get('certified_front_back_pair_only') is True, status
assert verifier.automatic_lookup_disabled() is True
assert mode.get('collector_manual_only') is True, mode
assert mode.get('manual_registration_manual_only') is True, mode
assert mode.get('collector_syncs_manual_pairs') is True, mode
assert mode.get('manual_front_back_upload') is True, mode
assert mode.get('back_stored_separately') is True, mode
assert mode.get('grouped_by_game_only') is True, mode
assert mode.get('grader_subfolders_created') is False, mode
assert dual.get('ocr_accuracy_boost') is True, dual
assert dual.get('public_ocr_accuracy_boost') is True, dual
assert ocr.get('ok') is True and ocr.get('engine') == 'slab-ocr-accuracy-v147', ocr
assert public.get('ok') is True, public
assert str(pair_queue.ANDROID_ROOT) == '/storage/emulated/0/Download/TCG등급학습'
assert '/sdcard' not in str(pair_queue.ANDROID_ROOT)
probe=pair_queue._pair_folder(pair_queue.ANDROID_ROOT,'pokemon','0123456789abcdefabcd')
assert str(probe).endswith('/pokemon/수동등록대기/0123456789abcdefabcd')
assert '/pokemon/PSA/' not in str(probe)
print('[OK] 수동등록 앞면+뒷면 2장 저장 계약 정상')
print('[OK] OCR v147: 적응형 다중크롭 + 등급사별 인증번호 길이 + OCR 오인문자 보정')
print('[OK] 수동등록/자동수집 등급사진 모두 OCR v147 적용')
print('[OK] 게임별 폴더만 사용하고 등급사는 메타데이터로 보존')
PY

# 현재 index.html에 앞뒤사진 업로드 UI 브리지를 중복 없이 추가하고
# 버전 쿼리를 갱신해 Android/WebView 브라우저 캐시가 구버전 JS를 잡지 않게 합니다.
python - <<'PY'
from pathlib import Path
import re
p=Path('index.html')
text=p.read_text(encoding='utf-8')
tag='<script src="./manual_dual_photo_bridge.js?v=147"></script>'
pattern=r'<script\s+src=["\']\./manual_dual_photo_bridge\.js(?:\?v=\d+)?["\']\s*></script>'
if re.search(pattern,text):
    text=re.sub(pattern,tag,text,count=1)
elif '</body>' in text:
    text=text.replace('</body>',tag+'\n</body>',1)
elif '</html>' in text:
    text=text.replace('</html>',tag+'\n</html>',1)
else:
    text += '\n'+tag+'\n'
p.write_text(text,encoding='utf-8')
print('[OK] 앞뒤사진 UI 브리지:', text.count('manual_dual_photo_bridge.js'), 'v147')
PY

if command -v node >/dev/null 2>&1; then
  node --check graded_photo_dashboard.js
  node --check manual_official_verify_bridge.js
  node --check manual_dual_photo_bridge.js
else
  echo '[INFO] node 없음 · JS는 브라우저 로드 시 확인합니다.'
fi

test -s manual_dual_photo_registration.py
test -s manual_dual_photo_bridge.js
test -s ocr_accuracy_boost_v147.py
test -s public_ocr_accuracy_boost_v147.py
grep -q 'manual_dual_photo_bridge.js?v=147' index.html

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

printf '\n=== 앞뒤사진 수동대기 게임별 분류기 ===\n'
PAIR_OUTPUT="$(python graded_photo_manual_pair_queue.py 2>&1)" || {
  printf '%s\n' "$PAIR_OUTPUT"
  echo '[오류] 앞뒤사진 수동대기 분류기 실행 실패'
  exit 1
}
printf '%s\n' "$PAIR_OUTPUT"
if ! printf '%s' "$PAIR_OUTPUT" | grep -Fq '/storage/emulated/0/Download/TCG등급학습'; then
  echo '[오류] Android Download 폴더 안전쓰기 검사에 실패했습니다.'
  echo '[조치] Termux에서 termux-setup-storage 실행 → 파일/사진 접근 허용 → 이 설치 스크립트를 다시 실행하세요.'
  exit 1
fi
if ! printf '%s' "$PAIR_OUTPUT" | grep -Fq 'PSA/BGS 등급사 하위폴더 없음'; then
  echo '[오류] 게임별 단순 폴더 정책이 적용되지 않았습니다.'
  exit 1
fi

printf '\n[OK] 설치 완료\n'
printf '%s\n' '- OCR v147: 라벨 위치별 다중크롭을 필요한 만큼만 실행하여 인식률 향상'
printf '%s\n' '- O/0, I/1, L/1, S/5, B/8 등 인증번호 OCR 혼동을 숫자 후보 안에서만 안전 보정'
printf '%s\n' '- PSA/BGS/CGC/TAG/BRG별 인증번호 길이 규칙으로 엉뚱한 숫자 채택 감소'
printf '%s\n' '- 수동등록 화면에서 등급 슬랩 앞면 + 뒷면 사진을 모두 필수 선택'
printf '%s\n' '- 앞면은 OCR용, 뒷면은 같은 등록번호의 별도 증빙사진으로 안전 저장'
printf '%s\n' '- 동일한 앞/뒤 사진 선택은 거절'
printf '%s\n' '- PSA/BGS/CGC/TAG/BRG 자동 인증사이트 조회 완전 비활성화'
printf '%s\n' '- 포켓몬/원피스/나루토 중 인증번호 + 앞면 + 뒷면이 모두 확인된 자동수집 후보만 저장'
printf '%s\n' '- 저장은 pokemon / onepiece / naruto 게임별 폴더만 사용'
printf '%s\n' '- 공식사이트는 사용자가 직접 열어 확인하고 확인화면을 수동등록'
printf '%s\n' '- 수동 확인자료는 RAW 등급 보정학습으로 자동 승격하지 않음'