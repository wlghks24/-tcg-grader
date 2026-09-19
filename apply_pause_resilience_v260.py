#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p=Path(path)
    text=p.read_text(encoding='utf-8')
    if text.count(old)!=1:
        raise SystemExit(f'{path}: expected exactly one patch anchor, found {text.count(old)}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')


# v257 dependency closure: fail closed on backend imports, local browser assets,
# service-worker functional assets and the grading-company fallback snapshot.
Path('tablet_runtime_manifest.py').write_text('''#!/usr/bin/env python3
"""Single source of truth for the Android tablet runtime bundle."""
from __future__ import annotations
import argparse, ast, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ACTIVE_RUNTIME_FILES=(
"index.html","safe_runtime.py","collection_runtime_health.py","tablet_runtime_manifest.py","TABLET_SCHEDULED_UPDATE.sh",
"quality_review_policy.py","quality_review_policy_v2.json",
"auto_repair_engine.py","auto_update_all.py","collection_job_contract.py","collector_self_healing.py","tcg_code_repair_learning.py",
"tcg_updater.py","tcg_updater_v135.py","grading_accuracy_v99.py","server_security_guard.py","runtime_bundle_guard_v143.py","update_releases.py",
"update_market_watch.py","update_market_prices.py","update_promo_events.py","update_purchase_sources.py",
"update_exchange_rates.py","grading_company_watch.py","graded_photo_multi_source.py","graded_photo_manual_pair_queue.py",
"grading_cert_verifier.py","manual_collection_mode.py","manual_graded_photo_registration.py",
"manual_dual_photo_registration.py","manual_dual_photo_bridge.js","manual_official_proof.py",
"ocr_accuracy_boost_v147.py","public_ocr_accuracy_boost_v147.py","ocr_front_back_fallback_v148.py",
"legacy_ocr_registry_cleanup_v149.py","release_tcg_port.py","multi_channel_agent.py","search_method_learning.py",
"verified_grade_learning_v135.py","verified_grade_learning_v135_safe.py","event_collection_hardening_v139.py",
"event_collection_hardening_v140.py","event_collection_hardening_v141.py","collection_learning_hardening_v142.py",
"collection_learning_hardening_v144.py","event_source_overlay_v144.py","event_source_expansion_v145.py",
"event_gap_learning.py","event_priority_watch.py","event_quick_watch.py","social_event_discovery.py",
"multi_route_event_discovery.py","adaptive_collection_learner.py","verified_collection_neural.py","verified_collection_job_neural.py","fan_social_learning.py",
# Browser assets are executable/visible parts of the tablet runtime too. Keep
# them in the fail-closed manifest so a partial checkout cannot pass startup
# merely because the Python backend still compiles.
"grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js",
"grade_market_flow.js","grade_market_flow.css","grading_costs_live.js","grading_costs_live.css",
"grading_proxy_costs.js","grading_proxy_costs.css","grading_total_cost.js","grading_total_cost.css",
"inventory_lookup.js","inventory_lookup.css","auto_market_center.js","auto_market_center.css",
"multi_market_prices.js","multi_market_prices.css","auto_validation_flow.js","auto_validation_flow.css",
"graded_photo_dashboard.js","graded_photo_dashboard.css","market_catalog_expander.js","image_quality_guard.js",
"box_knowledge_stats.js","box_knowledge_stats.css","feature_category_nav.js","feature_category_nav.css",
"purchase_ui_polish.css","ui_polish_v121.css","ui_tablet_refine_v122.css",
"manifest.webmanifest","icon.svg","vision_calibration.json","grading_company_updates.json","sw.js")

_INDEX_SCRIPT_RE=re.compile(r'<script\\b[^>]*\\bsrc=["\\']([^"\\']+)["\\']',re.I)
_SW_CORE_RE=re.compile(r'const\\s+CORE\\s*=\\s*\\[(.*?)\\]\\s*;',re.S)
_QUOTED_RE=re.compile(r'["\\']([^"\\']+)["\\']')
_CRITICAL_SW_SUFFIXES={".js",".css",".webmanifest",".svg"}
_CRITICAL_SW_DATA={"vision_calibration.json","grading_company_updates.json"}

def _normalize_local_asset(value:str)->str|None:
    text=str(value or "").strip()
    if not text or text.startswith(("http://","https://","//","data:","blob:","#")):
        return None
    text=text.split("?",1)[0].split("#",1)[0].strip()
    while text.startswith("./"):
        text=text[2:]
    text=text.lstrip("/")
    return text or None

def _index_script_assets(root:Path)->list[str]:
    source=(root/"index.html").read_text(encoding="utf-8",errors="strict")
    return sorted({asset for raw in _INDEX_SCRIPT_RE.findall(source) if (asset:=_normalize_local_asset(raw))})

def _service_worker_core_assets(root:Path)->list[str]:
    source=(root/"sw.js").read_text(encoding="utf-8",errors="strict")
    match=_SW_CORE_RE.search(source)
    if not match:
        raise ValueError("sw_core_unparseable")
    return sorted({asset for raw in _QUOTED_RE.findall(match.group(1)) if (asset:=_normalize_local_asset(raw))})

def _startup_local_python_imports(root:Path)->list[str]:
    source=(root/"tcg_updater.py").read_text(encoding="utf-8",errors="strict")
    tree=ast.parse(source,filename="tcg_updater.py")
    modules:set[str]=set()
    for node in tree.body:
        if isinstance(node,ast.Import):
            modules.update(alias.name.split(".",1)[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module and node.level==0:
            modules.add(node.module.split(".",1)[0])
    files=[]
    for module in sorted(modules):
        name=f"{module}.py"
        if (root/name).is_file():
            files.append(name)
    return files

def _dependency_errors(root:Path)->list[str]:
    manifest=set(ACTIVE_RUNTIME_FILES)
    errors=[]
    try:
        for asset in _index_script_assets(root):
            if asset not in manifest:
                errors.append(f"index_script_not_manifest:{asset}")
    except (OSError,UnicodeError,ValueError) as exc:
        errors.append(f"index_dependency_scan:{type(exc).__name__}")
    try:
        for asset in _service_worker_core_assets(root):
            if Path(asset).suffix.lower() in _CRITICAL_SW_SUFFIXES or asset in _CRITICAL_SW_DATA:
                if asset not in manifest:
                    errors.append(f"sw_core_not_manifest:{asset}")
    except (OSError,UnicodeError,ValueError) as exc:
        errors.append(f"sw_dependency_scan:{type(exc).__name__}")
    try:
        for name in _startup_local_python_imports(root):
            if name not in manifest:
                errors.append(f"startup_import_not_manifest:{name}")
    except (OSError,UnicodeError,SyntaxError,ValueError) as exc:
        errors.append(f"startup_dependency_scan:{type(exc).__name__}")
    return sorted(set(errors))

def audit(root:Path=ROOT,*,compile_python:bool=False)->dict:
    missing=[]; symlinks=[]; compile_errors=[]; checked_python=0
    duplicates=sorted({name for name in ACTIVE_RUNTIME_FILES if ACTIVE_RUNTIME_FILES.count(name)>1})
    for name in ACTIVE_RUNTIME_FILES:
        path=root/name
        if not path.is_file(): missing.append(name); continue
        if path.is_symlink(): symlinks.append(name); continue
        if compile_python and path.suffix.lower()==".py":
            checked_python+=1
            try: compile(path.read_text(encoding="utf-8",errors="strict"),name,"exec",dont_inherit=True)
            except (OSError,UnicodeError,SyntaxError,ValueError,OverflowError) as exc:
                compile_errors.append({"file":name,"error":type(exc).__name__,"line":getattr(exc,"lineno",None)})
    dependency_errors=_dependency_errors(root) if not missing else []
    try:
        import quality_review_policy
        quality_policy=quality_review_policy.validate(root/"quality_review_policy_v2.json")
    except Exception as exc:
        quality_policy={"ok":False,"errors":[f"validator_error:{type(exc).__name__}"]}
    return {"ok":not missing and not symlinks and not compile_errors and not duplicates and not dependency_errors and bool(quality_policy.get("ok")),"schema_version":1,
            "active_file_count":len(ACTIVE_RUNTIME_FILES),"python_checked":checked_python,
            "missing":missing,"symlinks":symlinks,"compile_errors":compile_errors,"duplicates":duplicates,
            "dependency_errors":dependency_errors,"quality_policy":quality_policy}
def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--compile",action="store_true")
    args=p.parse_args(); result=audit(compile_python=args.compile)
    print(json.dumps(result,ensure_ascii=False,separators=(",",":"))); return 0 if result["ok"] else 1
if __name__=="__main__": raise SystemExit(main())
''',encoding='utf-8')

