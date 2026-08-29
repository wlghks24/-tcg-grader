from pathlib import Path

ROOT=Path(__file__).resolve().parent
P=ROOT/'graded_photo_multi_source.py'
s=P.read_text(encoding='utf-8')

s=s.replace('import concurrent.futures\nimport base64\nimport json, os, re, urllib.parse, urllib.request', 'import concurrent.futures\nimport base64\nimport html\nimport json, os, re, urllib.parse, urllib.request', 1)

anchor="""def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:\n rows=_google_cse(query,limit)\n if rows:return rows,[]\n errors=[]\n try:\n  s=_searcher();rows,err,_,ok=s._search_bing_rss(query,limit)\n  if err:errors.append('bing_rss:'+err[:160])\n  if rows:return rows,errors\n except Exception as exc:errors.append('bing_rss:'+type(exc).__name__)\n try:\n  s=_searcher();rows,err,_,ok=s._search_ddg(query,limit)\n  if err:errors.append('duckduckgo:'+err[:160])\n  if rows:return rows,errors\n except Exception as exc:errors.append('duckduckgo:'+type(exc).__name__)\n return [],errors\n"""
insert=anchor+"""\ndef _bing_image_rows(query:str,src:dict,limit:int=10)->list[dict]:\n try:\n  url='https://www.bing.com/images/search?'+urllib.parse.urlencode({'q':query,'form':'HDRSC3'})\n  req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.8,en;q=0.7'})\n  with urllib.request.urlopen(req,timeout=7) as r:\n   raw=r.read(1_500_000)\n  text=html.unescape(raw.decode('utf-8','ignore'))\n except Exception:\n  return []\n out=[]\n for m in re.finditer(r'\\\"murl\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',text,re.I):\n  start=max(0,m.start()-1400);end=min(len(text),m.end()+1400);chunk=text[start:end]\n  pm=re.search(r'\\\"purl\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',chunk,re.I)\n  if not pm: continue\n  img=bytes(m.group(1),'utf-8').decode('unicode_escape')\n  page=bytes(pm.group(1),'utf-8').decode('unicode_escape')\n  try:\n   pu=urllib.parse.urlsplit(page)\n  except ValueError:\n   continue\n  if pu.scheme!='https' or not _allowed_host(pu.hostname or '',src['domain']):\n   continue\n  tm=re.search(r'\\\"t\\\"\\s*:\\s*\\\"([^\\\"]+)\\\"',chunk,re.I)\n  title=bytes(tm.group(1),'utf-8').decode('unicode_escape') if tm else page\n  out.append({'title':title[:260],'url':page[:1200],'snippet':'','image_url':img[:1200] if img.startswith('https://') else '', 'search_provider':'bing_images'})\n  if len(out)>=limit: break\n return out\n"""
if '_bing_image_rows' not in s:
    if anchor not in s: raise SystemExit('query rows anchor not found')
    s=s.replace(anchor,insert,1)

old=""" diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0}\n for expected_company,q in _queries(src,game):\n  queries+=1\n  try:\n   qrows,err=_query_rows(q,10)\n   for rr in qrows:\n    if isinstance(rr,dict):\n     item=dict(rr);item['_expected_company']=expected_company;raw.append(item)\n   errors.extend(err);diag['raw_results']+=len(qrows)\n  except Exception as exc:errors.append(type(exc).__name__)\n candidates={}\n"""
new=""" diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0,'image_results':0}\n for expected_company,q in _queries(src,game):\n  queries+=1\n  try:\n   qrows,err=_query_rows(q,10)\n   for rr in qrows:\n    if isinstance(rr,dict):\n     item=dict(rr);item['_expected_company']=expected_company;raw.append(item)\n   errors.extend(err);diag['raw_results']+=len(qrows)\n  except Exception as exc:errors.append(type(exc).__name__)\n # One compact image-search per game/source. Bing image rows expose the actual\n # marketplace page (purl) and source image (murl), which avoids search redirect loss.\n try:\n  gname={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]\n  iq=f'site:{src[\"domain\"]} {gname} PSA BGS CGC TAG BRG graded card slab'\n  irows=_bing_image_rows(iq,src,12)\n  for rr in irows:\n   if isinstance(rr,dict): raw.append(dict(rr))\n  diag['image_results']+=len(irows);diag['raw_results']+=len(irows)\n except Exception as exc: errors.append('bing_images:'+type(exc).__name__)\n candidates={}\n"""
if old not in s: raise SystemExit('discover block not found')
s=s.replace(old,new,1)

s=s.replace("diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0}\n for game in GAMES:", "diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0,'image_results':0}\n for game in GAMES:", 1)
oldsum="""'company_matches':sum(int(x.get('company_matches',0)) for x in stats.values()),'resolved_redirects':sum(int(x.get('resolved_redirects',0)) for x in stats.values())},"""
newsum="""'company_matches':sum(int(x.get('company_matches',0)) for x in stats.values()),'resolved_redirects':sum(int(x.get('resolved_redirects',0)) for x in stats.values()),'image_results':sum(int(x.get('image_results',0)) for x in stats.values())},"""
if oldsum in s:s=s.replace(oldsum,newsum,1)

P.write_text(s,encoding='utf-8')
print('graded photo Bing image fallback applied')
