#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
[ -n "$SCRIPT_DIR" ] && cd "$SCRIPT_DIR"

LOG_FILE="${GRAPHIFY_LOG_FILE:-GRAPHIFY_UPDATE.log}"
SELF_HEAL="GRAPHIFY_SELF_HEAL.py"
GRAPHIFY_BIN="${GRAPHIFY_BIN:-graphify}"
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

say() {
  [ "$QUIET" = "1" ] || printf '%s\n' "$*"
}

run_graphify() {
  "$GRAPHIFY_BIN" "$@"
}

validate_outputs() {
  missing=""
  for required in graphify-out/graph.json graphify-out/GRAPH_REPORT.md graphify-out/graph.html; do
    if [ ! -s "$required" ]; then
      missing="${missing}${missing:+, }$required"
    fi
  done
  if [ -n "$missing" ]; then
    echo "[Graphify] 필수 지도 산출물 누락: $missing"
    return 24
  fi
  return 0
}

resolve_graphify() {
  if command -v "$GRAPHIFY_BIN" >/dev/null 2>&1; then
    return 0
  fi
  if [ "$GRAPHIFY_BIN" = "graphify" ] && [ -x "$HOME/.local/bin/graphify" ]; then
    export PATH="$HOME/.local/bin:$PATH"
    GRAPHIFY_BIN="$HOME/.local/bin/graphify"
    return 0
  fi
  echo "[Graphify] graphify: command not found"
  return 10
}

perform_update() {
  run_graphify --version || return 11
  mkdir -p graphify-out || return 20

  if [ -s "graphify-out/graph.json" ]; then
    echo "[Graphify] 변경분 지도 갱신: update --force"
    run_graphify update . --force || return 21
  else
    echo "[Graphify] 최초 코드 지도 생성: extract --code-only"
    run_graphify extract . --code-only || return 22
  fi

  if [ -s "graphify-out/graph.json" ] && { [ ! -s "graphify-out/GRAPH_REPORT.md" ] || [ ! -s "graphify-out/graph.html" ]; }; then
    echo "[Graphify] 보고서/HTML 보완 생성: cluster-only --no-label"
    run_graphify cluster-only . --no-label || return 23
  fi

  validate_outputs || return $?
  return 0
}

invoke_self_heal() {
  failure_code="$1"
  reason="$2"
  [ "${GRAPHIFY_DISABLE_SELF_HEAL:-0}" = "1" ] && return 1
  [ -f "$SELF_HEAL" ] || return 1
  command -v python >/dev/null 2>&1 || return 1

  echo "[Graphify] 오류코드 $failure_code 감지 → 검증된 자가복구 전략을 시도합니다."
  python "$SELF_HEAL" \
    --repair \
    --log "$LOG_FILE" \
    --failure-code "$failure_code" \
    --reason "$reason"
}

say "[Graphify] 코드 지도 갱신을 시작합니다..."
# Run the internal sequence in a subshell so its explicit exit code is captured
# here instead of terminating this wrapper before the final user-facing result.
(
  printf '\n===== %s =====\n' "$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date)"

  resolve_graphify
  preflight_status=$?
  if [ "$preflight_status" -ne 0 ]; then
    status="$preflight_status"
  else
    perform_update
    status=$?
  fi

  if [ "$status" -ne 0 ]; then
    echo "[Graphify] 1차 지도 갱신 실패(status=$status)"
    if invoke_self_heal "$status" "GRAPHIFY_UPDATE.sh primary refresh failed"; then
      if validate_outputs; then
        echo "[Graphify] 자가복구 후 필수 산출물 검증 성공"
        status=0
      else
        status=34
      fi
    fi
  fi

  printf '[Graphify] 최종 status=%s\n' "$status"
  exit "$status"
) >> "$LOG_FILE" 2>&1
status=$?

if [ "$status" -eq 0 ]; then
  say "[OK] Graphify 코드 지도 갱신 완료"
  say "     보고서: graphify-out/GRAPH_REPORT.md"
  say "     지도:   graphify-out/graph.html"
  say "     데이터: graphify-out/graph.json"
  if [ -s graphify_self_heal_report.json ]; then
    say "     자가복구 리포트: graphify_self_heal_report.json"
  fi
else
  say "[오류] Graphify 지도 갱신 실패(status=$status) · $LOG_FILE 마지막 내용을 확인하세요."
  [ -s graphify_self_heal_report.json ] && say "       자가복구 리포트: graphify_self_heal_report.json"
fi

exit "$status"
