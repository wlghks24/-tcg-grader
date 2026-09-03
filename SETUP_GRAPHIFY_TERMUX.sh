#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
[ -n "$SCRIPT_DIR" ] && cd "$SCRIPT_DIR"

GRAPHIFY_VERSION="${GRAPHIFY_VERSION:-0.9.53}"
GRAPHIFY_SPEC="graphifyy==$GRAPHIFY_VERSION"

printf '%s\n' "========================================"
printf '%s\n' " TCG Grader · Graphify 설치/코드지도 설정"
printf '%s\n' "========================================"

# 1) Platform detection.
if [ -n "${TERMUX_VERSION:-}" ] || printf '%s' "${PREFIX:-}" | grep -q 'com.termux'; then
  echo "[1/9] 운영체제: Android + Termux 확인"
else
  echo "[안내] 이 스크립트는 Android/Termux용입니다. 현재 환경을 Termux로 확인하지 못했습니다."
  echo "       Mac/Windows에서는 GRAPHIFY_CHATGPT_GUIDE.md 안내를 사용하세요."
fi

# 2) Python >= 3.10.
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

# 3) Install the repository-verified Graphify version. New upstream releases are
# not auto-adopted on the tablet until CI has verified the command contract.
echo "[3/9] Graphify 검증 버전 준비: $GRAPHIFY_VERSION"
export PATH="$HOME/.local/bin:$PATH"
current_graphify="$(graphify --version 2>/dev/null || true)"
if printf '%s' "$current_graphify" | grep -Eq "(^|[^0-9])${GRAPHIFY_VERSION//./\\.}([^0-9]|$)"; then
  echo "[OK] 이미 검증 버전 사용 중: $current_graphify"
else
  if command -v uv >/dev/null 2>&1; then
    echo "[설치] uv → $GRAPHIFY_SPEC"
    uv tool install --force "$GRAPHIFY_SPEC" || exit 1
    uv tool update-shell >/dev/null 2>&1 || true
  else
    echo "[설치] uv 없음 → pipx → $GRAPHIFY_SPEC"
    if ! command -v pipx >/dev/null 2>&1; then
      python -m pip install pipx || exit 1
    fi
    python -m pipx ensurepath >/dev/null 2>&1 || true
    python -m pipx install --force "$GRAPHIFY_SPEC" || exit 1
  fi
fi

# 4) PATH recovery.
export PATH="$HOME/.local/bin:$PATH"
if ! grep -Fq 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# Graphify / pipx / uv tools\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
fi
hash -r 2>/dev/null || true

if ! command -v graphify >/dev/null 2>&1 && [ -x "$HOME/.local/bin/graphify" ]; then
  export PATH="$HOME/.local/bin:$PATH"
fi
if ! command -v graphify >/dev/null 2>&1; then
  echo "[오류] graphify: command not found"
  echo '       export PATH="$HOME/.local/bin:$PATH"'
  echo '       source ~/.bashrc'
  exit 1
fi

# 5) Exact version contract.
echo "[4/9] 설치 버전 확인"
installed_graphify="$(graphify --version 2>&1)" || exit 1
echo "$installed_graphify"
if ! printf '%s' "$installed_graphify" | grep -Eq "(^|[^0-9])${GRAPHIFY_VERSION//./\\.}([^0-9]|$)"; then
  echo "[오류] 검증된 Graphify $GRAPHIFY_VERSION 버전과 다릅니다."
  exit 1
fi

# 6) Bounded learning engine self-test. It may select only code-defined repair
# strategies; learned JSON can never inject commands or edit/commit repository code.
echo "[5/9] Graphify 자가복구/학습 엔진 안전검사"
python ./GRAPHIFY_SELF_HEAL.py --self-test || exit 1

# 7) OpenAI/Codex + generic Agent Skills integration.
echo "[6/9] OpenAI/Codex 프로젝트 연동"
graphify codex install --project || graphify install --project --platform codex || exit 1
graphify agents install --project >/dev/null 2>&1 || graphify install --project --platform agents >/dev/null 2>&1 || true

# 8) Build map and Graphify's own git hooks.
echo "[7/9] 최초 코드 지도 생성/검증"
bash ./GRAPHIFY_UPDATE.sh || exit 1

echo "[8/9] Git 변경 시 지도 자동갱신 훅 설치"
graphify hook install || exit 1
graphify hook status || exit 1

# 9) Android updater uses `git merge --ff-only`, so attach a post-merge bridge.
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
- 터미널 갱신: bash GRAPHIFY_UPDATE.sh
- 자동 갱신 상태: graphify hook status

자가복구는 PATH/버전 불일치/지도 산출물 누락/갱신 실패/훅 실패를 분류하고,
검증된 재설치·재생성·훅복구 전략의 성공률만 학습합니다.
학습파일의 내용을 명령으로 실행하거나 코드를 임의 수정/커밋하지 않습니다.

중요: ChatGPT 모바일 앱 자체는 태블릿 로컬 훅을 직접 실행하지 않습니다.
OpenAI 자동 지도 우선 사용은 Codex 프로젝트의 AGENTS.md/Graphify 스킬을 사용합니다.
EOF