replace_once('sw.js',
"// v205 synchronizes topic coverage and seasonal release lifecycle.\nconst CACHE='tcg-v205-network-first-runtime';",
"// v260 closes runtime dependency gaps and hardens pause recovery.\nconst CACHE='tcg-v260-network-first-runtime';")
replace_once('sw.js',
"'./market_watch.json','./exchange_rates.json','./icon.svg']",
"'./market_watch.json','./exchange_rates.json','./grading_company_updates.json','./icon.svg']")

# Boot supervisor: avoid duplicate supervisors, preserve a wake lock while the
# supervisor is alive, and confirm transient health failures before restarting.
boot_anchor="""  echo 'LOG=TCG_ANDROID_STARTUP.log'\n  echo 'STATE=unknown'\n  echo 'stamp() { date \"+%Y-%m-%dT%H:%M:%S%z\" 2>/dev/null || date; }'\n  echo \"healthy() { python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen(\\\"http://127.0.0.1:8765/api/v135-health\\\",timeout=3)); raise SystemExit(0 if d.get(\\\"ok\\\") else 1)' >/dev/null 2>&1; }\"\n  echo 'diagnose() { printf \"[%s] \" \"$(stamp)\" >> \"$LOG\"; python tablet_runtime_probe.py >> \"$LOG\" 2>&1 || true; }'\n  echo 'rotate_log() { if [ -f \"$LOG\" ] && [ \"$(wc -c < \"$LOG\" 2>/dev/null || echo 0)\" -gt 2097152 ]; then mv -f \"$LOG\" \"$LOG.1\"; fi; }'\n  echo 'delay=30'\n  echo 'echo \"[$(stamp)] Termux:Boot supervisor started.\" >> \"$LOG\"'\n  echo 'diagnose'\n  echo 'while true; do'\n"""
boot_replacement="""  echo 'LOG=TCG_ANDROID_STARTUP.log'\n  echo 'STATE=unknown'\n  echo 'SUPERVISOR_LOCK_DIR=\"$HOME/.termux/tcg-grader-supervisor.lock\"'\n  echo 'SUPERVISOR_LOCK_PID=\"$SUPERVISOR_LOCK_DIR/pid\"'\n  echo 'WAKE_LOCKED=0'\n  echo 'FAIL_THRESHOLD=3'\n  echo 'CONFIRM_DELAY=5'\n  echo 'fail_count=0'\n  echo 'stamp() { date \"+%Y-%m-%dT%H:%M:%S%z\" 2>/dev/null || date; }'\n  echo \"healthy() { python -c 'import json,urllib.request; d=json.load(urllib.request.urlopen(\\\"http://127.0.0.1:8765/api/v135-health\\\",timeout=3)); raise SystemExit(0 if d.get(\\\"ok\\\") else 1)' >/dev/null 2>&1; }\"\n  echo 'diagnose() { printf \"[%s] \" \"$(stamp)\" >> \"$LOG\"; python tablet_runtime_probe.py >> \"$LOG\" 2>&1 || true; }'\n  echo 'rotate_log() { if [ -f \"$LOG\" ] && [ \"$(wc -c < \"$LOG\" 2>/dev/null || echo 0)\" -gt 2097152 ]; then mv -f \"$LOG\" \"$LOG.1\"; fi; }'\n  echo 'pid_is_supervisor() { pid=\"${1:-}\"; case \"$pid\" in \"\"|*[!0-9]*) return 1 ;; esac; kill -0 \"$pid\" 2>/dev/null || return 1; cmd=\"$(tr \"\\000\" \" \" < \"/proc/$pid/cmdline\" 2>/dev/null || true)\"; case \"$cmd\" in *TCG_AUTO_START.sh*) return 0 ;; *) return 1 ;; esac; }'\n  echo 'cleanup_supervisor() { rm -rf \"$SUPERVISOR_LOCK_DIR\" 2>/dev/null || true; if [ \"$WAKE_LOCKED\" = \"1\" ] && command -v termux-wake-unlock >/dev/null 2>&1; then termux-wake-unlock >/dev/null 2>&1 || true; fi; }'\n  echo 'if ! mkdir \"$SUPERVISOR_LOCK_DIR\" 2>/dev/null; then'\n  echo '  old_pid=\"\"; [ -r \"$SUPERVISOR_LOCK_PID\" ] && old_pid=\"$(cat \"$SUPERVISOR_LOCK_PID\" 2>/dev/null || true)\"'\n  echo '  if pid_is_supervisor \"$old_pid\"; then echo \"[$(stamp)] [OK] supervisor already running (PID $old_pid).\" >> \"$LOG\"; exit 0; fi'\n  echo '  rm -rf \"$SUPERVISOR_LOCK_DIR\" 2>/dev/null || true'\n  echo '  mkdir \"$SUPERVISOR_LOCK_DIR\" 2>/dev/null || { echo \"[$(stamp)] [ERROR] supervisor lock unavailable.\" >> \"$LOG\"; exit 1; }'\n  echo 'fi'\n  echo 'printf \"%s\\n\" \"$$\" > \"$SUPERVISOR_LOCK_PID\"'\n  echo 'trap cleanup_supervisor EXIT'\n  echo 'trap \"exit 130\" INT'\n  echo 'trap \"exit 143\" TERM'\n  echo 'trap \"exit 129\" HUP'\n  echo 'if command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock >/dev/null 2>&1; then WAKE_LOCKED=1; fi'\n  echo 'delay=30'\n  echo 'echo \"[$(stamp)] Termux:Boot supervisor started.\" >> \"$LOG\"'\n  echo 'diagnose'\n  echo 'while true; do'\n"""
replace_once('ANDROID_AUTO_START_INSTALL.sh',boot_anchor,boot_replacement)

