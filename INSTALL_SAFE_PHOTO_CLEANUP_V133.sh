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

for name in \
  safe_photo_cleanup.py \
  storage_optimizer.py \
  test_safe_photo_cleanup.py \
  test_safe_photo_cleanup_v132.py \
  test_safe_photo_cleanup_v133.py; do
  backup_if_exists "$name"
done

for name in \
  safe_photo_cleanup.py \
  storage_optimizer.py \
  test_safe_photo_cleanup.py \
  test_safe_photo_cleanup_v132.py \
  test_safe_photo_cleanup_v133.py; do
  tmp=".${name}.download.tmp"
  rm -f "$tmp"
  curl -L --fail --retry 3 --retry-delay 2 -H 'Cache-Control: no-cache' \
    "${BASE_URL}/${name}?$(date +%s)" -o "$tmp"
  test -s "$tmp"
  mv "$tmp" "$name"
done

python -m py_compile \
  safe_photo_cleanup.py storage_optimizer.py \
  test_safe_photo_cleanup.py test_safe_photo_cleanup_v132.py test_safe_photo_cleanup_v133.py

python - <<'PY'
import safe_photo_cleanup as cleanup
assert cleanup.DEFAULT_CACHE_DAYS >= 14
assert cleanup.REPORT_PATH.name == 'photo_cleanup_report.json'
print('[OK] v133 정책 확인: 수동/학습사진 보호, 오래된 미참조 캐시만 정리')
PY

python -m unittest -v \
  test_safe_photo_cleanup.py \
  test_safe_photo_cleanup_v132.py \
  test_safe_photo_cleanup_v133.py

echo "=== v133 안전 정리 사전검사(dry-run: 실제 사진 삭제 없음) ==="
python safe_photo_cleanup.py

python - <<'PY'
import json
from pathlib import Path
p=Path('photo_cleanup_report.json')
try:
    data=json.loads(p.read_text(encoding='utf-8'))
except Exception as exc:
    print('[WARN] 사전검사 보고서를 읽지 못했습니다:', type(exc).__name__)
else:
    guard=data.get('registry_guard') or {}
    summary=data.get('summary') or {}
    print('[INFO] 레지스트리 삭제허용:', guard.get('destructive_allowed'))
    print('[INFO] 스캔:', summary.get('scanned_images',0),
          '보호:', summary.get('protected_images',0),
          '삭제후보:', summary.get('delete_candidates',0),
          '해시보호:', summary.get('hash_guarded_images',0))
    errors=guard.get('errors') or []
    if errors:
        print('[SAFE] 보호자료 이상 감지로 실제 삭제는 자동 중지됩니다:', ', '.join(errors[:5]))
PY

echo "[OK] v133 학습사진 안전정리 최종 검토판 설치 완료"
echo "- 수동등록/검증대기/검증실패 사진: 자동삭제 안 함"
echo "- train/validation/holdout/reference/official/calibration 사진: 자동삭제 안 함"
echo "- 미검증/격리 후보라도 레지스트리에 경로·파일명·SHA가 있으면 보호"
echo "- 일반 grading_photos/graded_photos 폴더: 자동삭제 안 함"
echo "- graded_photo_cache/downloaded_graded_photos 등 명시적 캐시만 정리 대상"
echo "- 캐시도 기본 14일 이상 + 미참조 조건일 때만 삭제 가능"
echo "- 해시읽기 실패/파일변경/심볼릭링크/레지스트리 손상 시 삭제 중지 또는 보존"
echo "- 프로그램 밖 Download/DCIM 등 개인 폴더는 검색하지 않음"
echo "- 설치 단계는 dry-run이라 실제 사진은 삭제하지 않음"
echo "- 결과기록: photo_cleanup_report.json"
