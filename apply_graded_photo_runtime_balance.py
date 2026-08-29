#!/usr/bin/env python3
from pathlib import Path

p=Path('graded_photo_multi_source.py')
s=p.read_text(encoding='utf-8')
s=s.replace('RUN_SOURCE_LIMIT=6\nRUN_WAIT_SECONDS=95','RUN_SOURCE_LIMIT=3\nRUN_WAIT_SECONDS=120')
old='''def _collect_public_source(src:dict):
 found=[];errors=[];queries=0;diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0,'image_results':0}
 for game in GAMES:
  rows,err,q,d=_discover_source_game(src,game);found.extend(rows);errors.extend(err);queries+=q
  for k in diag: diag[k]+=int(d.get(k,0))
 seen={}
 for x in found:
  if x.get('url') and x['url'] not in seen:seen[x['url']]=x
 return src['id'],list(seen.values())[:MAX_PER_SOURCE],errors,queries,diag
'''
new='''def _collect_public_source(src:dict):
 # Run the three games in parallel. Previously they were sequential, so one source
 # often exceeded the whole-run timeout before returning any result at all.
 found=[];errors=[];queries=0;diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0,'image_results':0}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3,thread_name_prefix='graded-game') as gp:
  futs={gp.submit(_discover_source_game,src,game):game for game in GAMES}
  for fut in concurrent.futures.as_completed(futs):
   game=futs[fut]
   try:
    rows,err,q,d=fut.result();found.extend(rows);errors.extend(err);queries+=q
    for k in diag:diag[k]+=int(d.get(k,0))
   except Exception as exc:
    errors.append(game+':'+type(exc).__name__)
 seen={}
 for x in found:
  if x.get('url') and x['url'] not in seen:seen[x['url']]=x
 return src['id'],list(seen.values())[:MAX_PER_SOURCE],errors,queries,diag
'''
if old not in s:
 raise SystemExit('collector block not found')
s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
print('graded photo runtime balance applied')