loop_anchor="""  echo '  if healthy; then'\n  echo '    if [ \"$STATE\" != healthy ]; then echo \"[$(stamp)] [OK] local /api/v135-health recovered.\" >> \"$LOG\"; diagnose; fi'\n  echo '    STATE=healthy; delay=30; sleep 60; continue'\n  echo '  fi'\n  echo '  if [ \"$STATE\" != unhealthy ]; then echo \"[$(stamp)] [WARN] local health failed; recovery starts.\" >> \"$LOG\"; diagnose; fi'\n  echo '  STATE=unhealthy'\n  echo '  bash ANDROID_UPDATE_AND_START.sh >> \"$LOG\" 2>&1'\n  echo '  rc=$?'\n  echo '  if healthy; then STATE=healthy; echo \"[$(stamp)] [OK] recovery succeeded (rc=$rc).\" >> \"$LOG\"; diagnose; delay=30; sleep 60; continue; fi'\n"""
loop_replacement="""  echo '  if healthy; then'\n  echo '    if [ \"$STATE\" != healthy ]; then echo \"[$(stamp)] [OK] local /api/v135-health recovered.\" >> \"$LOG\"; diagnose; fi'\n  echo '    STATE=healthy; fail_count=0; delay=30; sleep 60; continue'\n  echo '  fi'\n  echo '  fail_count=$((fail_count+1))'\n  echo '  if [ \"$fail_count\" -lt \"$FAIL_THRESHOLD\" ]; then'\n  echo '    echo \"[$(stamp)] [WARN] health miss ${fail_count}/${FAIL_THRESHOLD}; confirming in ${CONFIRM_DELAY}s.\" >> \"$LOG\"'\n  echo '    sleep \"$CONFIRM_DELAY\"; continue'\n  echo '  fi'\n  echo '  fail_count=0'\n  echo '  if [ \"$STATE\" != unhealthy ]; then echo \"[$(stamp)] [WARN] confirmed local health failure; recovery starts.\" >> \"$LOG\"; diagnose; fi'\n  echo '  STATE=unhealthy'\n  echo '  bash ANDROID_UPDATE_AND_START.sh >> \"$LOG\" 2>&1'\n  echo '  rc=$?'\n  echo '  if healthy; then STATE=healthy; fail_count=0; echo \"[$(stamp)] [OK] recovery succeeded (rc=$rc).\" >> \"$LOG\"; diagnose; delay=30; sleep 60; continue; fi'\n"""
replace_once('ANDROID_AUTO_START_INSTALL.sh',loop_anchor,loop_replacement)
replace_once('ANDROID_AUTO_START_INSTALL.sh',
'echo "At reboot it checks origin/main before startup; while healthy it checks local /api/v135-health every 60 seconds."',
'echo "At reboot it checks origin/main before startup; while healthy it checks local /api/v135-health every 60 seconds and confirms 3 consecutive misses before recovery."')

