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
backup_if_exists test_safe_photo_cleanup.py

for name in safe_photo_cleanup.py storage_optimizer.py test_safe_photo_cleanup.py; do
  tmp=".${name}.download.tmp"
  curl -L --fail -H 'Cache-Control: no-cache' "${BASE_URL}/${name}?$(date +%s)" -o "$tmp"
  mv "$tmp" "$name"
done

python -m py_compile safe_photo_cleanup.py storage_optimizer.py test_safe_photo_cleanup.py
python -m unittest -v test_safe_photo_cleanup.py

echo "=== 안전 정리 사전검사(dry-run: 실제 삭제 없음) ==="
python safe_photo_cleanup.py

echo "[OK] v131 학습사진 안전정리 설치 완료"
echo "- 공식검증/참고학습/train/validation/holdout/확인대기 사진: 보호"
echo "- 빈 파일/확정 중복/14일 지난 명시적 거부/7일 지난 미참조 캐시: 정리 대상"
echo "- 프로그램 밖 Download/DCIM 같은 개인 폴더: 자동검색/삭제 안 함"
echo "- 다음 서버 시작부터 storage_optimizer가 안전 판정 항목만 자동 정리"
echo "- 지금 즉시 실제 정리하려면: python safe_photo_cleanup.py --apply"
echo "- 결과기록: photo_cleanup_report.json"
