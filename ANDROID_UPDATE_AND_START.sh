#!/data/data/com.termux/files/usr/bin/bash
set -u
cd "$(dirname "$0")"

# Safe tablet updater: only fast-forward a clean tracked checkout. Runtime data,
# logs and untracked learning files are never reset or deleted here.
UPDATE_LOCK_DIR=".tcg_android_update.lock"
UPDATE_LOCK_PID="$UPDATE_LOCK_DIR/pid"

cleanup_update_lock() {
  rm -rf "$UPDATE_LOCK_DIR" 2>/dev/null || true
}

acquire_update_lock() {
  if mkdir "$UPDATE_LOCK_DIR" 2>/dev/null; then
    printf '%s\n' "$$" > "$UPDATE_LOCK_PID"
    return 0
  fi
  old_pid=""
  if [ -r "$UPDATE_LOCK_PID" ]; then
    old_pid="$(cat "$UPDATE_LOCK_PID" 2>/dev/null || true)"
  fi
  case "$old_pid" in
    ''|*[!0-9]*) old_pid="" ;;
  esac
  if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[OK] Android 업데이트 작업이 이미 실행 중입니다(PID $old_pid)."
    exit 0
  fi
  rm -rf "$UPDATE_LOCK_DIR" 2>/dev/null || true
  mkdir "$UPDATE_LOCK_DIR" 2>/dev/null || {
    echo "[안내] 업데이트 잠금을 만들 수 없어 현재 버전으로 서버를 시작합니다."
    return 1
  }
  printf '%s\n' "$$" > "$UPDATE_LOCK_PID"
}

LOCKED=0
if acquire_update_lock; then
  LOCKED=1
fi
trap '[ "${LOCKED:-0}" = "1" ] && cleanup_update_lock || true' EXIT INT TERM

before="local"
after="local"
updated=0

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  before="$(git rev-parse --short=8 HEAD 2>/dev/null || echo local)"
  branch="$(git branch --show-current 2>/dev/null || true)"
  if [ "$branch" != "main" ]; then
    echo "[안내] 현재 브랜치가 main이 아닙니다(${branch:-detached}). 자동 업데이트는 건너뜁니다."
  elif ! git diff --quiet --ignore-submodules -- || ! git diff --cached --quiet --ignore-submodules --; then
    echo "[안전] 추적 파일에 로컬 수정이 있어 자동 업데이트를 건너뜁니다. 파일은 삭제/초기화하지 않습니다."
  else
    echo "[업데이트] GitHub main 최신 상태를 확인합니다..."
    if git fetch origin main --prune; then
      local_head="$(git rev-parse HEAD 2>/dev/null || true)"
      remote_head="$(git rev-parse origin/main 2>/dev/null || true)"
      if [ -n "$remote_head" ] && [ "$local_head" != "$remote_head" ]; then
        if git merge --ff-only origin/main; then
          updated=1
        else
          echo "[안전] fast-forward 업데이트가 불가능해 현재 버전을 유지합니다. reset/강제병합은 하지 않습니다."
        fi
      else
        echo "[OK] 이미 최신 main입니다."
      fi
    else
      echo "[안내] 네트워크/GitHub 연결 문제로 업데이트 확인을 건너뜁니다. 현재 버전으로 시작합니다."
    fi
  fi
  after="$(git rev-parse --short=8 HEAD 2>/dev/null || echo local)"
fi

if [ "$updated" = "1" ]; then
  echo "[OK] Android 코드 업데이트 완료: $before -> $after"
else
  echo "[OK] Android 실행 빌드: $after"
fi

if [ ! -s "START_TCG_UPDATER_ANDROID.sh" ]; then
  echo "[오류] START_TCG_UPDATER_ANDROID.sh 파일이 없습니다."
  exit 1
fi

# The launcher itself owns the server singleton lock and safely releases stale
# port 8765 processes, so this wrapper never uses broad kill/reset commands.
exec bash START_TCG_UPDATER_ANDROID.sh