# Stateful verified-learning work must finish. New triggers queue instead of
# cancelling the currently running Market AI tracker.
replace_once('.github/workflows/market-ai-auto-tracker.yml',
"concurrency:\n  group: ${{ github.workflow }}-${{ github.ref }}\n  cancel-in-progress: true",
"concurrency:\n  group: ${{ github.workflow }}-${{ github.ref }}\n  # Preserve the running verified-learning cycle; newer triggers queue instead.\n  cancel-in-progress: false")
replace_once('market_ai_auto_tracker.py',
'''            if "concurrency:" not in text or "cancel-in-progress: true" not in text:\n                findings.append(_finding(\n                    "MARKET_TRACKER_CONCURRENCY_GUARD_MISSING",\n                    TRACKER_WORKFLOW,\n                    "AI tracker workflow must serialize/cancel duplicate in-progress runs",\n                    severity="critical",\n                ))''',
'''            if ("concurrency:" not in text or "cancel-in-progress: false" not in text\n                    or "cancel-in-progress: true" in text):\n                findings.append(_finding(\n                    "MARKET_TRACKER_CONCURRENCY_GUARD_MISSING",\n                    TRACKER_WORKFLOW,\n                    "AI tracker workflow must serialize runs without cancelling the active verified-learning cycle",\n                    severity="critical",\n                ))''')
replace_once('test_market_ai_auto_tracker.py',
'"concurrency:\\n  group: market-ai-${{ github.ref }}\\n  cancel-in-progress: true\\n"',
'"concurrency:\\n  group: market-ai-${{ github.ref }}\\n  cancel-in-progress: false\\n"')
insert_anchor='''    def test_tracker_workflow_requires_sha_pinned_github_actions(self):\n'''
insert='''    def test_tracker_workflow_rejects_cancelling_active_verified_learning(self):\n        with tempfile.TemporaryDirectory() as tmp:\n            root = Path(tmp)\n            self._repo(root)\n            workflow = root / tracker.TRACKER_WORKFLOW\n            text = workflow.read_text(encoding="utf-8").replace(\n                "cancel-in-progress: false", "cancel-in-progress: true"\n            )\n            workflow.write_text(text, encoding="utf-8")\n            codes = {row["code"] for row in tracker.scan_static(root)}\n            self.assertIn("MARKET_TRACKER_CONCURRENCY_GUARD_MISSING", codes)\n\n'''
replace_once('test_market_ai_auto_tracker.py',insert_anchor,insert+insert_anchor)

