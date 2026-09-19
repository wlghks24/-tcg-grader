#!/data/data/com.termux/files/usr/bin/bash
set -u
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
cd "${TCG_REPO_DIR:-$SCRIPT_DIR}" || exit 1

LOCK_GUARD="$HOME/.local/state/tcg-grader/gdrive-sync/wrapper.lock"
mkdir -p "$(dirname "$LOCK_GUARD")"
if ! mkdir "$LOCK_GUARD" 2>/dev/null; then
  exit 0
fi
trap 'rm -rf "$LOCK_GUARD" 2>/dev/null || true' EXIT INT TERM

exec python tablet_gdrive_sync.py "$@"
