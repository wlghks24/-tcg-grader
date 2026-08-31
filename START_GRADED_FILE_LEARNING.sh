#!/data/data/com.termux/files/usr/bin/bash
set -eu
cd "$(dirname "$0")"

mkdir -p GRADE_TRAINING_INBOX/drop/pokemon
mkdir -p GRADE_TRAINING_INBOX/drop/onepiece
mkdir -p GRADE_TRAINING_INBOX/drop/naruto

printf '\n=== 등급완료 카드 파일 학습 ===\n'
printf '사진을 아래 폴더에 넣으세요.\n'
printf '  포켓몬: %s/GRADE_TRAINING_INBOX/drop/pokemon\n' "$PWD"
printf '  원피스: %s/GRADE_TRAINING_INBOX/drop/onepiece\n' "$PWD"
printf '  나루토: %s/GRADE_TRAINING_INBOX/drop/naruto\n' "$PWD"
printf '\n공식 인증조회는 안전 제한을 지키며 이번 실행 최대 6건 처리합니다.\n\n'

python IMPORT_GRADED_LEARNING_FILES.py --verify-limit 6

printf '\n=== 완료 ===\n'
printf '상세결과: %s/graded_file_learning_report.json\n' "$PWD"
printf '대기 항목이 있으면 나중에 이 파일을 다시 실행하면 이어서 처리됩니다.\n'
