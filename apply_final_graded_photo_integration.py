#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).resolve().parent/'graded_photo_multi_source.py'
s=p.read_text(encoding='utf-8')

s=s.replace('RUN_SOURCE_LIMIT=6\nRUN_WAIT_SECONDS=95', 'RUN_SOURCE_LIMIT=3\nRUN_WAIT_SECONDS=3600')

marker='def collect()->dict:\n'
helper='''def _adaptive_timeout_seconds(state:dict)->int:\n    a=state.get('adaptive_timeout') if isinstance(state.get('adaptive_timeout'),dict) else {}\n    runs=int(a.get('completed_runs',0) or 0)\n    recent=a.get('recent',[]) if isinstance(a.get('recent'),list) else []\n    recent=recent[-8:]\n    timeout_rate=(sum(1 for x in recent if isinstance(x,dict) and int(x.get('timed_out_sources',0) or 0)>0)/len(recent)) if recent else 0.0\n    elapsed=[float(x.get('elapsed_seconds',0) or 0) for x in recent if isinstance(x,dict) and float(x.get('elapsed_seconds',0) or 0)>0]\n    avg=(sum(elapsed)/len(elapsed)) if elapsed else 0.0\n    if runs < 3: base=3600\n    elif runs < 8: base=1800\n    elif runs < 15: base=900\n    elif runs < 30: base=300\n    else: base=120\n    if timeout_rate >= 0.50: base=max(base,3600)\n    elif timeout_rate >= 0.25: base=max(base,1800)\n    if avg>0: base=max(base,min(3600,int(avg*2.2+30)))\n    return max(120,min(3600,int(base)))\n\ndef _record_adaptive_timeout(state:dict,elapsed:float,timed_out:int,total_candidates:int,raw_results:int)->int:\n    a=state.setdefault('adaptive_timeout',{})\n    recent=a.setdefault('recent',[])\n    recent.append({'at':_now(),'elapsed_seconds':round(float(elapsed),1),'timed_out_sources':int(timed_out),'total_candidates':int(total_candidates),'raw_results':int(raw_results)})\n    a['recent']=recent[-12:]\n    a['completed_runs']=int(a.get('completed_runs',0) or 0)+1\n    a['last_elapsed_seconds']=round(float(elapsed),1)\n    a['last_timed_out_sources']=int(timed_out)\n    a['last_candidates']=int(total_candidates)\n    a['last_raw_results']=int(raw_results)\n    return _adaptive_timeout_seconds(state)\n\n'''
if '_adaptive_timeout_seconds' not in s:
    s=s.replace(marker,helper+marker,1)

old="def collect()->dict:\n registry=_registry();stats={};errors=[]"
new="def collect()->dict:\n run_started=time.monotonic()\n registry=_registry();stats={};errors=[]"
s=s.replace(old,new,1)

old="state=_load(LEARNING,{})\n first_full_collection=not bool(state.get('initial_collection_completed'))"
new="state=_load(LEARNING,{})\n adaptive_timeout_seconds=_adaptive_timeout_seconds(state)\n first_full_collection=not bool(state.get('initial_collection_completed'))"
s=s.replace(old,new,1)

s=s.replace("done,pending=concurrent.futures.wait(futs,timeout=RUN_WAIT_SECONDS)","done,pending=concurrent.futures.wait(futs,timeout=adaptive_timeout_seconds)")

summary_old="'image_results':sum(int(x.get('image_results',0)) for x in stats.values())}"
summary_new="'image_results':sum(int(x.get('image_results',0)) for x in stats.values()),'adaptive_timeout_seconds':adaptive_timeout_seconds,'elapsed_seconds':0.0,'next_timeout_seconds':adaptive_timeout_seconds}"
s=s.replace(summary_old,summary_new,1)

old="atomic_write_json(OUT,payload,suffix='.graded-photo.tmp')\n if first_full_collection:"
new="""elapsed_seconds=round(time.monotonic()-run_started,1)\n payload['summary']['elapsed_seconds']=elapsed_seconds\n timed_out=int(payload['summary'].get('timed_out_sources',0) or 0)\n learning_state=_load(LEARNING,{})\n next_timeout=_record_adaptive_timeout(learning_state,elapsed_seconds,timed_out,len(rows),int(payload['summary'].get('raw_results',0) or 0))\n payload['summary']['next_timeout_seconds']=next_timeout\n learning_state['last_adaptive_timeout_seconds']=adaptive_timeout_seconds\n learning_state['next_adaptive_timeout_seconds']=next_timeout\n atomic_write_json(LEARNING,learning_state,suffix='.graded-photo-adaptive.tmp')\n atomic_write_json(OUT,payload,suffix='.graded-photo.tmp')\n if first_full_collection:"""
s=s.replace(old,new,1)

# Preserve adaptive learning when first-full completion is written.
old="done_state['source_cursor']=0\n  atomic_write_json(LEARNING,done_state,suffix='.graded-photo-first-complete.tmp')"
new="done_state['source_cursor']=0\n  if isinstance(learning_state.get('adaptive_timeout'),dict): done_state['adaptive_timeout']=learning_state['adaptive_timeout']\n  done_state['last_adaptive_timeout_seconds']=learning_state.get('last_adaptive_timeout_seconds',adaptive_timeout_seconds)\n  done_state['next_adaptive_timeout_seconds']=learning_state.get('next_adaptive_timeout_seconds',next_timeout)\n  atomic_write_json(LEARNING,done_state,suffix='.graded-photo-first-complete.tmp')"
s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
print('final graded photo integration applied')