# Shared QA requires the new pause-recovery supervisor contracts.
qa_anchor='''    "TCG_ANDROID_STARTUP.log",\n)'''
qa_new='''    "TCG_ANDROID_STARTUP.log",\n    "SUPERVISOR_LOCK_DIR",\n    "pid_is_supervisor",\n    "termux-wake-lock",\n    "FAIL_THRESHOLD=3",\n    "CONFIRM_DELAY=5",\n    "fail_count=$((fail_count+1))",\n)'''
replace_once('tablet_runtime_qa.py',qa_anchor,qa_new)

# New deterministic pause/recovery scenario tests.
Path('test_tablet_pause_recovery_v260.py').write_text(r'''#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT/name).read_text(encoding='utf-8')


class TabletPauseRecoveryV260Tests(unittest.TestCase):
    def test_generated_boot_supervisor_is_syntax_valid_and_hardened(self):
        installer=read('ANDROID_AUTO_START_INSTALL.sh')
        for marker in (
            'SUPERVISOR_LOCK_DIR', 'SUPERVISOR_LOCK_PID', 'pid_is_supervisor',
            'termux-wake-lock', 'termux-wake-unlock', 'FAIL_THRESHOLD=3',
            'CONFIRM_DELAY=5', 'fail_count=$((fail_count+1))',
            'confirmed local health failure; recovery starts.',
            'delay=30', 'delay=300', 'ANDROID_UPDATE_AND_START.sh',
        ):
            self.assertIn(marker,installer,marker)

        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'repo'; root.mkdir()
            home=Path(tmp)/'home'; home.mkdir()
            (root/'ANDROID_AUTO_START_INSTALL.sh').write_text(installer,encoding='utf-8')
            for name in (
                'tcg_updater.py','tcg_updater_v135.py','index.html',
                'START_TCG_UPDATER_ANDROID.sh','ANDROID_UPDATE_AND_START.sh',
                'VERIFY_TABLET_FINAL.sh',
            ):
                (root/name).write_text('stub\n',encoding='utf-8')
            (root/'tablet_runtime_probe.py').write_text(
                '#!/usr/bin/env python3\nimport sys\nraise SystemExit(0)\n',encoding='utf-8')
            env=dict(os.environ); env['HOME']=str(home)
            run=subprocess.run(
                ['bash','ANDROID_AUTO_START_INSTALL.sh'],cwd=root,env=env,
                text=True,capture_output=True,check=False,timeout=15,
            )
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            boot=home/'.termux/boot/TCG_AUTO_START.sh'
            self.assertTrue(boot.is_file())
            syntax=subprocess.run(['bash','-n',str(boot)],text=True,capture_output=True,check=False)
            self.assertEqual(syntax.returncode,0,syntax.stderr)
            generated=boot.read_text(encoding='utf-8')
            self.assertIn('FAIL_THRESHOLD=3',generated)
            self.assertIn('pid_is_supervisor()',generated)
            self.assertIn('termux-wake-lock',generated)

    def test_pause_scenario_contract_matrix(self):
        boot=read('ANDROID_AUTO_START_INSTALL.sh')
        update=read('ANDROID_UPDATE_AND_START.sh')
        start=read('START_TCG_UPDATER_ANDROID.sh')
        scheduled=read('TABLET_SCHEDULED_UPDATE.sh')
        scenarios={
            'transient_health_timeout': ('FAIL_THRESHOLD=3' in boot and 'CONFIRM_DELAY=5' in boot),
            'hard_server_crash': ('ANDROID_UPDATE_AND_START.sh' in boot and 'retrying in ${delay}s' in boot),
            'duplicate_supervisor': ('SUPERVISOR_LOCK_DIR' in boot and 'pid_is_supervisor' in boot),
            'stale_supervisor_pid': ('/proc/$pid/cmdline' in boot and 'rm -rf \"$SUPERVISOR_LOCK_DIR\"' in boot),
            'screen_off_doze': ('termux-wake-lock' in boot and 'termux-wake-unlock' in boot),
            'network_update_failure': ('현재 버전으로 시작합니다' in update),
            'bad_remote_candidate': ('verify_remote_candidate "$remote_head"' in update),
            'runtime_json_collision': ('.tcg_runtime_preserved' in update and 'restore_runtime_snapshot' in update),
            'port_8765_collision': ('release_tcg_port.py' in start),
            'stale_start_lock': ('.tcg_android_start.lock' in start and '종료된 이전 시작 잠금' in start),
            'scheduled_update_overlap': ('scheduled-update' in scheduled and 'acquire_lock' in scheduled),
            'bounded_retry_backoff': ('delay=30' in boot and 'delay=300' in boot),
        }
        self.assertEqual([],sorted(name for name,ok in scenarios.items() if not ok),scenarios)

    def test_stateful_market_tracker_is_serialized_without_in_progress_cancel(self):
        workflow=read('.github/workflows/market-ai-auto-tracker.yml')
        self.assertIn('concurrency:',workflow)
        self.assertIn('cancel-in-progress: false',workflow)
        self.assertNotIn('cancel-in-progress: true',workflow)
        tracker=read('market_ai_auto_tracker.py')
        self.assertIn('cancel-in-progress: false',tracker)
        self.assertIn('cancel-in-progress: true',tracker)  # explicitly rejected

    def test_stale_snapshot_collectors_remain_fail_closed(self):
        for name in ('.github/workflows/tcg-static-data-refresh.yml','.github/workflows/grading-company-watch.yml'):
            text=read(name)
            self.assertIn('cancel-in-progress: true',text)
            self.assertIn('git fetch origin main',text)
            self.assertIn('git rev-parse HEAD',text)
            self.assertIn('git rev-parse origin/main',text)
            self.assertIn('discard',text)


if __name__=='__main__':
    unittest.main()
''',encoding='utf-8')

