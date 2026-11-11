#!/data/data/com.termux/files/usr/bin/bash
# TCG Grader: supervised Lenovo/Termux installation from a reviewed Git checkout.
# No force push/reset, deleted data, arbitrary download-and-execute, or cloud sync.
set -euo pipefail

REPO="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
OFFICIAL="https://github.com/wlghks24/-tcg-grader.git"
ACTION="${1:---check}"

help() {
  cat <<'USAGE'
Lenovo TCG 설치기 V1004 (Termux + 로컬 PWA)
  bash INSTALL_LENOVO_TCG_V1004.sh --check    읽기전용 사전 점검
  bash INSTALL_LENOVO_TCG_V1004.sh --install  승인된 GitHub main + 서버 자동 설치
  bash INSTALL_LENOVO_TCG_V1004.sh --status   현재 서버/자동화 상태 읽기
최초 설치: Termux에서 'pkg install python python-pillow git' 실행,
          공식 저장소 git clone 후 이 파일을 실행하세요.
기존 설치: 현재 프로젝트 폴더에서 'bash main update-now' 후 사용하세요.
브라우저 앱: http://127.0.0.1:8765/index.html → Chrome 앱 설치/홈 화면 추가
USAGE
}
fail() { printf '[설치 보류] %s\n' "$1" >&2; exit 2; }
termux_only() {
  case "${PREFIX:-}" in
    */com.termux/files/usr) ;;
    *) fail 'Android Termux 환경에서만 실행할 수 있습니다.' ;;
  esac
}
origin_is_official() {
  case "$1" in
    https://github.com/wlghks24/-tcg-grader|https://github.com/wlghks24/-tcg-grader.git|git@github.com:wlghks24/-tcg-grader.git|git@github.com:wlghks24/-tcg-grader) return 0 ;;
    *) return 1 ;;
  esac
}
preflight() {
  termux_only
  for cmd in git python bash; do command -v "$cmd" >/dev/null 2>&1 || fail "$cmd 명령이 없습니다. Termux에서 pkg install python python-pillow git 을 실행하세요."; done
  [ -d "$REPO/.git" ] && [ ! -L "$REPO/.git" ] || fail '공식 Git 저장소 checkout이 아닙니다. 기존 원본 폴더를 삭제하지 마세요.'
  [ ! -L "$REPO" ] || fail '심볼릭 링크 저장소는 허용하지 않습니다.'
  actual="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
  origin_is_official "$actual" || fail "공식 origin이 아닙니다: $actual"
  branch="$(git -C "$REPO" branch --show-current)"
  [ "$branch" = main ] || fail "현재 브랜치가 main이 아닙니다($branch)."
  head="$(git -C "$REPO" rev-parse --verify HEAD)"
  case "$head" in *[!0-9a-f]*|'') fail 'Git HEAD가 올바르지 않습니다.';; esac
  [ "${#head}" -eq 40 ] || fail 'Git HEAD 길이가 올바르지 않습니다.'
  [ -z "$(git -C "$REPO" diff --cached --name-only)" ] || fail 'staged 파일을 보호하기 위해 설치를 보류합니다.'
  for name in main VERIFY_TABLET_FINAL.sh tablet_runtime_manifest.py tablet_runtime_probe.py; do
    [ -f "$REPO/$name" ] && [ ! -L "$REPO/$name" ] || fail "필수 파일 누락/링크: $name"
  done
  printf '[사전점검] 폴더=%s\n[사전점검] 설치본 SHA=%s\n' "$REPO" "$head"
  echo '[안내] --check는 원격 최신 SHA·실제 태블릿 화면·자동 부팅을 인증하지 않습니다.'
}
install() {
  preflight
  command -v pkg >/dev/null 2>&1 || fail 'Termux pkg가 없습니다.'
  python - <<'PY' || fail 'Pillow 13.x 또는 Python 의존성 확인 실패. pkg install python python-pillow 를 실행하세요.'
from PIL import __version__
major=int(__version__.split('.',1)[0])
assert major==13, f'Pillow {__version__}: requires 13.x'
PY
  [ -z "$(git -C "$REPO" diff --name-only -- main VERIFY_TABLET_FINAL.sh tablet_runtime_manifest.py tablet_runtime_probe.py)" ] || fail '실행 제어 코드가 로컬에서 수정돼 있어 자동 설치를 보류합니다.'
  [ -n "$(git -C "$REPO" rev-parse --verify refs/remotes/origin/main 2>/dev/null || true)" ] || fail 'origin/main 참조가 없습니다. bash main update-now를 먼저 실행하세요.'
  head="$(git -C "$REPO" rev-parse HEAD)"
  tracked="$(git -C "$REPO" rev-parse refs/remotes/origin/main)"
  [ "$head" = "$tracked" ] || fail 'origin/main과 일치하지 않습니다. 먼저 bash main update-now 실행 후 재시도하세요.'
  remote_line="$(git ls-remote "$OFFICIAL" refs/heads/main)" || fail '공식 GitHub main 조회 실패(네트워크). 설치 보류.'
  read -r remote_head _ <<< "$remote_line"
  [ "${#remote_head}" -eq 40 ] || fail '원격 main SHA 형식 오류. 설치 보류.'
  [ "$head" = "$remote_head" ] || fail '공식 GitHub main이 더 최신입니다. bash main update-now 후 재검증하세요.'
  cd "$REPO"
  echo '[1/4] 설치 전 런타임 매니페스트와 Python 검증'
  python tablet_runtime_manifest.py --check --compile
  echo '[2/4] 태블릿 최종 무결성 검증'
  bash VERIFY_TABLET_FINAL.sh
  echo '[3/4] 기존 보호된 Termux 서버/감시 서비스 설치'
  bash main auto-install
  echo '[4/4] 로컬 HTTP 실행 SHA 확인'
  python tablet_runtime_probe.py --require-health --require-runtime-contract
  bash main auto-status
  echo '[서버 설치 검증 통과] 아래 URL을 태블릿 Chrome에서 열어 앱 설치/홈 화면 추가를 선택하세요.'
  echo 'http://127.0.0.1:8765/index.html'
  echo '[주의] Chrome 홈 화면 설치 및 재부팅 후 자동실행은 실제 태블릿에서 별도로 확인해야 합니다.'
}
status() {
  preflight
  cd "$REPO"
  bash main auto-status
  python tablet_runtime_probe.py --require-health --require-runtime-contract
  echo '[안내] 이 결과만으로 Chrome 앱 설치와 재부팅 성공을 증명하지는 않습니다.'
}

case "$ACTION" in
  --help|-h|help) help ;;
  --check|check) preflight ;;
  --install|install) install ;;
  --status|status) status ;;
  *) help; exit 2 ;;
esac
