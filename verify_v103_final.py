#!/usr/bin/env python3
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
checks=[]
def run(name,cmd,timeout):
    try:
        p=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
        detail=(p.stdout+p.stderr)[-5000:]
        checks.append({'name':name,'ok':p.returncode==0,'detail':detail})
        return p.returncode==0
    except subprocess.TimeoutExpired as e:
        checks.append({'name':name,'ok':False,'detail':f'TimeoutExpired: {e}'})
        return False
run('compileall',[sys.executable,'-m','compileall','-q','.'],60)
run('v103_market_source_tests',[sys.executable,'verify_v103_market_sources.py'],60)
run('market_crosscheck_self_test',[sys.executable,'market_public_crosscheck.py','self-test'],30)
run('v102_full_regression',[sys.executable,'verify_v102_final.py'],240)
report={
 'build':'TCG_Grader_v103_COLLECTORY_KREAM_CROSSCHECK_2026-08-28',
 'ok':all(x['ok'] for x in checks),
 'successful':sum(1 for x in checks if x['ok']),
 'failed':sum(1 for x in checks if not x['ok']),
 'checks':checks,
 'market_policy':{
   'sources':['Collectory','KREAM'],
   'public_html_only':True,
   'login_or_private_api_used':False,
   'match_priority':['card_number','product_code','card_name'],
   'primary_price_auto_overwrite':False,
   'rotating_targets_per_cycle':4,
   'default_source_timeout_seconds':12,
   'previous_observation_preserved_on_temporary_failure':True,
 }
}
(ROOT/'V103_FINAL_VERIFICATION_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'ok':report['ok'],'successful':report['successful'],'failed':report['failed']},ensure_ascii=False))
raise SystemExit(0 if report['ok'] else 1)
