#!/usr/bin/env python3
from __future__ import annotations
import compileall, json, subprocess, sys, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
checks=[]
def add(name,ok,detail=''):
    checks.append({'name':name,'ok':bool(ok),'detail':detail})

def run(name,args,timeout=120):
    try:
        p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=timeout)
        add(name,p.returncode==0,(p.stdout+p.stderr)[-2500:])
    except Exception as e:
        add(name,False,f'{type(e).__name__}: {e}')

add('compileall',compileall.compile_dir(str(ROOT),quiet=1))
run('v101_vision_self_learning',[sys.executable,'-B','vision_self_learning.py'],180)
for f in ['verify_v99_accuracy.py','verify_v99_cross_runtime.py','verify_v99_learning_pipeline.py','verify_vision_calibration.py','verify_ai_code_improver.py','verify_fault_injection_healing.py']:
    if (ROOT/f).exists(): run(f,[sys.executable,'-B',f],180)
# Server read-only endpoint smoke test on an isolated process.
proc=None
try:
    proc=subprocess.Popen([sys.executable,'-B','tcg_updater.py'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    ok=False; body=''
    for _ in range(40):
        time.sleep(.25)
        try:
            with urllib.request.urlopen('http://127.0.0.1:8765/api/vision-self-learning',timeout=2) as r:
                body=r.read().decode('utf-8'); ok=(r.status==200 and 'v101-isolated-self-learning-calibration' in body); break
        except Exception: pass
    add('vision_self_learning_status_api',ok,body[:1000])
except Exception as e:
    add('vision_self_learning_status_api',False,f'{type(e).__name__}: {e}')
finally:
    if proc is not None:
        proc.terminate()
        try: proc.wait(timeout=5)
        except Exception: proc.kill()
report={'build':'TCG_Grader_v101_FINAL_COMBINED_2026-08-28','ok':all(x['ok'] for x in checks),'checks':checks,'successful':sum(x['ok'] for x in checks),'failed':sum(not x['ok'] for x in checks)}
(ROOT/'V101_FINAL_VERIFICATION_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if report['ok'] else 1)
