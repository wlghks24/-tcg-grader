#!/data/data/com.termux/files/usr/bin/bash
set -eu

OFFICIAL_REPO='wlghks24/-tcg-grader'
OFFICIAL_HTTPS='https://github.com/wlghks24/-tcg-grader.git'

is_official_origin() {
  case "${1:-}" in
    https://github.com/wlghks24/-tcg-grader|https://github.com/wlghks24/-tcg-grader.git|https://github.com/wlghks24/-tcg-grader/|https://github.com/wlghks24/-tcg-grader.git/|git@github.com:wlghks24/-tcg-grader|git@github.com:wlghks24/-tcg-grader.git|ssh://git@github.com/wlghks24/-tcg-grader|ssh://git@github.com/wlghks24/-tcg-grader.git)
      return 0 ;;
    *) return 1 ;;
  esac
}

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

# Recovery executes a script fetched from GitHub, so fail closed if the local
# `origin` was altered to another repository. The actual fetch also uses the
# fixed canonical HTTPS URL rather than trusting `.git/config` for code source.
origin_url="$(git remote get-url origin 2>/dev/null || true)"
if ! is_official_origin "$origin_url"; then
  echo "[안전] origin 원격 저장소가 공식 TCG 저장소($OFFICIAL_REPO)가 아닙니다."
  echo "       현재 origin: ${origin_url:-없음}"
  echo "       복구 스크립트 실행을 중단했습니다."
  exit 12
fi

echo "[복구] GitHub main 최신 업데이트 스크립트를 준비합니다..."
git fetch --prune "$OFFICIAL_HTTPS" main:refs/remotes/origin/main

tmp="$(mktemp "${TMPDIR:-/tmp}/tcg-android-updater.XXXXXX.sh")"
cleanup() { rm -f "$tmp" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

git show origin/main:ANDROID_UPDATE_AND_START.sh > "$tmp"
# Make the tracked updater exactly match the verified official main first. The
# latest updater recognizes this state as an authorized self-bootstrap, restores
# the old HEAD baseline safely, then fast-forwards the whole checkout while
# preserving known runtime JSON snapshots and device-local ignored learning/photos.
git restore --worktree --source=origin/main -- ANDROID_UPDATE_AND_START.sh

echo "[복구] 최신 자기복구 업데이터로 전환합니다."
TCG_REPO_DIR="$repo" bash "$tmp"
