#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).resolve().parent/'graded_photo_multi_source.py'
s=p.read_text(encoding='utf-8')
old='''def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:\n rows=_google_cse(query,limit)\n if rows:return rows,[]\n errors=[]\n try:\n  s=_searcher();rows,err,_,ok=s._search_bing_rss(query,limit)\n  if err:errors.append('bing_rss:'+err[:160])\n  if rows:return rows,errors\n except Exception as exc:errors.append('bing_rss:'+type(exc).__name__)\n try:\n  s=_searcher();rows,err,_,ok=s._search_ddg(query,limit)\n  if err:errors.append('duckduckgo:'+err[:160])\n  if rows:return rows,errors\n except Exception as exc:errors.append('duckduckgo:'+type(exc).__name__)\n return [],errors\n'''
new='''def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:\n errors=[];merged=[];seen=set()\n def add(rows):\n  for row in rows or []:\n   if not isinstance(row,dict):continue\n   url=str(row.get('url') or '').strip()\n   key=url or (str(row.get('title') or ''),str(row.get('search_provider') or ''))\n   if not key or key in seen:continue\n   seen.add(key);merged.append(row)\n # Never let one provider suppress the others. Direct marketplace URLs from DDG\n # are especially useful when Bing RSS returns tracking/search URLs.\n try:add(_google_cse(query,limit))\n except Exception as exc:errors.append('google_cse:'+type(exc).__name__)\n try:\n  s=_searcher();rows,err,_,ok=s._search_bing_rss(query,limit)\n  if err:errors.append('bing_rss:'+err[:160])\n  add(rows)\n except Exception as exc:errors.append('bing_rss:'+type(exc).__name__)\n try:\n  s=_searcher();rows,err,_,ok=s._search_ddg(query,limit)\n  if err:errors.append('duckduckgo:'+err[:160])\n  add(rows)\n except Exception as exc:errors.append('duckduckgo:'+type(exc).__name__)\n return merged[:max(limit*3,limit)],errors\n'''
if old not in s:
 print('provider merge block already changed or not found')
else:
 s=s.replace(old,new,1)
 p.write_text(s,encoding='utf-8')
 print('graded photo provider merge v2 applied')
