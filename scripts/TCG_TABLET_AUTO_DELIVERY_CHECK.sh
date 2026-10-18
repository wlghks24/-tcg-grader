#!/data/data/com.termux/files/usr/bin/bash
# Device-side verification and optional installer for both TCG update routes.
# No git reset, no file purge, no synthesized GPT result.
set -u
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
REMOTE="${TCG_GDRIVE_REMOTE:-gdrive}"
REMOTE_ROOT="${TCG_GDRIVE_ROOT:-TCG_Grader_Sync}"
mode="${1:-status}"

status() {
  printf '\n=== TCG GitHub main / Termux 예약 상태 ===\n'
  git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo "GIT=not-installed"
  if [ -f "$ROOT/TABLET_SCHEDULED_UPDATE.sh" ]; then
    bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" status || true
  else
    echo "GITHUB_SCHEDULE=script-missing"
  fi
  printf '\n=== GPT->Drive->Tablet 데이터 수신 상태 ===\n'
  if command -v crontab >/dev/null 2>&1 && crontab -l 2>/dev/null | grep -F 'TABLET_GDRIVE_SYNC.sh' >/dev/null; then
    echo "DRIVE_CRON=installed"
  else
    echo "DRIVE_CRON=not-installed"
  fi
  if command -v pgrep >/dev/null 2>&1 && pgrep -x crond >/dev/null 2>&1; then
    echo "CROND=running"
  else
    echo "CROND=not-running-or-unavailable"
  fi
  if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -Fxq "${REMOTE}:"; then
    echo "DRIVE_REMOTE=configured"
    if rclone lsf "${REMOTE}:${REMOTE_ROOT}/to_tablet" --files-only --max-depth 1 >/dev/null 2>&1; then
      echo "DRIVE_INBOX=reachable"
    else
      echo "DRIVE_INBOX=unreachable"
    fi
    printf '\n=== 원격 파일 위치 (게시됨 vs 대기 중) ===\n'
    echo "TO_TABLET_LATEST_PACKAGE:"
    rclone lsf "${REMOTE}:${REMOTE_ROOT}/to_tablet" --files-only --max-depth 1 2>/dev/null | grep '^TCG_VERIFIED_.*\.tar\.gz
    rclone lsf "${REMOTE}:${REMOTE_ROOT}/receipts" --files-only --max-depth 1 2>/dev/null | grep '^TABLET_SYNC_RECEIPT_' | sort | tail -n 3 || true
  else
    echo "DRIVE_REMOTE=not-configured"
  fi
  if [ -d "$HOME/.local/state/tcg-grader/gdrive-sync" ]; then
    echo "DRIVE_STATE_DIR=exists (실패 원인은 이 폴더의 로그 확인)"
    ls -lt "$HOME/.local/state/tcg-grader/gdrive-sync" 2>/dev/null | head -n 10 || true
  else
    echo "DRIVE_STATE_DIR=not-created"
  fi
  printf '\n[점검] Drive 수신 cron은 08:00/20:00(태블릿 현지시간), GitHub 코드 갱신과 별개입니다.\n'
  printf '[점검] main local-only/cloud-off 실행 시 Drive 수신 cron이 제거될 수 있습니다.\n'
  printf '[점검] ChatGPT 예약의 메시지/알림은 데이터 파일 자동 게시를 의미하지 않습니다.\n'
  printf '[점검] verified bundle 발행 -> Drive to_tablet -> 태블릿 SHA/스키마 검사 -> receipts 가 전부 필요합니다.\n'
}

case "$mode" in
  status) status ;;
  install)
    echo "[설치] GitHub main 예약 업데이트 설치..."
    bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" install || exit $?
    echo "[설치] Drive JSON 동기화 수신기 설치..."
    bash "$ROOT/TABLET_GDRIVE_SYNC_INSTALL.sh" || exit $?
    status
    ;;
  *) echo "사용법: bash scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh [status|install]" >&2; exit 2 ;;
esac
 | sort | tail -n 1 || true
    echo "STAGING_LATEST_PACKAGE_NOT_DEPLOYED:"
    rclone lsf "${REMOTE}:${REMOTE_ROOT}/staging_artifacts" --files-only --max-depth 1 2>/dev/null | grep -E '\.(zip|tar\.gz)
    rclone lsf "${REMOTE}:${REMOTE_ROOT}/receipts" --files-only --max-depth 1 2>/dev/null | grep '^TABLET_SYNC_RECEIPT_' | sort | tail -n 3 || true
  else
    echo "DRIVE_REMOTE=not-configured"
  fi
  if [ -d "$HOME/.local/state/tcg-grader/gdrive-sync" ]; then
    echo "DRIVE_STATE_DIR=exists (실패 원인은 이 폴더의 로그 확인)"
    ls -lt "$HOME/.local/state/tcg-grader/gdrive-sync" 2>/dev/null | head -n 10 || true
  else
    echo "DRIVE_STATE_DIR=not-created"
  fi
  printf '\n[점검] ChatGPT 예약의 메시지/알림은 데이터 파일 자동 게시를 의미하지 않습니다.\n'
  printf '[점검] verified bundle 발행 -> Drive to_tablet -> 태블릿 SHA/스키마 검사 -> receipts 가 전부 필요합니다.\n'
}

case "$mode" in
  status) status ;;
  install)
    echo "[설치] GitHub main 예약 업데이트 설치..."
    bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" install || exit $?
    echo "[설치] Drive JSON 동기화 수신기 설치..."
    bash "$ROOT/TABLET_GDRIVE_SYNC_INSTALL.sh" || exit $?
    status
    ;;
  *) echo "사용법: bash scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh [status|install]" >&2; exit 2 ;;
esac
 | sort | tail -n 1 || true
    printf '[주의] staging_artifacts의 파일은 검증 후 to_tablet으로 게시되기 전까지 태블릿 적용 대상이 아닙니다.\n'
    printf '[주의] 파일 목록 조회만으로 SHA 검사·실제 태블릿 적용 성공을 판정하지 않습니다.\n'
    echo "최근 태블릿 영수증 파일명:"
    rclone lsf "${REMOTE}:${REMOTE_ROOT}/receipts" --files-only --max-depth 1 2>/dev/null | grep '^TABLET_SYNC_RECEIPT_' | sort | tail -n 3 || true
  else
    echo "DRIVE_REMOTE=not-configured"
  fi
  if [ -d "$HOME/.local/state/tcg-grader/gdrive-sync" ]; then
    echo "DRIVE_STATE_DIR=exists (실패 원인은 이 폴더의 로그 확인)"
    ls -lt "$HOME/.local/state/tcg-grader/gdrive-sync" 2>/dev/null | head -n 10 || true
  else
    echo "DRIVE_STATE_DIR=not-created"
  fi
  printf '\n[점검] ChatGPT 예약의 메시지/알림은 데이터 파일 자동 게시를 의미하지 않습니다.\n'
  printf '[점검] verified bundle 발행 -> Drive to_tablet -> 태블릿 SHA/스키마 검사 -> receipts 가 전부 필요합니다.\n'
}

case "$mode" in
  status) status ;;
  install)
    echo "[설치] GitHub main 예약 업데이트 설치..."
    bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" install || exit $?
    echo "[설치] Drive JSON 동기화 수신기 설치..."
    bash "$ROOT/TABLET_GDRIVE_SYNC_INSTALL.sh" || exit $?
    status
    ;;
  *) echo "사용법: bash scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh [status|install]" >&2; exit 2 ;;
esac
