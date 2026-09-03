#!/data/data/com.termux/files/usr/bin/bash
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" 2>/dev/null && pwd)"
cd "$SCRIPT_DIR"

OFFICIAL_REPO="wlghks24/-tcg-grader"
is_official_origin() {
  case "${1:-}" in
    https://github.com/wlghks24/-tcg-grader|https://github.com/wlghks24/-tcg-grader.git|https://github.com/wlghks24/-tcg-grader/|https://github.com/wlghks24/-tcg-grader.git/|git@github.com:wlghks24/-tcg-grader|git@github.com:wlghks24/-tcg-grader.git|ssh://git@github.com/wlghks24/-tcg-grader|ssh://git@github.com/wlghks24/-tcg-grader.git)
      return 0 ;;
    *) return 1 ;;
  esac
}

echo "========================================"
echo " TCG 태블릿 최종 적용 사전검사"
echo "========================================"

required_files="
ANDROID_RECOVER_UPDATE.sh
ANDROID_UPDATE_AND_START.sh
ANDROID_AUTO_START_INSTALL.sh
START_TCG_UPDATER_ANDROID.sh
runtime_bundle_guard_v143.py
collection_learning_hardening_v144.py
event_source_overlay_v144.py
event_source_expansion_v145.py
runtime_optimization_hardening.py
safe_runtime.py
auto_repair_engine.py
auto_update_all.py
collector_self_healing.py
tcg_code_repair_learning.py
csp_hash_hardening.py
index.html
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

echo "[1/9] 필수 파일 확인: OK"

bash -n ANDROID_RECOVER_UPDATE.sh
bash -n ANDROID_UPDATE_AND_START.sh
bash -n ANDROID_AUTO_START_INSTALL.sh
bash -n START_TCG_UPDATER_ANDROID.sh
bash -n GRAPHIFY_UPDATE.sh
bash -n SETUP_GRAPHIFY_TERMUX.sh
echo "[2/9] Android/Graphify 셸 문법: OK"

python -m py_compile \
  safe_runtime.py \
  auto_repair_engine.py \
  auto_update_all.py \
  collector_self_healing.py \
  tcg_code_repair_learning.py \
  runtime_optimization_hardening.py \
  csp_hash_hardening.py \
  GRAPHIFY_SELF_HEAL.py \
  GRAPHIFY_AUDIT.py \
  runtime_bundle_guard_v143.py \
  collection_learning_hardening_v144.py \
  event_source_overlay_v144.py \
  event_source_expansion_v145.py
echo "[3/9] 핵심 Python 문법/컴파일: OK"

python runtime_optimization_hardening.py --check >/dev/null
python tcg_code_repair_learning.py --self-test >/dev/null
python GRAPHIFY_SELF_HEAL.py --self-test >/dev/null
echo "[4/9] 최적화 하드닝/오류학습/자가복구 자체시험: OK"

python csp_hash_hardening.py --check >/dev/null
echo "[5/9] 브라우저 인라인 스크립트 CSP 해시: OK"

python - <<'PY'
import json
import tempfile
from pathlib import Path

import auto_update_all
import collector_self_healing
import tcg_code_repair_learning
import runtime_bundle_guard_v143
import event_source_expansion_v145
import GRAPHIFY_AUDIT
import GRAPHIFY_SELF_HEAL

assert tcg_code_repair_learning.CODE_REPAIR_CODES
assert tcg_code_repair_learning.PLAYBOOKS
assert collector_self_healing.POLICIES
assert "SOURCE_STRUCTURE_CHANGED" in collector_self_healing.QUARANTINE_CODES
assert callable(getattr(collector_self_healing, "_plan_from_row", None))
assert "collector_self_healing.py" in runtime_bundle_guard_v143.REQUIRED_FILES
assert "tcg_code_repair_learning.py" in runtime_bundle_guard_v143.REQUIRED_FILES
source_expansion=event_source_expansion_v145.apply()
assert source_expansion.get('patch') == 145
assert source_expansion.get('static_target_cells') == 9
assert source_expansion.get('scoped_learned_host_queries') is True
assert source_expansion.get('trust_auto_promotion') is False
assert float(source_expansion.get('unverified_source_learning_weight',-1)) == 0.0
assert int(source_expansion.get('max_hosts_per_scoped_query') or 0) <= 8
recovered = {
    "file": "releases.json",
    "ok": True,
    "collection_errors": ["NameError: historical diagnostic"],
    "remaining_collection_errors": [],
    "error": "NameError: historical diagnostic",
    "self_heal_policy": "transient_balanced",
}
assert tcg_code_repair_learning._details(recovered) == []
assert auto_update_all._result_error_details({
    "ok": True,
    "collection_errors": ["TIMEOUT: historical diagnostic"],
    "remaining_collection_errors": [],
    "error": "TIMEOUT: historical diagnostic",
}) == []
assert auto_update_all._timeout_only_errors(["TIMEOUT: source 30초 초과"])
assert not auto_update_all._timeout_only_errors([
    "TIMEOUT: source 30초 초과", "ValueError: malformed data"
])
assert not auto_update_all._timeout_only_errors(["ValueError: malformed data after timeout"])
assert not auto_update_all._timeout_only_errors(["HTTPError: status 429 after timeout"])
assert not auto_update_all._deferred_timeout_eligible({
    "ok": False,
    "timeout_exhausted": True,
    "collection_errors": ["ValueError: malformed data after timeout"],
})
update_source = Path("auto_update_all.py").read_text(encoding="utf-8")
assert "msg=f'{type(exc).__name__}: {exc}'; errors.append(msg)" not in update_source
assert "msg=diagnostic_exception(exc,1200); errors.append(msg)" in update_source
assert "errors=[auto_repair_engine.redact_sensitive(x,600) for x in (extra.get('errors') or [])" in update_source
assert "if stat_key == '__integration__' and _timeout_only_errors(errors):" in update_source
assert "'timeout_only_cache_fallback':True" in update_source
assert '"timeout_exhausted":_timeout_only_errors(warnings)' in update_source
assert "timeout_only_failure=_timeout_only_errors(errors)" in update_source
assert "timed_out=_timeout_only_errors(errors)" in update_source

