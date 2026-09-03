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
    # Re-extract changed files. --force is intentional because a legitimate
    # refactor/deletion can reduce the graph node count.
    graphify update . --force
  else
    # Initial local AST map. Code extraction itself does not require an LLM/API key.
    graphify extract . --code-only
  fi

  # Some headless/code-only flows can leave the raw graph ready before the report
  # and browser visualization are materialized. cluster-only reuses graph.json;
  # --no-label avoids requiring any external LLM/API key while guaranteeing the
  # human-readable report + HTML map are regenerated from the local graph.
  if [ -s "graphify-out/graph.json" ] && { [ ! -s "graphify-out/GRAPH_REPORT.md" ] || [ ! -s "graphify-out/graph.html" ]; }; then
    echo "[Graphify] 보고서/HTML 보완 생성: cluster-only --no-label"
    graphify cluster-only . --no-label
  fi
} >> "$LOG_FILE" 2>&1
status=$?

if [ "$status" -eq 0 ]; then
  missing=""
  for required in graphify-out/graph.json graphify-out/GRAPH_REPORT.md graphify-out/graph.html; do
    if [ ! -s "$required" ]; then
      missing="${missing}${missing:+, }$required"
    fi
  done
  if [ -n "$missing" ]; then
    say "[오류] Graphify 명령은 끝났지만 필수 지도 산출물이 없습니다: $missing"
    say "       $LOG_FILE 마지막 내용을 확인하세요."
    exit 1
  fi

  say "[OK] Graphify 코드 지도 갱신 완료"
  say "     보고서: graphify-out/GRAPH_REPORT.md"
  say "     지도:   graphify-out/graph.html"
  say "     데이터: graphify-out/graph.json"
else
  say "[오류] Graphify 지도 갱신 실패 · $LOG_FILE 마지막 내용을 확인하세요."
fi

exit "$status"
