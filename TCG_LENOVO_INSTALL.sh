#!/data/data/com.termux/files/usr/bin/bash
# Official Lenovo/Termux entrypoint. Never install a PR build or replace local data.
set -euo pipefail

OFFICIAL="https://github.com/wlghks24/-tcg-grader.git"
PROJECT="$HOME/-tcg-grader"
MODE="${1:---help}"

usage() {
  cat <<'HELP'
TCG Lenovo 태블릿 설치 도우미 (공식 GitHub main 전용)
  bash TCG_LENOVO_INSTALL.sh --check    읽기 전용 상태 확인
  bash TCG_LENOVO_INSTALL.sh --install  처음 설치/안전 업데이트 후 서버 실행
  bash TCG_LENOVO_INSTALL.sh --verify   태블릿의 127.0.0.1:8765 건강검사
  bash TCG_LENOVO_INSTALL.sh --boot     별도 설치한 Termux:Boot 자동시작 연결
사용 전: F-Droid Termux 설치, 필요한 경우 pkg install git python
화면: http://127.0.0.1:8765/index.html
HELP
}

case "$MODE" in
  --help|-h) usage; exit 0 ;;
  --check|--install|--verify|--boot) ;;
  *) usage >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then usage >&2; exit 2; fi

if ! command -v pkg >/dev/null 2>&1 || [ -z "${PREFIX:-}" ]; then
  echo "[HOLD] Android Termux에서만 실행할 수 있습니다. PC/일반 Linux 실행은 지원하지 않습니다." >&2
  exit 2
fi
if [ "$(id -u)" = 0 ]; then
  echo "[HOLD] root로 실행하지 않습니다. 일반 Termux 계정을 사용하세요." >&2
  exit 2
fi
if [ -L "$PROJECT" ]; then
  echo "[HOLD] 설치 경로가 심볼릭 링크입니다. 경로를 확인하세요: $PROJECT" >&2
  exit 2
fi

official_origin() {
  case "${1:-}" in
    "https://github.com/wlghks24/-tcg-grader"|"https://github.com/wlghks24/-tcg-grader.git"|"git@github.com:wlghks24/-tcg-grader"|"git@github.com:wlghks24/-tcg-grader.git") return 0 ;;
    *) return 1 ;;
  esac
}
check_existing() {
  if [ ! -e "$PROJECT" ]; then
    echo "[상태] 아직 설치되지 않았습니다: $PROJECT"
    return 1
  fi
  if [ ! -d "$PROJECT/.git" ] || ! command -v git >/dev/null 2>&1; then
    echo "[HOLD] 기존 폴더를 보호합니다. Git 저장소가 아닌 경로는 덮어쓰지 않습니다: $PROJECT" >&2
    exit 2
  fi
  local origin branch
  origin="$(git -C "$PROJECT" remote get-url origin 2>/dev/null || true)"
  branch="$(git -C "$PROJECT" branch --show-current 2>/dev/null || true)"
  if ! official_origin "$origin" || [ "$branch" != main ]; then
    echo "[HOLD] 공식 origin/main이 아닙니다. 현재 원격: ${origin:-없음}, 브랜치: ${branch:-없음}" >&2
    exit 2
  fi
  echo "[OK] 기존 공식 저장소 확인: $(git -C "$PROJECT" rev-parse --short=12 HEAD)"
  if [ -n "$(git -C "$PROJECT" status --porcelain --untracked-files=no)" ]; then
    echo "[보호] 로컬 추적 파일 수정이 있습니다. 자동 업데이트의 보존/거부 규칙을 적용합니다."
  fi
  return 0
}

if [ "$MODE" = --check ]; then
  if ! command -v python >/dev/null 2>&1; then echo "[상태] Python 미설치"; fi
  if ! command -v git >/dev/null 2>&1; then echo "[상태] Git 미설치"; fi
  check_existing || true
  echo "[안내] 설치 실행은 --install, 실행 상태 확인은 --verify를 사용하세요."
  exit 0
