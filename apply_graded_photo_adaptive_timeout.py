#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).resolve().parent/'graded_photo_multi_source.py'
s=p.read_text(encoding='utf-8')

s=s.replace('import json, os, re, urllib.parse, urllib.request', 'import json, os, re, time, urllib.parse, urllib.request')
s=s.replace("RUN_SOURCE_LIMIT=6\nRUN_WAIT_SECONDS=95", "RUN_SOURCE_LIMIT=6\nRUN_WAIT_SECONDS=3600\nADAPTIVE_TIMEOUT_LEVELS=(3600,1800,900,300,120)")

anchor="def _now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')\n"
helper=r'''def _adaptive_timeout(state:dict)->int:
 prof=state.get('adaptive_timeout') if isinstance(state.get('adaptive_timeout'),dict) else {}
 runs=int(prof.get('runs',0) or 0)
 stable=int(prof.get('stable_runs',0) or 0)
 recent=list(prof.get('recent',[]))[-10:]
 # Start generously. Reduce only after repeated successful collections.
 if stable>=30: target=120
 elif stable>=15: target=300
 elif stable>=8: target=900
 elif stable>=3: target=1800
 else: target=3600
 # Recent timeout pressure automatically increases the budget again.
 if recent:
  timeout_rate=sum(1 for x in recent if isinstance(x,dict) and x.get('timed_out'))/len(recent)
  if timeout_rate>=0.50: target=max(target,3600)
  elif timeout_rate>=0.25: target=max(target,1800)
 # Never go below twice the learned average successful runtime (+30s margin).
 avg=float(prof.get('avg_success_seconds',0) or 0)
 if avg>0: target=max(target,min(3600,int(avg*2+30)))
 return max(120,min(3600,int(target)))

def _update_adaptive_timeout(state:dict,elapsed:float,timed_out:int,new_candidates:int)->dict:
 prof=state.get('adaptive_timeout') if isinstance(state.get('adaptive_timeout'),dict) else {}
 runs=int(prof.get('runs',0) or 0)+1
 stable=int(prof.get('stable_runs',0) or 0)
 success=(timed_out==0)
 if success: stable+=1
 else: stable=max(0,stable-2)
 avg=float(prof.get('avg_success_seconds',0) or 0)
 if success:
  avg=elapsed if avg<=0 else (avg*0.8+elapsed*0.2)
 recent=list(prof.get('recent',[]))[-9:]
 recent.append({'at':_now(),'seconds':round(elapsed,2),'timed_out':int(timed_out),'new_candidates':int(new_candidates),'success':success})
 prof.update({'runs':runs,'stable_runs':stable,'avg_success_seconds':round(avg,2),'recent':recent,'last_elapsed_seconds':round(elapsed,2)})
 state['adaptive_timeout']=prof
 return state

'''
if '_adaptive_timeout(' not in s:
    s=s.replace(anchor, anchor+'\n'+helper)

old=""" state=_load(LEARNING,{})\n first_full_collection=not bool(state.get('initial_collection_completed'))"""
new=""" state=_load(LEARNING,{})\n run_started=time.monotonic()\n adaptive_wait=_adaptive_timeout(state)\n first_full_collection=not bool(state.get('initial_collection_completed'))"""
s=s.replace(old,new)

s=s.replace("done,pending=concurrent.futures.wait(futs,timeout=RUN_WAIT_SECONDS)", "done,pending=concurrent.futures.wait(futs,timeout=adaptive_wait)")

old_payload="""'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values()),'initial_full_collection':first_full_collection,'previous_candidates':previous_count"""
new_payload="""'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values()),'adaptive_timeout_seconds':adaptive_wait,'initial_full_collection':first_full_collection,'previous_candidates':previous_count"""
s=s.replace(old_payload,new_payload)

old_tail=""" _save_learning(stats);return payload\n"""
new_tail=""" elapsed=time.monotonic()-run_started\n learned=_load(LEARNING,{})\n timed_out=sum(bool(x.get('timed_out')) for x in stats.values())\n new_candidates=max(0,len(rows)-previous_count)\n learned=_update_adaptive_timeout(learned,elapsed,timed_out,new_candidates)\n learned['adaptive_timeout']['next_timeout_seconds']=_adaptive_timeout(learned)\n atomic_write_json(LEARNING,learned,suffix='.graded-photo-adaptive-timeout.tmp')\n payload['summary']['elapsed_seconds']=round(elapsed,2)\n payload['summary']['next_timeout_seconds']=learned['adaptive_timeout']['next_timeout_seconds']\n atomic_write_json(OUT,payload,suffix='.graded-photo-summary-timeout.tmp')\n _save_learning(stats);return payload\n"""
s=s.replace(old_tail,new_tail)

p.write_text(s,encoding='utf-8')
print('graded photo adaptive timeout applied')
