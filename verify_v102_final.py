#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
checks=[]

def run(name,cmd,timeout):
    p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
    detail=(p.stdout+p.stderr)[-5000:]
    checks.append({'name':name,'ok':p.returncode==0,'detail':detail})
    return p.returncode==0

run('compileall',[sys.executable,'-m','compileall','-q','.'],60)
run('ebay_collector_self_test',[sys.executable,'ebay_grader_learning.py','self-test'],30)
run('provider_segment_self_test',[sys.executable,'provider_segment_learning.py'],30)
run('v102_provider_learning_tests',[sys.executable,'verify_v102_provider_learning.py'],60)
run('v101_regression_suite',[sys.executable,'verify_v101_final.py'],180)
run('browser_runtime',['node','verify_browser_runtime.js'],60)
run('vision_runtime',['node','verify_vision_runtime.js'],240)
run('camera_runtime',['node','verify_camera_runtime.js'],60)
run('service_worker_runtime',['node','verify_service_worker_runtime.js'],60)
run('v99_cross_runtime',[sys.executable,'verify_v99_cross_runtime.py'],90)

try:
    from feature_contract import audit_feature_contract
    r=audit_feature_contract(ROOT)
    checks.append({'name':'feature_contract','ok':bool(r.get('ok')),'detail':json.dumps({'implemented':r.get('implemented'),'total':r.get('total'),'missing':r.get('missing')},ensure_ascii=False)})
except Exception as e:
    checks.append({'name':'feature_contract','ok':False,'detail':f'{type(e).__name__}: {e}'})

report={
    'build':'TCG_Grader_v102_EBAY_PROVIDER_PHOTO_LEARNING_2026-08-28',
    'ok':all(x['ok'] for x in checks),
    'successful':sum(1 for x in checks if x['ok']),
    'failed':sum(1 for x in checks if not x['ok']),
    'checks':checks,
    'new_learning_policy':{
        'ebay_official_browse_api_only':True,
        'graded_condition_id':'2750',
        'seller_label_alone_never_official':True,
        'official_certification_verification_required':True,
        'company_game_mode_segmented':True,
        'raw_slab_isolated':True,
        'same_artwork_grouped_for_holdout':True,
        'upward_correction_allowed':False,
        'max_segment_downward_correction':-0.5,
    }
}
(ROOT/'V102_FINAL_VERIFICATION_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'ok':report['ok'],'successful':report['successful'],'failed':report['failed']},ensure_ascii=False))
raise SystemExit(0 if report['ok'] else 1)
