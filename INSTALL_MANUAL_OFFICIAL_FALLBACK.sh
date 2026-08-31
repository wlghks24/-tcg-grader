#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

printf '\n=== 등급사 403/429 수동 공식확인 보강 설치 ===\n'

python -m py_compile tcg_updater_v135.py manual_official_proof.py

if command -v node >/dev/null 2>&1; then
  node --check manual_official_verify_bridge.js
else
  echo '[INFO] node 없음 · JS는 브라우저 로드 시 확인합니다.'
fi

pkill -f 'python.*tcg_updater_v135.py' 2>/dev/null || true
pkill -f 'python.*tcg_updater.py' 2>/dev/null || true
sleep 2
nohup python tcg_updater_v135.py > TCG_ANDROID_STARTUP.log 2>&1 &
sleep 6

printf '\n=== 건강검사 ===\n'
HEALTH="$(curl -fsS --max-time 6 http://127.0.0.1:8765/api/v135-health)"
echo "$HEALTH"
printf '%s' "$HEALTH" | grep -q '"manual_official_browser_fallback": true'
printf '%s' "$HEALTH" | grep -q '"ok": true'

printf '\n=== 수동 공식확인 API ===\n'
curl -fsS --max-time 6 http://127.0.0.1:8765/api/manual-official-proof-status | head -c 1200 || true
printf '\n\n[OK] 설치 완료\n'
printf '%s\n' '- 등급사 자동조회 쿨다운 시 공식사이트 직접 열기 버튼 표시'
printf '%s\n' '- 공식 조회 결과 화면 캡처를 등록하면 등급사+인증번호+등급 OCR 정확일치 검사'
printf '%s\n' '- 캡처 일치 자료는 참고등록만 허용하고 RAW 등급 보정학습에는 사용하지 않음'
printf '%s\n' '- 나중에 라이브 공식조회 성공 시 정상 공식검증 레퍼런스로 승격 가능'