fi

if [ "$MODE" = --verify ]; then
  if ! check_existing; then
    echo "[HOLD] 설치된 저장소가 없습니다." >&2
    exit 2
  fi
  if ! command -v python >/dev/null 2>&1; then
    echo "[HOLD] Python이 없습니다." >&2
    exit 2
  fi
  python - <<'PY'
import json, sys, urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8765/api/v135-health", timeout=5) as reply:
        info = json.load(reply)
    if info.get("ok") is not True:
        raise ValueError("health ok가 true가 아님")
except (OSError, ValueError, json.JSONDecodeError) as exc:
    print("[HOLD] 태블릿 서버 확인 실패:", exc, file=sys.stderr)
    raise SystemExit(1)
print("[OK] 태블릿 로컬 서버 건강검사 통과: http://127.0.0.1:8765/index.html")
print("[주의] 실제 카드 촬영·등급·시세 정확도 검증은 별도입니다.")
PY
  exit 0
fi

if [ "$MODE" = --boot ]; then
  check_existing || { echo "[HOLD] 먼저 --install 하세요." >&2; exit 2; }
  if [ ! -f "$PROJECT/ANDROID_AUTO_START_INSTALL.sh" ]; then
    echo "[HOLD] 공식 자동시작 설치 파일이 없습니다." >&2
    exit 2
  fi
  echo "[안내] Termux:Boot 앱을 먼저 설치하고 한 번 실행해 주세요."
  (cd "$PROJECT" && bash ANDROID_AUTO_START_INSTALL.sh)
  exit 0
fi

# Only --install reaches this point.
if ! command -v git >/dev/null 2>&1 || ! command -v python >/dev/null 2>&1; then
  echo "[설치] Termux 공식 패키지 저장소의 Git/Python을 설치합니다."
  pkg update -y
  pkg install -y git python
fi
if ! check_existing; then
  echo "[설치] 공식 GitHub main을 새 경로에 받습니다. 기존 파일은 삭제하지 않습니다."
  STAGE="$(mktemp -d "$HOME/.tcg-install-XXXXXXXX")"
  if ! git clone --branch main --single-branch "$OFFICIAL" "$STAGE/checkout"; then
    echo "[HOLD] GitHub 다운로드 실패. 검사 가능한 임시 폴더: $STAGE" >&2
    exit 1
  fi
  for name in ANDROID_UPDATE_AND_START.sh START_TCG_UPDATER_ANDROID.sh tablet_runtime_manifest.py; do
    if [ ! -f "$STAGE/checkout/$name" ]; then
      echo "[HOLD] 필수 파일 누락: $name, 임시 폴더: $STAGE" >&2
      exit 1
    fi
  done
  if ! (cd "$STAGE/checkout" && bash -n ANDROID_UPDATE_AND_START.sh && \
        bash -n START_TCG_UPDATER_ANDROID.sh && \
        python tablet_runtime_manifest.py --check --compile); then
    echo "[HOLD] 신규 설치본 검증 실패. 기존 설치는 변경되지 않았습니다: $STAGE" >&2
    exit 1
  fi
  if [ -e "$PROJECT" ] || [ -L "$PROJECT" ]; then
    echo "[HOLD] 설치 도중 동일 경로가 생겼습니다. 기존 폴더를 보존합니다." >&2
    exit 2
  fi
  mv "$STAGE/checkout" "$PROJECT"
  rmdir "$STAGE" 2>/dev/null || true
  echo "[OK] 새 코드 설치 완료. GitHub main: $(git -C "$PROJECT" rev-parse --short=12 HEAD)"
fi

echo "[시작] 공식 updater가 최신 main, 로컬 수정, 학습자료를 검증합니다."
echo "[안내] 화면은 태블릿 Chrome의 http://127.0.0.1:8765/index.html 에서 엽니다."
cd "$PROJECT"
exec bash ANDROID_UPDATE_AND_START.sh