# Dependency-closure regression from v257, now carried forward in v260.
Path('test_tablet_runtime_dependency_closure_v257.py').write_text(r'''#!/usr/bin/env python3
from __future__ import annotations
import ast
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

import tablet_runtime_manifest as manifest
import tcg_updater

ROOT=Path(__file__).resolve().parent

class _ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.sources=[]
    def handle_starttag(self,tag,attrs):
        if tag.lower()!='script': return
        src=dict(attrs).get('src')
        if src: self.sources.append(src)

def _normalize(value):
    text=str(value or '').strip()
    if not text or text.startswith(('http://','https://','//','data:','blob:','#')): return None
    text=text.split('?',1)[0].split('#',1)[0].strip()
    while text.startswith('./'): text=text[2:]
    return text.lstrip('/') or None

def _index_scripts():
    parser=_ScriptParser(); parser.feed((ROOT/'index.html').read_text(encoding='utf-8'))
    return {asset for raw in parser.sources if (asset:=_normalize(raw))}

def _sw_core():
    source=(ROOT/'sw.js').read_text(encoding='utf-8')
    match=re.search(r'const\s+CORE\s*=\s*\[(.*?)\]\s*;',source,re.S)
    if not match: raise AssertionError('service-worker CORE list missing')
    return {asset for raw in re.findall(r'[\'\"]([^\'\"]+)[\'\"]',match.group(1)) if (asset:=_normalize(raw))}

def _startup_local_imports():
    tree=ast.parse((ROOT/'tcg_updater.py').read_text(encoding='utf-8'),filename='tcg_updater.py')
    modules=set()
    for node in tree.body:
        if isinstance(node,ast.Import): modules.update(alias.name.split('.',1)[0] for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module and node.level==0: modules.add(node.module.split('.',1)[0])
    return {f'{module}.py' for module in modules if (ROOT/f'{module}.py').is_file()}

class TabletRuntimeDependencyClosureV257Tests(unittest.TestCase):
    def test_manifest_has_no_duplicates_and_audits_dependency_graph(self):
        self.assertEqual(len(manifest.ACTIVE_RUNTIME_FILES),len(set(manifest.ACTIVE_RUNTIME_FILES)))
        result=manifest.audit(ROOT,compile_python=False)
        self.assertEqual([],result.get('dependency_errors'),result)
        self.assertEqual([],result.get('duplicates'),result)
    def test_every_local_index_script_is_fail_closed_public_and_precached(self):
        scripts=_index_scripts(); self.assertTrue(scripts)
        self.assertTrue(scripts.issubset(set(manifest.ACTIVE_RUNTIME_FILES)),scripts-set(manifest.ACTIVE_RUNTIME_FILES))
        self.assertTrue(scripts.issubset(set(tcg_updater.PUBLIC_STATIC_FILES)),scripts-set(tcg_updater.PUBLIC_STATIC_FILES))
        core=_sw_core(); self.assertTrue(scripts.issubset(core),scripts-core)
    def test_service_worker_functional_assets_are_manifested_and_public(self):
        core=_sw_core(); functional={name for name in core if Path(name).suffix.lower() in {'.js','.css','.webmanifest','.svg'}}
        functional.update({'vision_calibration.json','grading_company_updates.json'}&core)
        self.assertTrue(functional.issubset(set(manifest.ACTIVE_RUNTIME_FILES)),functional-set(manifest.ACTIVE_RUNTIME_FILES))
        self.assertTrue(core.issubset(set(tcg_updater.PUBLIC_STATIC_FILES)),core-set(tcg_updater.PUBLIC_STATIC_FILES))
        self.assertEqual(set(),{name for name in core if not (ROOT/name).is_file()})
    def test_server_startup_local_imports_are_fail_closed(self):
        imports=_startup_local_imports(); self.assertIn('grading_accuracy_v99.py',imports); self.assertIn('server_security_guard.py',imports)
        self.assertTrue(imports.issubset(set(manifest.ACTIVE_RUNTIME_FILES)),imports-set(manifest.ACTIVE_RUNTIME_FILES))
    def test_grading_static_fallback_is_public_precached_and_fail_closed(self):
        name='grading_company_updates.json'; self.assertIn(name,tcg_updater.PUBLIC_STATIC_FILES); self.assertIn(name,_sw_core()); self.assertIn(name,manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn('/grading_company_updates.json?t=',(ROOT/'grading_costs_live.js').read_text(encoding='utf-8'))
    def test_service_worker_cache_generation_was_rotated(self):
        source=(ROOT/'sw.js').read_text(encoding='utf-8'); self.assertIn("const CACHE='tcg-v260-network-first-runtime';",source); self.assertNotIn('tcg-v205-network-first-runtime',source)

if __name__=='__main__': unittest.main()
''',encoding='utf-8')

