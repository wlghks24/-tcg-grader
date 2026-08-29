from pathlib import Path

ROOT=Path(__file__).resolve().parent
P=ROOT/'graded_photo_multi_source.py'
s=P.read_text(encoding='utf-8')
old="""def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:
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
"""
new="""def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:
 # Merge all available providers instead of returning the first non-empty one.
 # Bing RSS often yields tracking/intermediate URLs, while DuckDuckGo is more
 # likely to expose the actual marketplace URL. Keeping both makes the market
 # domain filter resilient without weakening it.
 errors=[];merged=[]
 try:
  merged.extend(_google_cse(query,limit))
 except Exception as exc:
  errors.append('google_cse:'+type(exc).__name__)
 try:
  srch=_searcher();rows,err,_,ok=srch._search_ddg(query,limit)
  if err:errors.append('duckduckgo:'+err[:160])
  merged.extend(rows)
 except Exception as exc:
  errors.append('duckduckgo:'+type(exc).__name__)
 try:
  srch=_searcher();rows,err,_,ok=srch._search_bing_rss(query,limit)
  if err:errors.append('bing_rss:'+err[:160])
  merged.extend(rows)
 except Exception as exc:
  errors.append('bing_rss:'+type(exc).__name__)
 out=[];seen=set()
 for r in merged:
  if not isinstance(r,dict):continue
  u=str(r.get('url') or '').strip()
  key=(u,str(r.get('title') or '').strip())
  if not u or key in seen:continue
  seen.add(key);out.append(r)
  if len(out)>=max(limit*3,limit):break
 return out,errors
"""
if old not in s:
    raise SystemExit('provider merge block not found')
s=s.replace(old,new,1)
P.write_text(s,encoding='utf-8')
print('graded photo provider merge applied')
