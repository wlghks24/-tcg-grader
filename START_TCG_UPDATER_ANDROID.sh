#!/data/data/com.termux/files/usr/bin/bash
set -u
cd "$(dirname "$0")"

echo "========================================"
echo " TCG v31 Android 태블릿 서버 시작"
echo "========================================"

if ! command -v python >/dev/null 2>&1; then
  echo "Python을 처음 설치합니다. 잠시 기다려 주세요."
  pkg update -y || exit 1
  pkg install python -y || exit 1
fi

echo "서버를 종료하려면 Ctrl+C를 누르세요."
if [ ! -f "tcg_updater.py" ] || [ ! -f "index.html" ]; then
  echo "[오류] 프로그램 필수 파일이 없습니다. GitHub 저장소를 다시 다운로드하세요."
  exit 1
fi
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
  trap 'termux-wake-unlock >/dev/null 2>&1 || true' EXIT INT TERM
fi
echo "로컬 서버를 먼저 시작합니다. 자료 수집은 백그라운드에서 자동 실행됩니다."
python tcg_updater.py
