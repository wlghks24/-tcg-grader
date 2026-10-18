#!/data/data/com.termux/files/usr/bin/bash
# TCG v13.6: verify two independent update channels. Fail closed for installs.
# status never changes credentials, crontab, boot scripts or checked-out code.
set -u
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
REMOTE="${TCG_GDRIVE_REMOTE:-gdrive}"
REMOTE_ROOT="${TCG_GDRIVE_ROOT:-TCG_Grader_Sync}"
MODE="${1:-status}"

valid_target() {
  [[ "$REMOTE" =~ ^[a-zA-Z0-9_-]+$ ]] &&
  [[ "$REMOTE_ROOT" =~ ^[a-zA-Z0-9_/-]+$ ]] &&
  [[ "/$REMOTE_ROOT/" != *"/../"* ]] &&
  [[ "/$REMOTE_ROOT/" != *"/./"* ]]
}
remote_exists() {
  command -v rclone >/dev/null 2>&1 &&
  rclone listremotes 2>/dev/null | grep -Fxq "${REMOTE}:"
}
remote_folders_exist() {
  rclone lsf "${REMOTE}:${REMOTE_ROOT}/to_tablet" --max-depth 1 >/dev/null 2>&1 &&
  rclone lsf "${REMOTE}:${REMOTE_ROOT}/receipts" --max-depth 1 >/dev/null 2>&1
}
cron_installed() {
  command -v crontab >/dev/null 2>&1 &&
  crontab -l 2>/dev/null | grep -F 'TABLET_GDRIVE_SYNC.sh' >/dev/null
}
status() {
  printf '\n=== CHANNEL A: GitHub code/main updater ===\n'
  printf 'GITHUB_LOCAL_SHA='
  git -C "$ROOT" rev-parse --short=12 HEAD 2>/dev/null || echo 'unknown'
  if [ -s "$ROOT/TABLET_SCHEDULED_UPDATE.sh" ]; then
    bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" status || echo 'GITHUB_SCHEDULE=status-error'
  else
    echo 'GITHUB_SCHEDULE=script-missing'
  fi
  printf '\n=== CHANNEL B: verified GPT JSON -> Drive -> Tablet ===\n'
  if cron_installed; then
    echo 'DRIVE_CRON=installed'
  else
    echo 'DRIVE_CRON=missing'
  fi
  if command -v pgrep >/dev/null 2>&1 && pgrep -x crond >/dev/null 2>&1; then
    echo 'CROND=running'
  else
    echo 'CROND=not-running-or-unavailable'
  fi
  if ! valid_target; then
    echo 'DRIVE_REMOTE=unsafe-configuration'
  elif ! remote_exists; then
    echo 'DRIVE_REMOTE=not-configured'
  else
    echo 'DRIVE_REMOTE=configured'
    if remote_folders_exist; then
      echo 'DRIVE_FOLDERS=reachable'
      receipts="$(rclone lsf "${REMOTE}:${REMOTE_ROOT}/receipts" --files-only --max-depth 1 2>/dev/null | grep '^TABLET_SYNC_RECEIPT_' | sort | tail -n 3 || true)"
      if [ -n "$receipts" ]; then
        echo 'RECEIPTS=present-not-content-verified'
        printf '%s\n' "$receipts" | sed 's/^/RECEIPT_FILENAME=/'
      else
        echo 'RECEIPTS=missing'
      fi
      packages="$(rclone lsf "${REMOTE}:${REMOTE_ROOT}/to_tablet" --files-only --max-depth 1 2>/dev/null | grep '^manifest_.*\.json$' | sort | tail -n 1 || true)"
      if [ -n "$packages" ]; then
        printf 'NEWEST_MANIFEST_FILENAME=%s\n' "$packages"
      else
        echo 'NEWEST_MANIFEST_FILENAME=none'
      fi
    else
      echo 'DRIVE_FOLDERS=unreachable'
    fi
  fi
  if [ -d "$HOME/.local/state/tcg-grader/gdrive-sync" ]; then
    echo 'RECEIVER_LOCAL_STATE=present'
  else
    echo 'RECEIVER_LOCAL_STATE=missing'
  fi
  echo 'GPT_PUBLISHER=not-verified-by-device-check'
  echo 'END_TO_END_DELIVERY=HOLD-until-fresh-receipt-and-device-run'
  echo '[설명] 예약 알림은 17개 JSON의 실제 게시/검증/적용을 증명하지 않습니다.'
  echo '[설명] 태블릿 수신은 08:00/20:00 현지시간 cron이며, GitHub 코드는 별도 23:00 KST 점검입니다.'
}
preflight_drive() {
  if ! valid_target; then
    echo '[HOLD] rclone 원격/폴더 설정이 안전한 경로 형식이 아닙니다.' >&2
    return 10
  fi
  if ! remote_exists; then
    echo "[HOLD] rclone '${REMOTE}:' 미인증/미설치. 본인이 rclone config 후 재실행하세요." >&2
    return 11
  fi
  if ! remote_folders_exist; then
    echo '[HOLD] Drive to_tablet 또는 receipts 폴더 접근 실패. 인증/경로를 먼저 확인하세요.' >&2
    return 12
  fi
  for f in TABLET_GDRIVE_SYNC_INSTALL.sh TABLET_GDRIVE_SYNC.sh tablet_gdrive_sync.py tablet_gdrive_sync_hardening.py tablet_gdrive_sync_hardening_contextual.py tablet_gdrive_sync_perf_v262.py; do
    if [ ! -s "$ROOT/$f" ]; then
      echo "[HOLD] 동기화 실행 의존 파일 누락: $f" >&2
      return 13
    fi
  done
  return 0
}
case "$MODE" in
  status) status ;;
  install|install-drive)
    # Strictly no GitHub updater/cron/boot changes before all Drive preflights pass.
    preflight_drive || exit $?
    if [ "$MODE" = install ]; then
      [ -s "$ROOT/TABLET_SCHEDULED_UPDATE.sh" ] || { echo '[HOLD] GitHub 예약 스크립트 누락' >&2; exit 14; }
      bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" install || exit $?
    fi
    bash "$ROOT/TABLET_GDRIVE_SYNC_INSTALL.sh" || exit $?
    status
    ;;
  run-now)
    preflight_drive || exit $?
    echo '[실행] 검증된 기존 데이터만 동기화하며, 실패 시 기존 정상본을 보호합니다.'
    bash "$ROOT/TABLET_GDRIVE_SYNC.sh" || exit $?
    status
    ;;
  *) echo '사용법: bash scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh [status|install|install-drive|run-now]' >&2; exit 2 ;;
esac
