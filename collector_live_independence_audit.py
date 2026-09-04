#!/usr/bin/env python3
"""Live collector independence audit.

Runs collector entrypoints separately, never merges their execution/error domains,
and writes a bounded JSON report. Network access is optional: inaccessible providers
are reported as inaccessible, never as success.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parent
KST=timezone(timedelta(hours=9))
REPORT=ROOT/'COLLECTOR_LIVE_INDEPENDENCE_REPORT.json'
MAX_SECONDS=90

# Explicit entrypoints only. Add collectors here after confirming their CLI is safe/no-write.
CANDIDATES=[
 ('tcgdex','tcgdex_collector.py'),('justtcg','justtcg_collector.py'),
 ('snkrdunk','snkrdunk_collector.py'),('pavilion','pavilion_collector.py'),
 ('pricecharting','pricecharting_collector.py'),('ebay','ebay_collector.py'),
 ('kream','kream_collector.py'),('collectory','collectory_collector.py'),
]

def stamp(): return datetime.now(KST).isoformat(timespec='seconds')
def sig(cid,stage,evidence):
 raw=f'{cid}|{stage}|{evidence[:160]}'; return hashlib.sha256(raw.encode()).hexdigest()[:20]

def classify(text, rc):
 t=text.lower()
 if '429' in t or 'too many requests' in t: return 'rate_limited'
 if '403' in t or 'forbidden' in t: return 'blocked'
 if 'timeout' in t or 'timed out' in t: return 'timeout'
 if rc==0: return 'success'
 return 'failed'

def run_one(cid, rel, execute):
 p=ROOT/rel; base={'collector_id':cid,'entrypoint':rel,'started_at_kst':stamp()}
 if not p.is_file(): return {**base,'status':'not_present','records':None}
 if not execute: return {**base,'status':'present_not_executed','records':None}
 started=time.monotonic()
 env=dict(os.environ); env['TCG_LIVE_AUDIT']='1'; env['PYTHONDONTWRITEBYTECODE']='1'
 try:
  cp=subprocess.run([sys.executable,str(p),'--audit'],cwd=ROOT,env=env,capture_output=True,text=True,timeout=MAX_SECONDS)
  evidence=' '.join(((cp.stdout or '')+' '+(cp.stderr or '')).split())[:800]
  status=classify(evidence,cp.returncode)
  return {**base,'status':status,'returncode':cp.returncode,'elapsed_ms':int((time.monotonic()-started)*1000),'records':None,'error_signature':None if status=='success' else sig(cid,status,evidence),'evidence':evidence}
 except subprocess.TimeoutExpired:
  return {**base,'status':'timeout','records':None,'error_signature':sig(cid,'timeout',rel),'elapsed_ms':MAX_SECONDS*1000}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--execute',action='store_true'); args=ap.parse_args()
 rows=[run_one(*x,args.execute) for x in CANDIDATES]
 ids=[r['collector_id'] for r in rows]; signatures=[r.get('error_signature') for r in rows if r.get('error_signature')]
 payload={'version':1,'checked_at_kst':stamp(),'execution_requested':args.execute,'collectors':rows,'summary':{'declared':len(rows),'present':sum(r['status']!='not_present' for r in rows),'success':sum(r['status']=='success' for r in rows),'inaccessible_or_failed':sum(r['status'] in {'blocked','rate_limited','timeout','failed'} for r in rows),'unique_collector_ids':len(ids)==len(set(ids)),'unique_error_domains':len(signatures)==len(set(signatures))}}
 REPORT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(payload['summary'],ensure_ascii=False)); return 0 if payload['summary']['unique_collector_ids'] and payload['summary']['unique_error_domains'] else 1
if __name__=='__main__': raise SystemExit(main())
