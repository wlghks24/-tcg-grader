#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"
BASE_URL="https://raw.githubusercontent.com/wlghks24/-tcg-grader/main"
STAMP="$(date +%Y%m%d_%H%M%S)"

backup_if_exists() {
  if [ -f "$1" ]; then
    cp -p "$1" "$1.before_photo_cleanup_${STAMP}"
  fi
}

backup_if_exists storage_optimizer.py
backup_if_exists safe_photo_cleanup.py
backup_if_exists test_safe_photo_cleanup_v132.py

for name in safe_photo_cleanup.py storage_optimizer.py test_safe_photo_cleanup_v132.py; do
  tmp=".${name}.download.tmp"
  rm -f "$tmp"
  curl -L --fail --retry 3 --retry-delay 2 -H 'Cache-Control: no-cache' \
    "${BASE_URL}/${name}?$(date +%s)" -o "$tmp"
  test -s "$tmp"
  mv "$tmp" "$name"
done

python -m py_compile safe_photo_cleanup.py storage_optimizer.py test_safe_photo_cleanup_v132.py
python -m unittest -v test_safe_photo_cleanup_v132.py

echo "=== v132 안전 정리 사전검사(dry-run: 실제 삭제 없음) ==="
python safe_photo_cleanup.py

echo "[OK] v132 학습사진 안전정리 검토·보강 완료"
echo "- 공식검증/참고학습/train/validation/holdout/확인대기 사진: 보호"
echo "- 확인대기 사진은 중복이어도 삭제 금지"
echo "- 명시적 검증실패 사진도 14일 유예기간 전에는 삭제 금지"
echo "- 보호 레지스트리가 손상/읽기실패면 삭제기능 자동중지(fail-closed)"
echo "- graded_photo_cache/downloaded_graded_photos 등 복합 폴더명도 정상 인식"
echo "- 프로그램 밖 Download/DCIM 같은 개인 폴더: 자동검색/삭제 안 함"
echo "- 다음 서버 시작부터 storage_optimizer가 안전 판정 항목만 자동 정리"
echo "- 결과기록: photo_cleanup_report.json"
