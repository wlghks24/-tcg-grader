#!/data/data/com.termux/files/usr/bin/bash
set -eu

if ! command -v git >/dev/null 2>&1; then
  echo "[오류] git 명령을 찾을 수 없습니다."
  exit 1
fi

repo="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$repo" ] || [ ! -d "$repo/.git" ]; then
  echo "[오류] TCG Git 저장소 폴더 안에서 실행해 주세요."
  exit 1
fi
cd "$repo"

echo "[복구] GitHub main 최신 업데이트 스크립트를 준비합니다..."
git fetch origin main --prune

tmp="$(mktemp "${TMPDIR:-/tmp}/tcg-android-updater.XXXXXX.sh")"
cleanup() { rm -f "$tmp" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

git show origin/main:ANDROID_UPDATE_AND_START.sh > "$tmp"
# Make the tracked updater exactly match origin/main first. The latest updater
# recognizes this state as an authorized self-bootstrap, restores the old HEAD
# baseline safely, then fast-forwards the whole checkout while preserving known
# runtime JSON snapshots and device-local ignored learning/photos.
git restore --worktree --source=origin/main -- ANDROID_UPDATE_AND_START.sh

echo "[복구] 최신 자기복구 업데이터로 전환합니다."
TCG_REPO_DIR="$repo" bash "$tmp"
