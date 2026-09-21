#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
REPO="${TCG_REPO_DIR:-$SCRIPT_DIR}"
REMOTE="${TCG_GDRIVE_REMOTE:-gdrive}"
REMOTE_ROOT="${TCG_GDRIVE_ROOT:-TCG_Grader_Sync}"
STATE="$HOME/.local/state/tcg-grader/gdrive-sync"
BOOT_DIR="$HOME/.termux/boot"
BOOT_RECOVERY_FILE="$BOOT_DIR/00_TCG_GDRIVE_RECOVERY.sh"
BOOT_CRON_FILE="$BOOT_DIR/TCG_GDRIVE_SYNC_BOOT.sh"

cd "$REPO"

for cmd in python git curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[설치] $cmd"
    pkg install -y "$cmd"
  fi
done
if ! command -v rclone >/dev/null 2>&1; then
  echo "[설치] rclone"
  pkg install -y rclone
fi
if ! command -v crond >/dev/null 2>&1; then
  echo "[설치] cronie"
  pkg install -y cronie
fi

mkdir -p "$STATE" "$BOOT_DIR"
# Keep this list aligned with TABLET_GDRIVE_SYNC.sh and the v273 runtime import
# chain. The old installer could report success even when the performance or
# contextual layer was missing, which would only fail later at 08:00/20:00.
for file in \
  TABLET_GDRIVE_SYNC.sh \
  tablet_gdrive_sync.py \
  tablet_gdrive_sync_hardening.py \
  tablet_gdrive_sync_hardening_contextual.py \
  tablet_gdrive_sync_perf_v262.py; do
  if [ ! -s "$REPO/$file" ]; then
    echo "[오류] 필수 동기화 파일 누락: $file"
    exit 2
  fi
done
chmod +x \
  "$REPO/TABLET_GDRIVE_SYNC.sh" \
  "$REPO/tablet_gdrive_sync.py" \
  "$REPO/tablet_gdrive_sync_hardening.py" \
  "$REPO/tablet_gdrive_sync_hardening_contextual.py" \
  "$REPO/tablet_gdrive_sync_perf_v262.py"

if ! rclone listremotes 2>/dev/null | grep -Fxq "${REMOTE}:"; then
  cat <<EOF
[사용자 1회 작업]
rclone 원격 '${REMOTE}:'가 아직 없습니다.
지금 아래 명령을 실행해 Google Drive 로그인을 완료한 뒤 이 설치기를 다시 실행하세요.

  rclone config

권장:
- n) New remote
- name: ${REMOTE}
- Storage: drive (Google Drive)
- client_id/client_secret: 본인 Google OAuth 값을 사용하려면 입력
- scope: drive
- root_folder_id: 비움
- service_account_file: 비움
- 브라우저 로그인 완료
EOF
  exit 3
fi

if ! rclone lsf "${REMOTE}:${REMOTE_ROOT}" --dirs-only --max-depth 1 >/dev/null 2>&1; then
  echo "[오류] ${REMOTE}:${REMOTE_ROOT}에 접근할 수 없습니다. rclone 인증/권한을 확인하세요."
  exit 4
fi
for subdir in to_tablet receipts; do
  if ! rclone lsf "${REMOTE}:${REMOTE_ROOT}/${subdir}" --max-depth 1 >/dev/null 2>&1; then
    echo "[오류] 필수 Drive 경로에 접근할 수 없습니다: ${REMOTE}:${REMOTE_ROOT}/${subdir}"
    exit 4
  fi
done

# GPT의 07:00 / 19:00 KST 검증 이후 각각 1시간 뒤 확인합니다.
# cron은 태블릿 현지시간을 사용하므로 한국시간 태블릿에서는 08:00 / 20:00입니다.
CRON_LINE="0 8,20 * * * cd '$REPO' && bash '$REPO/TABLET_GDRIVE_SYNC.sh' >> '$STATE/cron.log' 2>&1"
( crontab -l 2>/dev/null | grep -Fv "TABLET_GDRIVE_SYNC.sh" || true
  printf '%s\n' "$CRON_LINE"
) | crontab -

# Termux:Boot는 파일명 정렬 순서대로 실행하므로 00_ 복구가 다른 TCG 시작 스크립트보다 먼저 실행됩니다.
cat > "$BOOT_RECOVERY_FILE" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -u
cd '$REPO' || exit 0
bash '$REPO/TABLET_GDRIVE_SYNC.sh' --recover-only >> '$STATE/boot-recovery.log' 2>&1 || true
EOF
chmod +x "$BOOT_RECOVERY_FILE"

# 부팅 시 crond만 복구합니다. 장시간 wake-lock은 잡지 않습니다.
cat > "$BOOT_CRON_FILE" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -u
pgrep -x crond >/dev/null 2>&1 || crond
EOF
chmod +x "$BOOT_CRON_FILE"

pgrep -x crond >/dev/null 2>&1 || crond
if ! pgrep -x crond >/dev/null 2>&1; then
  echo "[오류] crond 시작 확인에 실패했습니다. 08:00/20:00 자동 동기화를 보장할 수 없습니다."
  exit 6
fi

# 설치 자체가 08:00/20:00 외 추가 동기화를 만들지 않도록 기본값은 검사만 수행합니다.
python -m py_compile \
  "$REPO/tablet_gdrive_sync.py" \
  "$REPO/tablet_gdrive_sync_hardening.py" \
  "$REPO/tablet_gdrive_sync_hardening_contextual.py" \
  "$REPO/tablet_gdrive_sync_perf_v262.py"
bash -n "$REPO/TABLET_GDRIVE_SYNC.sh"
if ! crontab -l 2>/dev/null | grep -Fqx "$CRON_LINE"; then
  echo "[오류] 12시간 cron 등록 확인 실패"
  exit 5
fi

echo "[OK] GPT→Drive→태블릿 자동 동기화 설치/검증 완료"
echo "     생산: 07:00 / 19:00 KST 검증 후 패키지 준비"
echo "     태블릿: 08:00 / 20:00 (태블릿 현지시간)"
echo "     Drive: ${REMOTE}:${REMOTE_ROOT}"
echo "     부팅 선복구: $BOOT_RECOVERY_FILE"
echo "     부팅 cron 복구: $BOOT_CRON_FILE"
echo "[중요] Termux:Boot를 설치했다면 앱 아이콘을 한 번 실행하고, Android 배터리 최적화에서 Termux/Termux:Boot를 제한 없음으로 설정하는 것을 권장합니다."

if [ "${TCG_GDRIVE_SYNC_RUN_NOW:-0}" = "1" ]; then
  echo "[수동옵션] 설치 직후 1회 동기화를 실행합니다."
  bash "$REPO/TABLET_GDRIVE_SYNC.sh"
fi
