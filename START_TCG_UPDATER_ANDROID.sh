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
python auto_update_all.py || true
python verify_all.py || echo "검사보고서에서 수정 필요 항목을 확인하세요."
if command -v termux-wake-lock >/dev/null 2>&1; then
  termux-wake-lock || true
  trap 'termux-wake-unlock >/dev/null 2>&1 || true' EXIT INT TERM
fi
python tcg_updater.py
