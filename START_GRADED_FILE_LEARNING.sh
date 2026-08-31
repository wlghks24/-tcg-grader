#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

LOCAL_INBOX="$PWD/GRADE_TRAINING_INBOX/drop"
ANDROID_INBOX="/sdcard/Download/TCG등급학습"

mkdir -p "$LOCAL_INBOX/pokemon" "$LOCAL_INBOX/onepiece" "$LOCAL_INBOX/naruto"

if [ -d /sdcard/Download ] && [ -r /sdcard/Download ]; then
  mkdir -p "$ANDROID_INBOX/pokemon" "$ANDROID_INBOX/onepiece" "$ANDROID_INBOX/naruto" 2>/dev/null || true
fi

if [ -d "$ANDROID_INBOX" ] && [ -r "$ANDROID_INBOX" ]; then
  SOURCE="$ANDROID_INBOX"
else
  SOURCE="$LOCAL_INBOX"
fi

printf '\n=== 등급완료 카드 파일 학습 ===\n'
printf '사용 폴더: %s\n' "$SOURCE"
printf '사진을 게임별 폴더에 넣으세요.\n'
printf '  포켓몬: %s/pokemon\n' "$SOURCE"
printf '  원피스: %s/onepiece\n' "$SOURCE"
printf '  나루토: %s/naruto\n' "$SOURCE"
printf '\n공식 인증조회는 안전 제한을 지키며 이번 실행 최대 6건 처리합니다.\n\n'

python IMPORT_GRADED_LEARNING_FILES.py "$SOURCE" --verify-limit 6

printf '\n=== 완료 ===\n'
printf '상세결과: %s/graded_file_learning_report.json\n' "$PWD"
printf '대기 항목이 있으면 나중에 이 파일을 다시 실행하면 이어서 처리됩니다.\n'
