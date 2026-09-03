#!/data/data/com.termux/files/usr/bin/bash
set -u

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
[ -n "$SCRIPT_DIR" ] && cd "$SCRIPT_DIR"

printf '%s\n' "========================================"
printf '%s\n' " TCG Grader · Graphify 설치/코드지도 설정"
printf '%s\n' "========================================"

# 1) Platform detection: this project is currently run on Android + Termux.
if [ -n "${TERMUX_VERSION:-}" ] || printf '%s' "${PREFIX:-}" | grep -q 'com.termux'; then
  echo "[1/8] 운영체제: Android + Termux 확인"
else
  echo "[안내] 이 스크립트는 Android/Termux용입니다. 현재 환경을 Termux로 확인하지 못했습니다."
  echo "       Mac/Windows에서는 GRAPHIFY_CHATGPT_GUIDE.md의 해당 안내를 사용하세요."
fi

# 2) Python >= 3.10
if ! command -v python >/dev/null 2>&1; then
  echo "[2/8] Python 없음 → Termux Python을 설치합니다."
  if command -v pkg >/dev/null 2>&1; then
    pkg install python -y || exit 1
  else
    echo "[오류] pkg 명령이 없습니다. Python 3.10+를 먼저 설치하세요."
    exit 1
  fi
fi

python - <<'PY'
import sys
print(f"[2/8] Python: {sys.version.split()[0]}")
if sys.version_info < (3, 10):
    raise SystemExit(10)
PY
py_status=$?
if [ "$py_status" -eq 10 ]; then
  echo "[안내] Python 3.10 미만입니다. Termux 패키지를 최신화한 뒤 Python을 다시 설치합니다."
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

# 3) Install Graphify. Prefer existing uv; if uv is unavailable use pipx as requested.
echo "[3/8] Graphify 설치 준비"
if command -v uv >/dev/null 2>&1; then
  echo "[OK] uv 발견: $(uv --version 2>/dev/null || true)"
  if uv tool list 2>/dev/null | grep -q '^graphifyy '; then
    uv tool upgrade graphifyy || exit 1
  else
    uv tool install graphifyy || exit 1
  fi
  uv tool update-shell >/dev/null 2>&1 || true
else
  echo "[안내] uv가 없어 pipx 방식으로 설치합니다."
  if ! command -v pipx >/dev/null 2>&1; then
    python -m pip install pipx || exit 1
  fi
  python -m pipx ensurepath >/dev/null 2>&1 || true
  if python -m pipx list 2>/dev/null | grep -q 'package graphifyy '; then
    python -m pipx upgrade graphifyy || exit 1
  else
    python -m pipx install graphifyy || exit 1
  fi
fi

# 4) PATH recovery for the common ~/.local/bin install location.
export PATH="$HOME/.local/bin:$PATH"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

if ! grep -Fq 'HOME/.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  printf '\n# Graphify / pipx / uv tools\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.bashrc"
fi
hash -r 2>/dev/null || true

if ! command -v graphify >/dev/null 2>&1 && [ -x "$HOME/.local/bin/graphify" ]; then
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v graphify >/dev/null 2>&1; then
  echo "[오류] graphify: command not found"
  echo "       아래를 실행한 뒤 Termux를 다시 열어주세요:"
  echo '       export PATH="$HOME/.local/bin:$PATH"'
  echo '       source ~/.bashrc'
  exit 1
fi

# 5) Version check.
echo "[4/8] 설치 버전 확인"
graphify --version || exit 1

# 6) OpenAI/Codex + generic agent project integration.
# ChatGPT mobile app cannot execute a tablet-local PreToolUse hook itself; Codex/agent
# instruction files are the supported local coding-assistant path. The repo guide
# explains how ChatGPT uses committed/retrieved graph artifacts instead.
echo "[5/8] OpenAI/Codex 프로젝트 연동"
graphify codex install --project || graphify install --project --platform codex || exit 1
# Also install the cross-framework Agent Skills copy when supported.
graphify agents install --project >/dev/null 2>&1 || graphify install --project --platform agents >/dev/null 2>&1 || true

# 7) Build initial code-only map and enable Graphify's own git hooks.
echo "[6/8] 최초 코드 지도 생성"
bash ./GRAPHIFY_UPDATE.sh || exit 1

echo "[7/8] Git 변경 시 지도 자동갱신 훅 설치"
graphify hook install || exit 1
graphify hook status 2>/dev/null || true

# 8) The tablet updater advances main with `git merge --ff-only`, which fires
# post-merge rather than post-commit/post-checkout. Add a small wrapper so remote
# ChatGPT/GitHub commits also refresh the local code map after the tablet pulls.
echo "[8/8] 태블릿 원격 업데이트 후 지도 자동갱신 연결"
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

cat <<'EOF'

========================================
[완료] Graphify 설치 및 코드지도 설정 성공
========================================
- 버전 확인: graphify --version
- 코드 지도: graphify-out/graph.html
- 요약 보고서: graphify-out/GRAPH_REPORT.md
- 그래프 데이터: graphify-out/graph.json
- 터미널에서 변경분 갱신: graphify update .
- AI 스킬 안에서 변경분 갱신: /graphify . --update
- Codex에서는 스킬 호출 문법이 $graphify 입니다.
- 자동 갱신 상태: graphify hook status
- 태블릿이 원격 main을 fast-forward 한 뒤에도 지도를 백그라운드 갱신합니다.

중요: ChatGPT 모바일 앱 자체에는 태블릿 로컬 훅을 직접 실행하는 기능이 없습니다.
OpenAI 쪽 자동 지도 우선 사용은 Codex 프로젝트의 AGENTS.md/Graphify 스킬로 적용하며,
ChatGPT에서 GitHub 프로젝트를 작업할 때는 graphify-out/GRAPH_REPORT.md와 graph.json을
저장소에 제공한 경우 그 자료를 코드 구조 참고용으로 사용할 수 있습니다.
EOF
