#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
[ -n "$SCRIPT_DIR" ] && cd "$SCRIPT_DIR"

GRAPHIFY_VERSION="${GRAPHIFY_VERSION:-0.9.53}"
GRAPHIFY_SPEC="graphifyy==$GRAPHIFY_VERSION"
SELF_HEAL="./GRAPHIFY_SELF_HEAL.py"
HEAL_LOG="${GRAPHIFY_LOG_FILE:-GRAPHIFY_UPDATE.log}"

printf '%s\n' "========================================"
printf '%s\n' " TCG Grader · Graphify 설치/코드지도 설정"
printf '%s\n' "========================================"

heal_setup() {
  failure_code="$1"
  reason="$2"
  [ -f "$SELF_HEAL" ] || return 1
  command -v python >/dev/null 2>&1 || return 1
  GRAPHIFY_VERSION="$GRAPHIFY_VERSION" python "$SELF_HEAL" \
    --repair \
    --log "$HEAL_LOG" \
    --failure-code "$failure_code" \
    --reason "$reason"
}

if [ -n "${TERMUX_VERSION:-}" ] || printf '%s' "${PREFIX:-}" | grep -q 'com.termux'; then
  echo "[1/9] 운영체제: Android + Termux 확인"
else
  echo "[안내] 이 스크립트는 Android/Termux용입니다. 현재 환경을 Termux로 확인하지 못했습니다."
  echo "       Mac/Windows에서는 GRAPHIFY_CHATGPT_GUIDE.md 안내를 사용하세요."
fi

if ! command -v python >/dev/null 2>&1; then
  echo "[2/9] Python 없음 → Termux Python을 설치합니다."
  if command -v pkg >/dev/null 2>&1; then
    pkg install python -y || exit 1
  else
    echo "[오류] pkg 명령이 없습니다. Python 3.10+를 먼저 설치하세요."
    exit 1
  fi
fi

python - <<'PY'
import sys
print(f"[2/9] Python: {sys.version.split()[0]}")
if sys.version_info < (3, 10):
    raise SystemExit(10)
PY
py_status=$?
if [ "$py_status" -eq 10 ]; then
  echo "[안내] Python 3.10 미만 → Termux 패키지를 최신화합니다."
  if command -v pkg >/dev/null 2>&1; then
    pkg update -y && pkg install python -y || exit 1
  fi
  python - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f"Python 3.10+ 필요. 현재: {sys.version.split()[0]}")
print(f"[OK] Python {sys.version.split()[0]}")
PY
elif [ "$py_status" -ne 0 ]; then
  exit "$py_status"
fi

echo "[3/9] Graphify 검증 버전 준비: $GRAPHIFY_VERSION"
export PATH="$HOME/.local/bin:$PATH"
current_graphify="$(graphify --version 2>/dev/null || true)"
if printf '%s' "$current_graphify" | grep -Eq "(^|[^0-9])${GRAPHIFY_VERSION//./\\.}([^0-9]|$)"; then
  echo "[OK] 이미 검증 버전 사용 중: $current_graphify"
else
  install_ok=0
  if command -v uv >/dev/null 2>&1; then
    echo "[설치] uv → $GRAPHIFY_SPEC"
    if uv tool install --force "$GRAPHIFY_SPEC"; then
      install_ok=1
      uv tool update-shell >/dev/null 2>&1 || true
    fi
  else
    echo "[설치] uv 없음 → pipx → $GRAPHIFY_SPEC"
    if ! command -v pipx >/dev/null 2>&1; then
      python -m pip install pipx || true
    fi
    python -m pipx ensurepath >/dev/null 2>&1 || true
    if python -m pipx install --force "$GRAPHIFY_SPEC"; then
      install_ok=1
    fi
  fi

  if [ "$install_ok" != "1" ]; then
    echo "[복구] 1차 설치 실패 → 자가학습 복구 엔진으로 원인분류/재설치를 시도합니다."
    heal_setup 10 "SETUP_GRAPHIFY_TERMUX.sh graphify install failed" || {
      echo "[오류] Graphify 자동 설치/복구에 실패했습니다."
      exit 1
    }
  fi
fi

export PATH="$HOME/.local/bin:$PATH"
if ! grep -Fq 'TCG_GRAPHIFY_PATH' "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# TCG_GRAPHIFY_PATH\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
fi
hash -r 2>/dev/null || true

if ! command -v graphify >/dev/null 2>&1; then
  echo "[복구] graphify 명령을 PATH에서 찾지 못했습니다 → 자동 PATH/설치 복구"
  heal_setup 10 "SETUP_GRAPHIFY_TERMUX.sh graphify command not found" || exit 1
  export PATH="$HOME/.local/bin:$PATH"
  hash -r 2>/dev/null || true
fi
if ! command -v graphify >/dev/null 2>&1; then
  echo "[오류] graphify: command not found"
  exit 1
fi

echo "[4/9] 설치 버전 확인"
installed_graphify="$(graphify --version 2>&1)" || {
  heal_setup 11 "SETUP_GRAPHIFY_TERMUX.sh graphify version command failed" || exit 1
  installed_graphify="$(graphify --version 2>&1)" || exit 1
}
echo "$installed_graphify"
if ! printf '%s' "$installed_graphify" | grep -Eq "(^|[^0-9])${GRAPHIFY_VERSION//./\\.}([^0-9]|$)"; then
  echo "[복구] 검증 버전 불일치 → $GRAPHIFY_VERSION 자동복구"
  heal_setup 11 "SETUP_GRAPHIFY_TERMUX.sh pinned version mismatch" || exit 1
  installed_graphify="$(graphify --version 2>&1)" || exit 1
  if ! printf '%s' "$installed_graphify" | grep -Eq "(^|[^0-9])${GRAPHIFY_VERSION//./\\.}([^0-9]|$)"; then
    echo "[오류] 자동복구 후에도 Graphify $GRAPHIFY_VERSION이 아닙니다: $installed_graphify"
    exit 1
  fi
