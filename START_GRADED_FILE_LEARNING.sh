#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

LOCAL_INBOX="$PWD/GRADE_TRAINING_INBOX/drop"
ANDROID_INBOX="/storage/emulated/0/Download/TCG등급학습"

mkdir -p "$LOCAL_INBOX/pokemon" "$LOCAL_INBOX/onepiece" "$LOCAL_INBOX/naruto"

if [ -d /storage/emulated/0/Download ] && [ -r /storage/emulated/0/Download ]; then
  mkdir -p "$ANDROID_INBOX/pokemon" "$ANDROID_INBOX/onepiece" "$ANDROID_INBOX/naruto" 2>/dev/null || true
fi

if [ -d "$ANDROID_INBOX" ] && [ -r "$ANDROID_INBOX" ]; then
  SOURCE="$ANDROID_INBOX"
else
  SOURCE="$LOCAL_INBOX"
fi

printf '\n=== 등급완료 카드 파일 학습 · OCR v148 ===\n'
printf '사용 폴더: %s\n' "$SOURCE"
printf '사진을 게임별 폴더에 넣으세요.\n'
printf '  포켓몬: %s/pokemon\n' "$SOURCE"
printf '  원피스: %s/onepiece\n' "$SOURCE"
printf '  나루토: %s/naruto\n' "$SOURCE"
printf '\nPSA/BGS/CGC/TAG/BRG 자동 인증사이트 조회는 하지 않습니다.\n'
printf 'OCR v148로 등급사·등급·인증번호를 읽고 공식사이트 수동확인 대기로 보냅니다.\n\n'

# Import in the same Python process after applying manual-only mode. This makes
# the file importer use the same adaptive OCR as the browser upload path and
# prevents the legacy importer from contacting grader certification sites.
python - "$SOURCE" <<'PY'
import sys
source=sys.argv[1]
import manual_collection_mode as manual_mode
status=manual_mode.apply()
if not status.get('ok'):
    raise SystemExit('[오류] 수동검증/OCR v148 모드를 적용하지 못했습니다.')
import IMPORT_GRADED_LEARNING_FILES as importer
# The old delay existed for live provider requests. They are OFF in manual mode,
# so do not waste 5.2 seconds between local OCR items.
importer.SAFE_PROVIDER_PAUSE_SECONDS=0.0
sys.argv=['IMPORT_GRADED_LEARNING_FILES.py',source,'--verify-limit','12']
raise SystemExit(importer.main())
PY

printf '\n=== 완료 ===\n'
printf '상세결과: %s/graded_file_learning_report.json\n' "$PWD"
printf '한 번에 최대 12개 사진을 OCR 처리합니다. 더 있으면 같은 파일을 다시 실행하면 이어서 처리됩니다.\n'
printf '공식 등급 확인은 사이트에서 직접 확인한 뒤 수동등록 기능을 사용하세요.\n'