# A recovered row may keep old diagnostics for display, but it must not be
# quarantined again as a current failure. Use a temporary memory file so the
# tablet's learned runtime state is never changed by this preflight.
with tempfile.TemporaryDirectory() as tmp:
    memory = Path(tmp) / "collector_self_heal_memory.json"
    original_observe = collector_self_healing.tcg_code_repair_learning.observe
    collector_self_healing.tcg_code_repair_learning.observe = lambda report: {"ok": True}
    try:
        observed = collector_self_healing.observe({"results": [recovered]}, path=memory)
    finally:
        collector_self_healing.tcg_code_repair_learning.observe = original_observe
    payload = json.loads(memory.read_text(encoding="utf-8"))
    assert observed["quarantined_for_code_repair"] == 0
    assert payload.get("quarantine") == []

safety = tcg_code_repair_learning._default_memory()["safety"]
assert safety["learned_text_executable"] is False
assert safety["source_rewrite"] is False
assert safety["git_write"] is False
assert safety["unverified_data_promotion"] is False
assert safety["allowlisted_playbooks_only"] is True

# Self-learning may rank code-defined policies/playbooks, but it must never turn
# learned text into executable repair code or close a fix without the complete
# verification playbook. These contracts also ensure concurrent tablet/PC jobs
# serialize their learning-memory transactions rather than overwriting each other.
repair_contracts = tcg_code_repair_learning.safety_contract_status()
collector_contracts = collector_self_healing.safety_contract_status()
assert repair_contracts and all(repair_contracts.values()), repair_contracts
assert collector_contracts and all(collector_contracts.values()), collector_contracts
assert set(tcg_code_repair_learning._required_check_ids("INTERNAL_CODE_ERROR")) == {
    "graphify_map_review", "python_compile", "collector_smoke", "runtime_bundle_guard"
}
repair_source = Path("tcg_code_repair_learning.py").read_text(encoding="utf-8")
assert "regression_episode = bool(" in repair_source
assert 'same_episode["verified_fix_regressions"] == 0' in repair_source

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
grep -Fq 'OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"' ANDROID_UPDATE_AND_START.sh
grep -Fq 'mktemp -d "$RUNTIME_BACKUP_DIR/' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if [ -L "$RUNTIME_BACKUP_DIR" ]; then' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if [ -L "$changed" ]; then' ANDROID_UPDATE_AND_START.sh
grep -Fq 'if ! is_runtime_path "$changed"; then' ANDROID_UPDATE_AND_START.sh
grep -Fq '[ -f "$manifest" ] && [ ! -L "$manifest" ] || return 1' ANDROID_UPDATE_AND_START.sh
grep -Fq 'restore_tmp=".${changed}.tcg-restore.$$"' ANDROID_UPDATE_AND_START.sh
grep -Fq 'fatal_restore_error=1' ANDROID_UPDATE_AND_START.sh
if grep -F 'find "$RUNTIME_BACKUP_DIR"' ANDROID_UPDATE_AND_START.sh >/dev/null; then
  echo "[오류] Android 런타임 복원본을 실제 생성 경로가 아닌 디렉터리 정렬로 다시 선택합니다."
  exit 17
fi
grep -Fq "OFFICIAL_HTTPS='https://github.com/wlghks24/-tcg-grader.git'" ANDROID_RECOVER_UPDATE.sh
grep -Fq "script-src 'self' 'sha256-" index.html
if grep -F "script-src 'self' 'unsafe-inline'" index.html >/dev/null; then
  echo "[오류] script-src에 unsafe-inline이 다시 활성화되었습니다."
  exit 16
fi
echo "[6/9] 통합/보안/코드지도 범위 계약: OK"

if [ -s graphify-out/graph.json ] || [ -s graphify-out/GRAPH_REPORT.md ] || [ -s graphify-out/graph.html ]; then
  if [ ! -s graphify-out/graph.json ] || [ ! -s graphify-out/GRAPH_REPORT.md ] || [ ! -s graphify-out/graph.html ]; then
    echo "[오류] Graphify 지도 산출물이 일부만 존재합니다. bash GRAPHIFY_UPDATE.sh로 복구하세요."
    exit 15
  fi
  python GRAPHIFY_SELF_HEAL.py --validate-only >/dev/null
  python GRAPHIFY_AUDIT.py --strict --no-write >/dev/null
  echo "[7/9] 기존 코드지도 무결성/범위 감사: OK"
else
  echo "[7/9] 기존 코드지도 없음: 최초 SETUP_GRAPHIFY_TERMUX.sh에서 생성 예정"
fi

if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  origin_url="$(git remote get-url origin 2>/dev/null || true)"
  if ! is_official_origin "$origin_url"; then
    echo "[오류] origin 원격 저장소가 공식 TCG 저장소($OFFICIAL_REPO)가 아닙니다."
    echo "       현재 origin: ${origin_url:-없음}"
    exit 21
  fi
  echo "[8/9] 공식 GitHub origin 확인: OK"

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
else
  echo "[오류] Git 저장소 상태를 확인할 수 없습니다."
  exit 22
fi

echo "[9/9] Git 최신본 일치 검사: OK"
echo "========================================"
echo "[OK] 태블릿 최종 적용 사전검사 통과"
echo "========================================"