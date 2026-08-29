from pathlib import Path

ROOT=Path(__file__).resolve().parent
P=ROOT/'graded_photo_multi_source.py'
s=P.read_text(encoding='utf-8')

s=s.replace('import concurrent.futures\nimport json, os, re, urllib.parse, urllib.request', 'import concurrent.futures\nimport base64\nimport json, os, re, urllib.parse, urllib.request', 1)

anchor="""def _allowed_host(host:str,domain:str)->bool:\n host=(host or '').lower().split(':')[0];domain=domain.lower()\n return host==domain or host.endswith('.'+domain)\n"""
insert=anchor+"""\ndef _unwrap_target_url(value:str,domain:str)->tuple[str,bool]:\n raw=str(value or '').strip()\n if not raw:return '',False\n current=raw\n changed=False\n for _ in range(4):\n  try:p=urllib.parse.urlsplit(current)\n  except ValueError:return '',changed\n  host=(p.hostname or '').lower()\n  if p.scheme=='https' and _allowed_host(host,domain):return current,changed\n  qs=urllib.parse.parse_qs(p.query)\n  target=''\n  for key in ('uddg','url','target','r','q'):\n   vals=qs.get(key)\n   if vals and str(vals[0]).startswith(('http://','https://')):\n    target=urllib.parse.unquote(str(vals[0]));break\n  if not target and qs.get('u'):\n   cand=str(qs['u'][0])\n   try:\n    decoded=urllib.parse.unquote(cand)\n    if decoded.startswith(('http://','https://')):target=decoded\n    elif decoded.startswith('a1'):\n     token=decoded[2:];token += '='*((4-len(token)%4)%4)\n     b=base64.urlsafe_b64decode(token.encode('ascii')).decode('utf-8','ignore')\n     if b.startswith(('http://','https://')):target=b\n   except Exception:pass\n  if not target:\n   # Last-resort extraction from an encoded tracking URL, still revalidated below.\n   decoded=urllib.parse.unquote(current)\n   m=re.search(r'https%?3A(?:%2F|/){2}[^&\\s]+',current,re.I)\n   if m:\n    try:target=urllib.parse.unquote(m.group(0))\n    except Exception:target=''\n   elif 'https://' in decoded and decoded!=current:\n    pos=decoded.find('https://');target=decoded[pos:]\n  if not target or target==current:break\n  current=target;changed=True\n try:p=urllib.parse.urlsplit(current)\n except ValueError:return '',changed\n if p.scheme=='https' and _allowed_host(p.hostname or '',domain):return current,changed\n return '',changed\n"""
if '_unwrap_target_url' not in s:
    if anchor not in s: raise SystemExit('allowed host anchor not found')
    s=s.replace(anchor,insert,1)

s=s.replace("diag={'raw_results':0,'domain_matches':0,'company_matches':0}", "diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0}")
s=s.replace("diag={'raw_results':0,'domain_matches':0,'company_matches':0}\n for game in GAMES:", "diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0}\n for game in GAMES:")

old=""" for r in raw:\n  url=str(r.get('url') or '')\n  try:p=urllib.parse.urlsplit(url)\n  except ValueError:continue\n  if p.scheme!='https' or not _allowed_host(p.hostname or '',src['domain']):continue\n  candidates.setdefault(url,r)\n"""
new=""" for r in raw:\n  raw_url=str(r.get('url') or '')\n  url,resolved=_unwrap_target_url(raw_url,src['domain'])\n  if not url:continue\n  if resolved:diag['resolved_redirects']+=1\n  item=dict(r);item['url']=url;item['_raw_url']=raw_url\n  candidates.setdefault(url,item)\n"""
if old not in s: raise SystemExit('candidate domain block not found')
s=s.replace(old,new,1)

oldsum="""'previous_candidates':previous_count,'raw_results':sum(int(x.get('raw_results',0)) for x in stats.values()),'domain_matches':sum(int(x.get('domain_matches',0)) for x in stats.values()),'company_matches':sum(int(x.get('company_matches',0)) for x in stats.values())},"""
newsum="""'previous_candidates':previous_count,'raw_results':sum(int(x.get('raw_results',0)) for x in stats.values()),'domain_matches':sum(int(x.get('domain_matches',0)) for x in stats.values()),'company_matches':sum(int(x.get('company_matches',0)) for x in stats.values()),'resolved_redirects':sum(int(x.get('resolved_redirects',0)) for x in stats.values())},"""
if oldsum in s:s=s.replace(oldsum,newsum,1)

P.write_text(s,encoding='utf-8')
print('graded photo redirect unwrap applied')