# Run both regression files whenever Android updater surfaces change.
workflow=Path('.github/workflows/android-updater-guard.yml')
w=workflow.read_text(encoding='utf-8')
for marker in ('test_tablet_pause_recovery_v260.py','test_tablet_runtime_dependency_closure_v257.py'):
    if marker not in w:
        needle="      - 'test_tablet_runtime_qa_integration.py'\n"
        if w.count(needle)!=2:
            raise SystemExit('android updater guard path anchor drifted')
        w=w.replace(needle,needle+f"      - '{marker}'\n")
run_needle='''          python test_tablet_runtime_qa_integration.py\n'''
if w.count(run_needle)!=1:
    raise SystemExit('android updater guard run anchor drifted')
w=w.replace(run_needle,run_needle+'''          python -m unittest -v test_tablet_pause_recovery_v260.py\n          python -m unittest -v test_tablet_runtime_dependency_closure_v257.py\n''',1)
verify_needle="""          grep -Fq 'TCG_ANDROID_STARTUP.log' ANDROID_AUTO_START_INSTALL.sh\n"""
if w.count(verify_needle)!=1:
    raise SystemExit('android updater guard boot marker anchor drifted')
w=w.replace(verify_needle,verify_needle+"""          grep -Fq 'SUPERVISOR_LOCK_DIR' ANDROID_AUTO_START_INSTALL.sh\n          grep -Fq 'FAIL_THRESHOLD=3' ANDROID_AUTO_START_INSTALL.sh\n          grep -Fq 'CONFIRM_DELAY=5' ANDROID_AUTO_START_INSTALL.sh\n          grep -Fq 'termux-wake-lock' ANDROID_AUTO_START_INSTALL.sh\n""",1)
workflow.write_text(w,encoding='utf-8')

print('pause resilience v260 patch applied')
