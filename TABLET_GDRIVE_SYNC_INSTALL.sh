#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
REPO="${TCG_REPO_DIR:-$SCRIPT_DIR}"
REMOTE="${TCG_GDRIVE_REMOTE:-gdrive}"
REMOTE_ROOT="${TCG_GDRIVE_ROOT:-TCG_Grader_Sync}"
STATE="$HOME/.local/state/tcg-grader/gdrive-sync"
BOOT_DIR="$HOME/.termux/boot"
BOOT_FILE="$BOOT_DIR/TCG_GDRIVE_SYNC_BOOT.sh"

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
chmod +x "$REPO/TABLET_GDRIVE_SYNC.sh" "$REPO/tablet_gdrive_sync.py"

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

# GPT의 07:00 KST 검증 작업 이후 충분한 반영 여유를 두고 하루 2회 확인합니다.
# 태블릿의 현지시간 기준 08:00 / 20:00이며 정확히 12시간 간격입니다.
CRON_LINE="0 8,20 * * * cd '$REPO' && bash '$REPO/TABLET_GDRIVE_SYNC.sh' >> '$STATE/cron.log' 2>&1"
( crontab -l 2>/dev/null | grep -Fv "TABLET_GDRIVE_SYNC.sh" || true
  printf '%s\n' "$CRON_LINE"
) | crontab -

cat > "$BOOT_FILE" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -u
termux-wake-lock >/dev/null 2>&1 || true
pgrep -x crond >/dev/null 2>&1 || crond
EOF
chmod +x "$BOOT_FILE"

pgrep -x crond >/dev/null 2>&1 || crond

echo "[검증] 첫 동기화 확인"
rc=0
bash "$REPO/TABLET_GDRIVE_SYNC.sh" || rc=$?
if [ "$rc" = "0" ] || [ "$rc" = "75" ]; then
  echo "[OK] GPT→Drive→태블릿 자동 동기화 설치 완료"
  echo "     주기: 12시간마다 1회 (08:00 / 20:00, 태블릿 현지시간)"
  echo "     Drive: ${REMOTE}:${REMOTE_ROOT}"
  echo "     부팅 자동실행: $BOOT_FILE"
  echo "[중요] Termux:Boot 앱을 설치한 경우 재부팅 후 crond가 자동 시작됩니다."
  exit 0
fi
echo "[안내] 설치는 완료됐지만 첫 동기화가 HOLD 상태입니다(rc=$rc). 로그를 확인하세요: $STATE"
exit "$rc"
