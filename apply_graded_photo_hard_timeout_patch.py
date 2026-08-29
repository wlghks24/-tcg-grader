from pathlib import Path

ROOT=Path(__file__).resolve().parent
P=ROOT/'graded_photo_multi_source.py'
s=P.read_text(encoding='utf-8')

# imports
s=s.replace('import json, os, re, urllib.parse, urllib.request\n', 'import json, os, re, sys, subprocess, urllib.parse, urllib.request\n', 1)

# hard per-source timeout constants
anchor="MAX_PAGE_BYTES=1_000_000\n"
if 'SOURCE_PROCESS_TIMEOUT' not in s:
    s=s.replace(anchor, anchor+"SOURCE_PROCESS_TIMEOUT=18\n", 1)

old=""" pool=concurrent.futures.ThreadPoolExecutor(max_workers=3,thread_name_prefix='graded-photo')
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
new=""" # Hard process isolation: a blocked DNS/HTTP/search worker can never hold the parent alive.
 for src in active:
  sid=src['id']
  try:
   cp=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--worker-source',sid],capture_output=True,text=True,timeout=SOURCE_PROCESS_TIMEOUT)
   if cp.returncode!=0:
    raise RuntimeError(('worker_exit_'+str(cp.returncode))+(':'+cp.stderr[-180:] if cp.stderr else ''))
   line=(cp.stdout or '').strip().splitlines()[-1]
   obj=json.loads(line)
   found=obj.get('rows',[]) if isinstance(obj,dict) else []
   errs=obj.get('errors',[]) if isinstance(obj,dict) else []
   queries=int(obj.get('queries',0)) if isinstance(obj,dict) else 0
   rows.extend(found)
   stats[sid]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),'verified_hits':0,'errors':len(errs),'queries':queries}
   errors.extend(f'{sid}:{x}' for x in errs[:3])
  except subprocess.TimeoutExpired:
   stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0,'timed_out':True}
   errors.append(sid+':hard_timeout')
  except Exception as exc:
   stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0}
   errors.append(sid+':'+type(exc).__name__)
"""
if old not in s:
    raise SystemExit('thread-pool block anchor missing')
s=s.replace(old,new,1)

# worker mode before normal main entry
old_main="""if __name__=='__main__':main()
"""
new_main="""def _worker_source_main(sid:str):
 src=next((x for x in SOURCES if x['id']==sid),None)
 if not src:
  print(json.dumps({'rows':[],'errors':['unknown_source'],'queries':0},ensure_ascii=False));return 2
 try:
  _sid,found,errs,queries=_collect_public_source(src)
  print(json.dumps({'rows':found,'errors':errs,'queries':queries},ensure_ascii=False));return 0
 except Exception as exc:
  print(json.dumps({'rows':[],'errors':[type(exc).__name__],'queries':0},ensure_ascii=False));return 1

if __name__=='__main__':
 if len(sys.argv)>=3 and sys.argv[1]=='--worker-source':
  raise SystemExit(_worker_source_main(sys.argv[2]))
 main()
"""
if old_main not in s:
    raise SystemExit('main anchor missing')
s=s.replace(old_main,new_main,1)
P.write_text(s,encoding='utf-8')
print('graded photo hard-timeout patch applied')
