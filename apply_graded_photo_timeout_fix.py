from pathlib import Path

ROOT = Path(__file__).resolve().parent
P = ROOT / 'graded_photo_multi_source.py'
s = P.read_text(encoding='utf-8')

# 1) Keep Android network waits short and bound per-run workload.
s = s.replace("MAX_PER_SOURCE=18\nMAX_IMAGE_PROBES_PER_SOURCE=8\nMAX_PAGE_BYTES=1_000_000\n",
              "MAX_PER_SOURCE=12\nMAX_IMAGE_PROBES_PER_SOURCE=2\nMAX_PAGE_BYTES=1_000_000\nRUN_SOURCE_LIMIT=6\nRUN_WAIT_SECONDS=95\nos.environ.setdefault('TCG_HTTP_TIMEOUT','5')\n")

# 2) One compact grader query per game/source. The old three queries multiplied timeout cost.
old_queries = '''def _queries(src:dict,game:str)->tuple[str,...]:
 g={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]
 return (
  f'site:{src["domain"]} {g} "PSA 10" graded card',
  f'site:{src["domain"]} {g} (BGS OR CGC) (10 OR 9.5) card',
  f'site:{src["domain"]} {g} (TAG OR BRG) graded card',
 )
'''
new_queries = '''def _queries(src:dict,game:str)->tuple[str,...]:
 g={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]
 return (f'site:{src["domain"]} {g} (PSA OR BGS OR CGC OR TAG OR BRG) (10 OR 9.5 OR graded OR slab)',)
'''
if old_queries not in s:
    raise SystemExit('queries anchor missing')
s = s.replace(old_queries, new_queries, 1)

# 3) Prefer fast Bing RSS first; use DDG only as fallback.
old_rows = '''def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:
 rows=_google_cse(query,limit)
 if rows:return rows,[]
 errors=[]
 try:
  s=_searcher();rows,err,_,ok=s._search_ddg(query,limit)
  if err:errors.append('duckduckgo:'+err[:160])
  if rows:return rows,errors
 except Exception as exc:errors.append('duckduckgo:'+type(exc).__name__)
 try:
  s=_searcher();rows,err,_,ok=s._search_bing_rss(query,limit)
  if err:errors.append('bing_rss:'+err[:160])
  if rows:return rows,errors
 except Exception as exc:errors.append('bing_rss:'+type(exc).__name__)
 return [],errors
'''
new_rows = '''def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:
 rows=_google_cse(query,limit)
 if rows:return rows,[]
 errors=[]
 try:
  s=_searcher();rows,err,_,ok=s._search_bing_rss(query,limit)
  if err:errors.append('bing_rss:'+err[:160])
  if rows:return rows,errors
 except Exception as exc:errors.append('bing_rss:'+type(exc).__name__)
 try:
  s=_searcher();rows,err,_,ok=s._search_ddg(query,limit)
  if err:errors.append('duckduckgo:'+err[:160])
  if rows:return rows,errors
 except Exception as exc:errors.append('duckduckgo:'+type(exc).__name__)
 return [],errors
'''
if old_rows not in s:
    raise SystemExit('query rows anchor missing')
s = s.replace(old_rows, new_rows, 1)

# 4) Rotate 6 markets per run and never use ThreadPoolExecutor context-manager wait=True.
old_collect = ''' e=_ebay_candidates();rows.extend(e);stats['ebay']={'candidates':len(e),'image_hits':sum(bool(x.get('image_url')) for x in e),'verified_hits':0,'errors':0,'queries':0}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3,thread_name_prefix='graded-photo') as pool:
  futs={pool.submit(_collect_public_source,src):src for src in SOURCES}
  for fut in concurrent.futures.as_completed(futs):
   src=futs[fut]
   try:
    sid,found,errs,queries=fut.result();rows.extend(found)
    stats[sid]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),'verified_hits':0,'errors':len(errs),'queries':queries}
    errors.extend(f'{sid}:{x}' for x in errs[:3])
   except Exception as exc:
    sid=src['id'];stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0};errors.append(sid+':'+type(exc).__name__)
'''
new_collect = ''' e=_ebay_candidates();rows.extend(e);stats['ebay']={'candidates':len(e),'image_hits':sum(bool(x.get('image_url')) for x in e),'verified_hits':0,'errors':0,'queries':0}
 state=_load(LEARNING,{})
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
'''
if old_collect not in s:
    raise SystemExit('collect executor anchor missing')
s = s.replace(old_collect, new_collect, 1)

# 5) Expose bounded-run diagnostics.
s = s.replace("'status':'ok' if rows else 'no_candidates','queries_attempted':sum(int(x.get('queries',0)) for x in stats.values())},",
              "'status':'ok' if rows else 'no_candidates','queries_attempted':sum(int(x.get('queries',0)) for x in stats.values()),'markets_this_run':[x['id'] for x in active],'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values())},",1)

P.write_text(s,encoding='utf-8')
print('graded photo timeout/hang patch applied')
