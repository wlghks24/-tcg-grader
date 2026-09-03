#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
[ -n "$SCRIPT_DIR" ] && cd "$SCRIPT_DIR"

LOG_FILE="GRAPHIFY_UPDATE.log"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

say() {
  [ "$QUIET" = "1" ] || printf '%s\n' "$*"
}

if ! command -v graphify >/dev/null 2>&1; then
  if [ -x "$HOME/.local/bin/graphify" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  else
    say "[Graphify] 아직 설치되지 않았습니다. 먼저 bash SETUP_GRAPHIFY_TERMUX.sh 를 실행하세요."
    exit 0
  fi
fi

if ! graphify --version >/dev/null 2>&1; then
  say "[Graphify] graphify 명령은 있지만 실행되지 않습니다. PATH/설치를 다시 확인하세요."
  exit 1
fi

mkdir -p graphify-out 2>/dev/null || true

say "[Graphify] 코드 지도 갱신을 시작합니다..."
{
  printf '\n===== %s =====\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date)"
  graphify --version

  if [ -s "graphify-out/graph.json" ]; then
    # Bare terminal command. Re-extract only changed files and keep the map code-focused.
    graphify update . --force
  else
    # Initial local AST map. This does not require an LLM/API key.
    graphify extract . --code-only
  fi
} >> "$LOG_FILE" 2>&1
status=$?

if [ "$status" -eq 0 ]; then
  say "[OK] Graphify 코드 지도 갱신 완료"
  [ -s "graphify-out/GRAPH_REPORT.md" ] && say "     보고서: graphify-out/GRAPH_REPORT.md"
  [ -s "graphify-out/graph.html" ] && say "     지도:   graphify-out/graph.html"
  [ -s "graphify-out/graph.json" ] && say "     데이터: graphify-out/graph.json"
else
  say "[오류] Graphify 지도 갱신 실패 · $LOG_FILE 마지막 내용을 확인하세요."
fi

exit "$status"
