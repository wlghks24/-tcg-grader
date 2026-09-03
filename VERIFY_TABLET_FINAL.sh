#!/data/data/com.termux/files/usr/bin/bash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo " TCG 태블릿 최종 적용 사전검사"
echo "========================================"

required_files="
ANDROID_RECOVER_UPDATE.sh
ANDROID_UPDATE_AND_START.sh
START_TCG_UPDATER_ANDROID.sh
runtime_bundle_guard_v143.py
safe_runtime.py
auto_repair_engine.py
auto_update_all.py
collector_self_healing.py
tcg_code_repair_learning.py
GRAPHIFY_UPDATE.sh
GRAPHIFY_SELF_HEAL.py
GRAPHIFY_AUDIT.py
SETUP_GRAPHIFY_TERMUX.sh
.graphifyignore
.gitignore
"

missing=0
for file in $required_files; do
  if [ ! -s "$file" ]; then
    echo "[오류] 필수 파일 누락: $file"
    missing=1
  fi
done
[ "$missing" -eq 0 ] || exit 10

echo "[1/7] 필수 파일 확인: OK"

bash -n ANDROID_RECOVER_UPDATE.sh
bash -n ANDROID_UPDATE_AND_START.sh
bash -n START_TCG_UPDATER_ANDROID.sh
bash -n GRAPHIFY_UPDATE.sh
bash -n SETUP_GRAPHIFY_TERMUX.sh
echo "[2/7] Android/Graphify 셸 문법: OK"

python -m py_compile \
  safe_runtime.py \
  auto_repair_engine.py \
  auto_update_all.py \
  collector_self_healing.py \
  tcg_code_repair_learning.py \
  GRAPHIFY_SELF_HEAL.py \
  GRAPHIFY_AUDIT.py \
  runtime_bundle_guard_v143.py
echo "[3/7] 핵심 Python 문법/컴파일: OK"

python tcg_code_repair_learning.py --self-test >/dev/null
python GRAPHIFY_SELF_HEAL.py --self-test >/dev/null
echo "[4/7] 오류학습/자가복구 자체시험: OK"

python - <<'PY'
import collector_self_healing
import tcg_code_repair_learning
import GRAPHIFY_AUDIT
import GRAPHIFY_SELF_HEAL

assert tcg_code_repair_learning.CODE_REPAIR_CODES
assert tcg_code_repair_learning.PLAYBOOKS
assert collector_self_healing.POLICIES
assert "SOURCE_STRUCTURE_CHANGED" in collector_self_healing.QUARANTINE_CODES

safety = tcg_code_repair_learning._default_memory()["safety"]
assert safety["learned_text_executable"] is False
assert safety["source_rewrite"] is False
assert safety["git_write"] is False
assert safety["unverified_data_promotion"] is False
assert safety["allowlisted_playbooks_only"] is True

rules, ignore_errors = GRAPHIFY_AUDIT._load_ignore_rules()
assert not ignore_errors, ignore_errors
assert GRAPHIFY_AUDIT._ignored_reason('.codex/skills/graphify/SKILL.md', rules)
assert GRAPHIFY_AUDIT._ignored_reason('.agents/skills/graphify/SKILL.md', rules)
assert GRAPHIFY_AUDIT._ignored_reason('AGENTS.md', rules)
assert GRAPHIFY_AUDIT._ignored_reason('tcg_live_data.json', rules)
assert GRAPHIFY_AUDIT._ignored_reason('.env.example', rules) is None
assert GRAPHIFY_SELF_HEAL.FAILURE_CODE_CATEGORY[25] == 'map_audit_failed'
assert GRAPHIFY_SELF_HEAL.CLUSTER_ARGS[-2:] == ('--exclude-hubs', '99')
print("TCG + Graphify bounded safety contracts: OK")
PY

grep -Fq 'import tcg_code_repair_learning' collector_self_healing.py
grep -Fq 'tcg_code_repair_learning.json' .gitignore
grep -Fq 'tcg_code_repair_candidates.json' .gitignore
grep -Fq 'tcg_code_repair_report.json' .gitignore
grep -Fq 'GRAPHIFY_VERSION="${GRAPHIFY_VERSION:-0.9.53}"' SETUP_GRAPHIFY_TERMUX.sh
grep -Fxq '.codex/' .graphifyignore
grep -Fxq '.agents/' .graphifyignore
grep -Fxq 'AGENTS.md' .graphifyignore
echo "[5/7] 통합/보안/코드지도 범위 계약: OK"

if [ -s graphify-out/graph.json ] || [ -s graphify-out/GRAPH_REPORT.md ] || [ -s graphify-out/graph.html ]; then
  if [ ! -s graphify-out/graph.json ] || [ ! -s graphify-out/GRAPH_REPORT.md ] || [ ! -s graphify-out/graph.html ]; then
    echo "[오류] Graphify 지도 산출물이 일부만 존재합니다. bash GRAPHIFY_UPDATE.sh로 복구하세요."
    exit 15
  fi
  python GRAPHIFY_SELF_HEAL.py --validate-only >/dev/null
  python GRAPHIFY_AUDIT.py --strict --no-write >/dev/null
  echo "[6/7] 기존 코드지도 무결성/범위 감사: OK"
else
  echo "[6/7] 기존 코드지도 없음: 최초 SETUP_GRAPHIFY_TERMUX.sh에서 생성 예정"
fi

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  local_head="$(git rev-parse HEAD)"
  echo "현재 로컬 빌드: ${local_head:0:12}"
  if [ "${TCG_FINAL_SKIP_HEAD_MATCH:-0}" != "1" ] && git rev-parse origin/main >/dev/null 2>&1; then
    remote_head="$(git rev-parse origin/main)"
    echo "origin/main 빌드: ${remote_head:0:12}"
    if [ "$local_head" != "$remote_head" ]; then
      echo "[오류] 태블릿 코드가 origin/main 최신본과 다릅니다."
      echo "       git fetch origin main 후 Android 복구 업데이트를 다시 실행하세요."
      exit 20
    fi
  fi
fi

echo "[7/7] Git 최신본 일치 검사: OK"
echo "========================================"
echo "[OK] 태블릿 최종 적용 사전검사 통과"
echo "========================================"
