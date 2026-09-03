#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
[ -n "$SCRIPT_DIR" ] && cd "$SCRIPT_DIR"

LOG_FILE="${GRAPHIFY_LOG_FILE:-GRAPHIFY_UPDATE.log}"
SELF_HEAL="GRAPHIFY_SELF_HEAL.py"
AUDIT_SCRIPT="GRAPHIFY_AUDIT.py"
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
  if [ -f "$SELF_HEAL" ] && command -v python >/dev/null 2>&1; then
    if python "$SELF_HEAL" --validate-only; then
      return 0
    fi
    echo "[Graphify] 필수 지도 산출물 무결성 검증 실패"
    return 24
  fi

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

run_map_audit() {
  [ -f "$AUDIT_SCRIPT" ] || return 0
  command -v python >/dev/null 2>&1 || return 0
  echo "[Graphify] 코드 지도 구조/범위 최적화 검사"
  python "$AUDIT_SCRIPT" --strict || return 25
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
    # Normal update is Graphify's fast incremental path.  Do not disable its
    # shrink-safety guard pre-emptively on every tablet refresh.  --force is a
    # bounded fallback for legitimate refactors/deletions that make the graph
    # smaller.
    echo "[Graphify] 변경분 지도 갱신: incremental update"
    if ! run_graphify update .; then
      echo "[Graphify] 일반 증분갱신 실패 → 삭제/축소 리팩터링용 --force 1회 재시도"
      run_graphify update . --force || return 21
    fi
  else
    echo "[Graphify] 최초 코드 지도 생성: extract --code-only"
    run_graphify extract . --code-only || return 22
  fi

  if [ -s "graphify-out/graph.json" ] && { [ ! -s "graphify-out/GRAPH_REPORT.md" ] || [ ! -s "graphify-out/graph.html" ]; }; then
    echo "[Graphify] 보고서/HTML 보완 생성: cluster-only --no-label --exclude-hubs 99"
    run_graphify cluster-only . --no-label --exclude-hubs 99 || return 23
  fi

  validate_outputs || return $?
  run_map_audit || return $?
  return 0
}

invoke_self_heal() {
  failure_code="$1"
  reason="$2"
  [ "${GRAPHIFY_DISABLE_SELF_HEAL:-0}" = "1" ] && return 1
  [ -f "$SELF_HEAL" ] || return 1
  command -v python >/dev/null 2>&1 || return 1

  echo "[Graphify] 오류코드 $failure_code 감지 → 오류서명 학습 + 검증된 자가수정 전략을 시도합니다."
  GRAPHIFY_BIN="$GRAPHIFY_BIN" python "$SELF_HEAL" \
    --repair \
    --log "$LOG_FILE" \
    --failure-code "$failure_code" \
    --reason "$reason"
}

say "[Graphify] 코드 지도 갱신을 시작합니다..."
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
    first_status="$status"
    echo "[Graphify] 1차 지도 갱신 실패(status=$first_status)"
    if invoke_self_heal "$first_status" "GRAPHIFY_UPDATE.sh primary refresh failed status=$first_status"; then
      echo "[Graphify] 자가복구 적용 후 실제 지도 갱신을 1회 재검증합니다."
      resolve_graphify
      retry_preflight=$?
      if [ "$retry_preflight" -ne 0 ]; then
        status="$retry_preflight"
      else
        perform_update
        status=$?
      fi
      if [ "$status" -eq 0 ]; then
        if validate_outputs && run_map_audit; then
          echo "[Graphify] 자가복구 후 실제 갱신 + 산출물/지도범위 무결성 검증 성공"
        else
          status=34
        fi
      else
        echo "[Graphify] 자가복구 후 실제 지도 갱신 재시도 실패(status=$status)"
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
  [ -s graphify-out/graph_audit.json ] && say "     최적화검사: graphify-out/graph_audit.json"
  if [ -s graphify_self_heal_report.json ]; then
    say "     자가복구 리포트: graphify_self_heal_report.json"
  fi
else
  say "[오류] Graphify 지도 갱신 실패(status=$status) · $LOG_FILE 마지막 내용을 확인하세요."
  [ -s graphify-out/graph_audit.json ] && say "       지도검사: graphify-out/graph_audit.json"
  [ -s graphify_self_heal_report.json ] && say "       자가복구 리포트: graphify_self_heal_report.json"
  [ -s graphify_self_heal_candidates.json ] && say "       미해결 오류후보: graphify_self_heal_candidates.json"
fi

exit "$status"
