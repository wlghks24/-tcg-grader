#!/data/data/com.termux/files/usr/bin/bash
set -u
cd "$(dirname "$0")"

# Do not hard-code an old app version in the startup banner.
# Show the exact Git commit currently installed on this tablet so users can
# immediately confirm whether the local server matches the latest checkout.
if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  TCG_BUILD="$(git rev-parse --short=8 HEAD 2>/dev/null || true)"
  TCG_BRANCH="$(git branch --show-current 2>/dev/null || true)"
else
  TCG_BUILD=""
  TCG_BRANCH=""
fi
[ -n "${TCG_BUILD}" ] || TCG_BUILD="local"
[ -n "${TCG_BRANCH}" ] || TCG_BRANCH="unknown"

echo "========================================"
echo " TCG Android 태블릿 서버 시작"
echo " 현재 빌드: ${TCG_BUILD} · 브랜치: ${TCG_BRANCH}"
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
if [ -f "storage_optimizer.py" ]; then
  echo "저장공간을 안전하게 최적화합니다..."
  python storage_optimizer.py || echo "[안내] 최적화 일부를 건너뛰고 서버를 시작합니다."
fi
# Guarantee one graded-photo discovery pass when the corpus is missing/stale/empty.
# It runs in background so the local server is not delayed; the regular 7-step 6-hour job remains active.
if [ -f "graded_photo_bootstrap.py" ] && [ -f "graded_photo_multi_source.py" ]; then
  echo "7단계 등급사진 수집 상태를 확인합니다..."
  (python graded_photo_bootstrap.py > graded_photo_bootstrap.log 2>&1) &
fi

echo "로컬 서버를 먼저 시작합니다. 자료 수집은 백그라운드에서 자동 실행됩니다."
python tcg_updater.py