fi

echo "[5/9] Graphify 자가복구/자가학습 엔진 안전검사"
python "$SELF_HEAL" --self-test || exit 1

echo "[6/9] OpenAI/Codex 프로젝트 연동"
if ! graphify codex install --project; then
  if ! graphify install --project --platform codex; then
    echo "[복구] Codex 프로젝트 연동 실패 → 학습형 연동복구"
    heal_setup 40 "SETUP_GRAPHIFY_TERMUX.sh codex install failed" || exit 1
  fi
fi
graphify agents install --project >/dev/null 2>&1 || \
  graphify install --project --platform agents >/dev/null 2>&1 || true
if [ ! -f AGENTS.md ]; then
  echo "[복구] AGENTS.md가 생성되지 않았습니다 → Codex 연동 재복구"
  heal_setup 40 "SETUP_GRAPHIFY_TERMUX.sh AGENTS.md missing after codex install" || exit 1
fi

echo "[7/9] 최초 코드 지도 생성/무결성 검증"
bash ./GRAPHIFY_UPDATE.sh || exit 1

echo "[8/9] Git 변경 시 지도 자동갱신 훅 설치"
if ! graphify hook install || ! graphify hook status; then
  echo "[복구] Graphify Git hook 실패 → 자가학습 hook 복구"
  heal_setup 41 "SETUP_GRAPHIFY_TERMUX.sh graphify hook failed" || exit 1
  graphify hook status || exit 1
fi

echo "[9/9] 태블릿 원격 업데이트 후 지도 자동갱신 연결"
if [ -d .git/hooks ]; then
  POST_MERGE=".git/hooks/post-merge"
  ORIGINAL=".git/hooks/post-merge.tcg-pre-graphify"
  if [ -f "$POST_MERGE" ] && ! grep -Fq 'TCG_GRAPHIFY_POST_MERGE' "$POST_MERGE"; then
    if [ ! -e "$ORIGINAL" ]; then
      cp -p "$POST_MERGE" "$ORIGINAL" 2>/dev/null || true
      chmod +x "$ORIGINAL" 2>/dev/null || true
    fi
  fi
  if [ ! -f "$POST_MERGE" ] || ! grep -Fq 'TCG_GRAPHIFY_POST_MERGE' "$POST_MERGE"; then
    cat > "$POST_MERGE" <<'HOOK'
#!/data/data/com.termux/files/usr/bin/bash
# TCG_GRAPHIFY_POST_MERGE
set +e
HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
REPO_DIR="$(CDPATH= cd -- "$HOOK_DIR/../.." 2>/dev/null && pwd)"
ORIGINAL="$HOOK_DIR/post-merge.tcg-pre-graphify"
if [ -x "$ORIGINAL" ]; then
  "$ORIGINAL" "$@" || true
fi
if [ -n "$REPO_DIR" ] && [ -f "$REPO_DIR/GRAPHIFY_UPDATE.sh" ]; then
  (cd "$REPO_DIR" && bash ./GRAPHIFY_UPDATE.sh --quiet >/dev/null 2>&1) &
fi
exit 0
HOOK
    chmod +x "$POST_MERGE" 2>/dev/null || true
  fi
  echo "[OK] main fast-forward 후 Graphify 지도 자동갱신 연결 완료"
else
  echo "[안내] .git/hooks가 없어 원격 업데이트 후 자동갱신 연결은 건너뜁니다."
fi

cat <<EOF

========================================
[완료] Graphify 설치 및 코드지도 설정 성공
========================================
- 검증 버전: Graphify $GRAPHIFY_VERSION
- 코드 지도: graphify-out/graph.html
- 요약 보고서: graphify-out/GRAPH_REPORT.md
- 그래프 데이터: graphify-out/graph.json
- 오류학습: graphify_self_heal_memory.json (기기 로컬)
- 자가복구 결과: graphify_self_heal_report.json (기기 로컬)
- 미해결 오류후보: graphify_self_heal_candidates.json (발생 시 기기 로컬)
- 복구 전 지도보존: .graphify_recovery/ (최대 6세대)
- 터미널 갱신: bash GRAPHIFY_UPDATE.sh
- 자동 갱신 상태: graphify hook status

자가복구는 오류 메시지를 정규화한 '오류서명' 단위로 원인을 분류하고,
같은 오류에서 과거 성공률이 높은 검증 전략을 먼저 사용합니다.
자동수정 범위는 Graphify PATH/검증버전/코드지도/Codex 연동/Git hook으로 제한됩니다.
TCG 원본 소스코드를 로그에서 생성한 임의 패치로 수정하거나 자동 commit/push하지 않습니다.
자동복구가 모두 실패하면 원인서명을 후보 JSON에 남겨 다음 코드 검토에 사용합니다.

중요: ChatGPT 모바일 앱 자체는 태블릿 로컬 훅을 직접 실행하지 않습니다.
OpenAI 자동 지도 우선 사용은 Codex 프로젝트의 AGENTS.md/Graphify 스킬을 사용합니다.
EOF
