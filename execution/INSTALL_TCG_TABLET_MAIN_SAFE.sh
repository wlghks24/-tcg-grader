#!/data/data/com.termux/files/usr/bin/bash
# Official-main-only fresh Lenovo/Termux staging; existing data is untouched.
set -euo pipefail
OFFICIAL='https://github.com/wlghks24/-tcg-grader.git'
PIN='3809492f45159d03c41bc18cb7daa0b11b64e6d4'
SHORT="$(printf '%.12s' "$PIN")"
MODE='--check'
if [ "$#" -gt 0 ]; then MODE="$1"; fi

say() { printf '%s\n' "$*"; }
hold() { say "[HOLD] $*" >&2; exit 2; }

case "$MODE" in
  --check|--install) ;;
  *) say 'Usage: bash execution/INSTALL_TCG_TABLET_MAIN_SAFE.sh [--check|--install]'; exit 2 ;;
esac
case "$(printenv PREFIX 2>/dev/null || true)" in
  /data/data/com.termux/files/usr) ;;
  *) hold 'Termux on Android is required.' ;;
esac
case "$HOME" in
  /data/data/com.termux/files/home|/data/data/com.termux/files/home/*) ;;
  *) hold 'Unexpected Termux HOME; no existing data will be modified.' ;;
esac
for cmd in bash git python node mktemp; do
  command -v "$cmd" >/dev/null 2>&1 || hold "Missing dependency: $cmd"
done

DEST="$HOME/tcg_grader_main_$SHORT"
[ ! -e "$DEST" ] && [ ! -L "$DEST" ] || hold "Destination already exists: $DEST"
say "GitHub=$OFFICIAL"
say "Reviewed main=$PIN"
say "Fresh destination=$DEST"
say 'Old projects, photos, labels, model state: leave untouched.'
if [ "$MODE" = '--check' ]; then
  say '[CHECK_OK] Local environment checks passed; no installation performed.'
  exit 0
fi

# The user must explicitly request --install. No third-party shell pipelines.
STAGE="$(mktemp -d "$HOME/.tcg-main-stage-$SHORT.XXXXXXXX")" || hold 'Cannot create staging directory.'
[ -d "$STAGE" ] && [ ! -L "$STAGE" ] || hold 'Unsafe staging directory.'
say "STAGING=$STAGE"
if ! git clone --branch main --single-branch --quiet "$OFFICIAL" "$STAGE/repo"; then
  hold "Cannot clone official main; inspect $STAGE; old projects unchanged."
fi
ACTUAL="$(git -C "$STAGE/repo" rev-parse --verify HEAD)" || hold 'Invalid cloned HEAD.'
TRACKED="$(git -C "$STAGE/repo" rev-parse --verify refs/remotes/origin/main)" || hold 'Invalid origin/main.'
ORIGIN="$(git -C "$STAGE/repo" remote get-url origin)" || hold 'Invalid Git origin.'
[ "$ORIGIN" = "$OFFICIAL" ] || hold 'Nonofficial Git origin.'
[ "$ACTUAL" = "$PIN" ] && [ "$TRACKED" = "$PIN" ] || hold "Unreviewed main SHA $ACTUAL; refuse automatic install."
if ! (cd "$STAGE/repo" && python -m pip install --disable-pip-version-check -r requirements.txt); then
  hold "Required Python dependencies unavailable; inspect $STAGE."
fi
if ! (cd "$STAGE/repo" && bash VERIFY_TABLET_FINAL.sh); then
  hold "Nine-stage tablet verification failed; inspect $STAGE. No server started."
fi
[ ! -e "$DEST" ] && [ ! -L "$DEST" ] || hold "Destination appeared during validation."
mv -- "$STAGE/repo" "$DEST" || hold "Cannot finalize staging; inspect $STAGE."
rmdir -- "$STAGE" 2>/dev/null || true
say "[STAGED_OK] $DEST"
say "Manual start only: cd '$DEST' && bash START_TCG_UPDATER_ANDROID.sh"
say 'Browser after startup: http://127.0.0.1:8765/index.html'
say 'Keep existing TCG server stopped before starting this new server.'
say 'Market snapshot freshness and physical Lenovo verification remain independent.'
