#!/usr/bin/env bash
# Reuse the reviewed Android launcher, including its checks/watchers/single lock.
# No root-source edits or extra scheduler. Existing cleanup/watchers are reused.
set -euo pipefail
if [ "${BASH_VERSINFO[0]}" -lt 5 ]; then
  echo 'HOLD: 통합 실행에는 Bash 5 이상이 필요합니다.' >&2
  exit 2
fi
case "${1:-}" in
  ''|--check) ;;
  *) echo '사용법: bash execution/start_tablet_unified_v897.sh [--check]' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then exit 2; fi
TCG_V897_ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
TCG_V897_PYTHON="$(type -P python)"
export TCG_V897_PYTHON
cd "$TCG_V897_ROOT"
"$TCG_V897_PYTHON" - "$TCG_V897_ROOT" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1])
launcher=root/'START_TCG_UPDATER_ANDROID.sh'
expected='f885535c224584ce2fb1a4bb16978e707b5661d002b9f888a524f69a34403667'
if launcher.is_symlink() or hashlib.sha256(launcher.read_bytes()).hexdigest()!=expected:
    raise SystemExit('HOLD: 기존 Android 실행기 버전이 다릅니다. 파일 보존 후 재검토가 필요합니다.')
manifest_path=root/'integrity_manifest.json'
if manifest_path.is_symlink(): raise SystemExit('HOLD: manifest symlink')
manifest=json.loads(manifest_path.read_text(encoding='utf-8'))['files']
required=(
    'tablet_unified_runtime_v889.py','tablet_image_unified_v888.py',
    'tablet_image_recheck_review_v887.py','tablet_image_reciprocity_v887.py',
    'tablet_image_recheck_cycle_v887.py','tablet_unified_ui_v890.py',
    'tablet_event_summary_v890.py','tablet_event_freshness_v891.py',
    'tablet_entity_store_v892.py','tablet_backlog_priority_v893.py',
    'tablet_feature_inventory_v894.py','tablet_target_image_v895.py',
    'tablet_event_coverage_v896.py','tablet_device_readback_v897.py',
    'apply_tablet_candidate_v897.py',
    'tablet_live_view_v898.py',
    'tablet_provider_json_v900.py',
    'tablet_collection_receipt_v901.py','tablet_display_fast_v901.py',
    'tablet_menu_shell_v903.py','tablet_menu_shell_v903.js',
    'tablet_card_facts_v904.py','tablet_card_view_v904.py','tablet_catalog_bridge.py',
)
for name in required:
    key='execution/'+name
    path=root/key
    if path.is_symlink() or path.parent.is_symlink(): raise SystemExit('HOLD: source symlink')
    raw=path.read_bytes()
    pin=manifest[key]
    if len(raw)!=pin['bytes'] or hashlib.sha256(raw).hexdigest()!=pin['sha256']:
        raise SystemExit('HOLD: 통합 실행 파일 해시 불일치: '+name)
    if path.suffix == '.py': compile(raw,str(path),'exec')
print('CODE_CHECK_OK: 기존 실행기와 통합 모듈 해시·문법 확인. 실기기 적용 확인은 별도입니다.',flush=True)
PY
if [ "${1:-}" = --check ]; then exit 0; fi
"$TCG_V897_PYTHON" -c 'from pathlib import Path; from execution.apply_tablet_candidate_v897 import require_startup_readiness; require_startup_readiness(Path.cwd())'

# V902: keep dispatch in this Bash. Exported-function import at a new shell
# boundary is not a reliable entrypoint contract on every native installation.
# Only the final server command changes; external nohup Python watchers do not.
unalias python 2>/dev/null || true
python() {
  if [ "$#" -eq 1 ] && [ "$1" = tcg_updater_v135.py ]; then
    echo '[TCG_UNIFIED_V902] 통합 런타임 서버 진입' >&2
    exec "$TCG_V897_PYTHON" -m execution.tablet_unified_runtime_v889
  else
    "$TCG_V897_PYTHON" "$@"
  fi
}
export -n -f python
# The immutable original uses dirname "$0". Preserve that path while sourcing;
# its last exit and EXIT/signal traps still own this process and its children.
BASH_ARGV0="$TCG_V897_ROOT/START_TCG_UPDATER_ANDROID.sh"
if [ "$0" != "$TCG_V897_ROOT/START_TCG_UPDATER_ANDROID.sh" ]; then
  echo 'HOLD: 기존 실행기의 작업 경로를 보존하지 못했습니다.' >&2
  exit 2
fi
# Restore the original launcher's option semantics rather than inheriting -e
# or pipefail from this preflight wrapper. Original START itself enables -u.
set +e
set +o pipefail
source "$TCG_V897_ROOT/START_TCG_UPDATER_ANDROID.sh"
