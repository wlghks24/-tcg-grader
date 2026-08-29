from pathlib import Path

ROOT=Path(__file__).resolve().parent
P=ROOT/'graded_photo_multi_source.py'
s=P.read_text(encoding='utf-8')

old=""" state=_load(LEARNING,{})
 try:cursor=int(state.get('source_cursor',0))%len(SOURCES)
 except Exception:cursor=0
 active=[SOURCES[(cursor+i)%len(SOURCES)] for i in range(min(RUN_SOURCE_LIMIT,len(SOURCES)))]
 state['source_cursor']=(cursor+len(active))%len(SOURCES);state['last_active_sources']=[x['id'] for x in active]
 atomic_write_json(LEARNING,state,suffix='.graded-photo-cursor.tmp')
 pool=concurrent.futures.ThreadPoolExecutor(max_workers=3,thread_name_prefix='graded-photo')
 futs={pool.submit(_collect_public_source,src):src for src in active}
 done,pending=concurrent.futures.wait(futs,timeout=RUN_WAIT_SECONDS)
 for fut in done:
  src=futs[fut]
  try:
   sid,found,errs,queries=fut.result();rows.extend(found)
   stats[sid]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),'verified_hits':0,'errors':len(errs),'queries':queries}
   errors.extend(f'{sid}:{x}' for x in errs[:3])
  except Exception as exc:
   sid=src['id'];stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0};errors.append(sid+':'+type(exc).__name__)
 for fut in pending:
  src=futs[fut];fut.cancel();sid=src['id']
  stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0,'timed_out':True}
  errors.append(sid+':run_timeout')
 pool.shutdown(wait=False,cancel_futures=True)
"""
new=""" state=_load(LEARNING,{})
 first_full_collection=not bool(state.get('initial_collection_completed'))
 try:cursor=int(state.get('source_cursor',0))%len(SOURCES)
 except Exception:cursor=0
 if first_full_collection:
  active=list(SOURCES)
  state['last_active_sources']=[x['id'] for x in active]
  state['initial_collection_started_at']=state.get('initial_collection_started_at') or _now()
 else:
  active=[SOURCES[(cursor+i)%len(SOURCES)] for i in range(min(RUN_SOURCE_LIMIT,len(SOURCES)))]
  state['source_cursor']=(cursor+len(active))%len(SOURCES);state['last_active_sources']=[x['id'] for x in active]
 atomic_write_json(LEARNING,state,suffix='.graded-photo-cursor.tmp')
 pool=concurrent.futures.ThreadPoolExecutor(max_workers=3,thread_name_prefix='graded-photo')
 futs={pool.submit(_collect_public_source,src):src for src in active}
 if first_full_collection:
  # Initial population run: no overall RUN_WAIT_SECONDS limit. Each HTTP request still
  # keeps its own network timeout so an unreachable host cannot block forever.
  done=set()
  for fut in concurrent.futures.as_completed(futs):
   done.add(fut)
  pending=set()
 else:
  done,pending=concurrent.futures.wait(futs,timeout=RUN_WAIT_SECONDS)
 for fut in done:
  src=futs[fut]
  try:
   sid,found,errs,queries=fut.result();rows.extend(found)
   stats[sid]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),'verified_hits':0,'errors':len(errs),'queries':queries}
   errors.extend(f'{sid}:{x}' for x in errs[:3])
  except Exception as exc:
   sid=src['id'];stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0};errors.append(sid+':'+type(exc).__name__)
 for fut in pending:
  src=futs[fut];fut.cancel();sid=src['id']
  stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0,'timed_out':True}
  errors.append(sid+':run_timeout')
 pool.shutdown(wait=first_full_collection,cancel_futures=not first_full_collection)
"""
if old not in s:
    raise SystemExit('collection timeout block not found')
s=s.replace(old,new,1)

old_summary="""'status':'ok' if rows else 'no_candidates','queries_attempted':sum(int(x.get('queries',0)) for x in stats.values()),'markets_this_run':[x['id'] for x in active],'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values())},"""
new_summary="""'status':'ok' if rows else 'no_candidates','queries_attempted':sum(int(x.get('queries',0)) for x in stats.values()),'markets_this_run':[x['id'] for x in active],'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values()),'initial_full_collection':first_full_collection},"""
if old_summary not in s:
    raise SystemExit('summary anchor not found')
s=s.replace(old_summary,new_summary,1)

old_tail=""" atomic_write_json(OUT,payload,suffix='.graded-photo.tmp');_save_learning(stats);return payload
"""
new_tail=""" atomic_write_json(OUT,payload,suffix='.graded-photo.tmp')
 if first_full_collection:
  done_state=_load(LEARNING,{})
  done_state['initial_collection_completed']=True
  done_state['initial_collection_completed_at']=_now()
  done_state['source_cursor']=0
  atomic_write_json(LEARNING,done_state,suffix='.graded-photo-first-complete.tmp')
 _save_learning(stats);return payload
"""
if old_tail not in s:
    raise SystemExit('completion anchor not found')
s=s.replace(old_tail,new_tail,1)

P.write_text(s,encoding='utf-8')
print('first full collection timeout exemption applied')
