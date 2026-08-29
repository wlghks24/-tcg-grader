#!/usr/bin/env python3
from pathlib import Path
p=Path(__file__).with_name('graded_photo_multi_source.py')
s=p.read_text(encoding='utf-8')

# Imports
if 'from detailed_collection_intelligence import' not in s:
 s=s.replace('from safe_runtime import atomic_write_json\n', 'from safe_runtime import atomic_write_json\nfrom detailed_collection_intelligence import build_queries, record_query_result, evidence_confidence, canonical_key, source_priority\n')
if 'import time' not in s.split('\n',25):
 s=s.replace('import json, os, re, urllib.parse, urllib.request\n', 'import json, os, re, urllib.parse, urllib.request, time\n')

# Add social/community public sources if absent.
needle=" {'id':'yahoo_jp','name':'Yahoo! Auctions JP','domain':'auctions.yahoo.co.jp','weight':0.70},\n)"
replacement=" {'id':'yahoo_jp','name':'Yahoo! Auctions JP','domain':'auctions.yahoo.co.jp','weight':0.70},\n {'id':'x','name':'X 공개게시물','domain':'x.com','weight':0.48},\n {'id':'instagram','name':'Instagram 공개게시물','domain':'instagram.com','weight':0.48},\n {'id':'naver','name':'Naver 공개블로그/카페','domain':'blog.naver.com','weight':0.52},\n)"
if needle in s and "'id':'x'" not in s:
 s=s.replace(needle,replacement)

# Replace query planner with adaptive detailed multilingual planner.
start=s.find('def _queries(src:dict,game:str)')
end=s.find('\ndef _discover_source_game', start)
if start!=-1 and end!=-1:
 block='''def _queries(src:dict,game:str)->tuple[tuple[str,str],...]:\n    sid=str(src.get('id') or '')\n    planned=[]\n    # Detailed multilingual source-specific planner. Keep the run bounded by\n    # prioritising productive sources/queries while still exploring all graders.\n    for company in COMPANIES:\n        for qsid,q in build_queries(game,'graded_photo',company):\n            if qsid==sid:\n                planned.append((company,q))\n                break\n    # Social/community sources get two contextual discovery queries in addition\n    # to grader names, because public posts often omit the word "graded".\n    if sid in {'x','instagram','naver'}:\n        g={'pokemon':'Pokemon 포켓몬','onepiece':'One Piece 원피스','naruto':'Naruto 나루토'}[game]\n        planned.extend([('PSA',f'site:{src["domain"]} {g} PSA 10'),('BGS',f'site:{src["domain"]} {g} slab card')])\n    return tuple(planned[:7])\n'''
 s=s[:start]+block+s[end:]

# Add timing + detailed learning to source-game discovery.
needle='def _discover_source_game(src:dict,game:str)->tuple[list[dict],list[str],int,dict]:\n raw=[];errors=[];queries=0\n'
if needle in s and 'detailed_started=time.monotonic()' not in s:
 s=s.replace(needle, needle+' detailed_started=time.monotonic()\n')

ret=' return out,errors,queries,diag\n\ndef _collect_public_source'
if ret in s and 'record_query_result(src[' not in s:
 repl=''' try:\n  record_query_result(str(src.get('id') or 'unknown'), f'{game}:graded_photo', raw=diag.get('raw_results',0), accepted=len(out), images=sum(bool(x.get('image_url')) for x in out), errors=len(errors), elapsed=time.monotonic()-detailed_started)\n except Exception:\n  pass\n return out,errors,queries,diag\n\ndef _collect_public_source'''
 s=s.replace(ret,repl)

# Add learned source priority to source ordering while retaining rotation/exploration.
old=" active=[SOURCES[(cursor+i)%len(SOURCES)] for i in range(min(RUN_SOURCE_LIMIT,len(SOURCES)))]\n"
if old in s and 'source_priority' in s:
 new=" rotated=[SOURCES[(cursor+i)%len(SOURCES)] for i in range(len(SOURCES))]\n  active=sorted(rotated[:max(RUN_SOURCE_LIMIT*2,RUN_SOURCE_LIMIT)], key=lambda x:source_priority(x['id']), reverse=True)[:min(RUN_SOURCE_LIMIT,len(SOURCES))]\n"
 s=s.replace(old,new)

# Add cross-source corroboration/confidence after dedupe rows list exists.
needle=' rows=list(dedup.values())[:MAX_ROWS];verified=0\n'
if needle in s and "cross_source_count" not in s:
 extra=''' rows=list(dedup.values())[:MAX_ROWS]\n # Cross-source corroboration: group similar titles across independent sources.\n groups={}\n for x in rows:\n  key=canonical_key(str(x.get('title') or ''),str(x.get('url') or ''))\n  groups.setdefault(key,set()).add(str(x.get('source_id') or ''))\n for x in rows:\n  key=canonical_key(str(x.get('title') or ''),str(x.get('url') or ''))\n  ids=sorted(y for y in groups.get(key,set()) if y)\n  x['cross_source_count']=len(ids);x['cross_sources']=ids[:12]\n  x['evidence_confidence']=evidence_confidence(ids,False)\n verified=0\n'''
 s=s.replace(needle,extra)

# If officially verified, recompute confidence at near-certain level.
needle="  x['official_result']=bool(ok);x['status']='verified_reference' if ok else 'quarantine_candidate'\n"
if needle in s and "evidence_confidence(x.get('cross_sources'" not in s:
 s=s.replace(needle, needle+"  x['evidence_confidence']=evidence_confidence(x.get('cross_sources') or [x.get('source_id')],bool(ok))\n")

p.write_text(s,encoding='utf-8')
print('detailed collection intelligence applied')
