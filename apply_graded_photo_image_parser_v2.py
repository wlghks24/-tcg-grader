from pathlib import Path

P=Path(__file__).resolve().parent/'graded_photo_multi_source.py'
s=P.read_text(encoding='utf-8')
start=s.index('def _bing_image_rows(')
end=s.index('\ndef _queries(', start)
new=r'''def _bing_image_rows(query:str,src:dict,limit:int=10)->list[dict]:
 try:
  url='https://www.bing.com/images/search?'+urllib.parse.urlencode({'q':query,'form':'HDRSC3'})
  req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.8,en;q=0.7'})
  with urllib.request.urlopen(req,timeout=8) as r: raw=r.read(1_800_000)
  text=raw.decode('utf-8','ignore')
 except Exception:return []
 out=[];seen=set()
 # Bing stores image metadata in an HTML attribute: m="{&quot;murl&quot;:...}".
 for am in re.finditer(r'\bm=["\']([^"\']{20,6000})["\']',text,re.I):
  try: meta=json.loads(html.unescape(am.group(1)))
  except Exception: continue
  if not isinstance(meta,dict):continue
  page=str(meta.get('purl') or meta.get('pUrl') or '')
  img=str(meta.get('murl') or meta.get('mUrl') or '')
  title=str(meta.get('t') or meta.get('title') or page)
  try:pu=urllib.parse.urlsplit(page)
  except ValueError:continue
  if pu.scheme!='https' or not _allowed_host(pu.hostname or '',src['domain']):continue
  if page in seen:continue
  seen.add(page)
  out.append({'title':title[:260],'url':page[:1200],'snippet':'','image_url':img[:1200] if img.startswith('https://') else '','search_provider':'bing_images_v2'})
  if len(out)>=limit:break
 # Fallback for alternate Bing markup where JSON is embedded directly.
 if not out:
  decoded=html.unescape(text)
  for m in re.finditer(r'"purl"\s*:\s*"([^"]+)"[^{}]{0,1200}"murl"\s*:\s*"([^"]+)"',decoded,re.I):
   page=m.group(1).replace('\\/','/');img=m.group(2).replace('\\/','/')
   try:pu=urllib.parse.urlsplit(page)
   except ValueError:continue
   if pu.scheme=='https' and _allowed_host(pu.hostname or '',src['domain']) and page not in seen:
    seen.add(page);out.append({'title':page[:260],'url':page[:1200],'snippet':'','image_url':img[:1200] if img.startswith('https://') else '','search_provider':'bing_images_v2'})
    if len(out)>=limit:break
 return out

def _ebay_public_rows(game:str,limit:int=12)->list[dict]:
 g={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]
 q=f'{g} PSA BGS CGC TAG BRG graded card slab'
 try:
  url='https://www.ebay.com/sch/i.html?'+urllib.parse.urlencode({'_nkw':q,'_sacat':'0'})
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept-Language':'en-US,en;q=0.8'})
  with urllib.request.urlopen(req,timeout=8) as r:text=r.read(1_800_000).decode('utf-8','ignore')
 except Exception:return []
 out=[];seen=set()
 for block in re.findall(r'<li[^>]+class="[^"]*s-item[^"]*"[^>]*>(.*?)</li>',text,re.I|re.S):
  hm=re.search(r'href="(https://www\.ebay\.com/itm/[^"?]+[^\"]*)"',block,re.I)
  if not hm:continue
  page=html.unescape(hm.group(1)).split('?')[0]
  if page in seen:continue
  title=''
  tm=re.search(r'<div[^>]+class="[^"]*s-item__title[^"]*"[^>]*>(.*?)</div>',block,re.I|re.S)
  if tm:title=re.sub(r'<[^>]+>',' ',html.unescape(tm.group(1))).strip()
  blob=title
  if not _company(blob):continue
  im=re.search(r'<img[^>]+(?:src|data-src)="(https://[^"]+)"',block,re.I)
  img=html.unescape(im.group(1)) if im else ''
  seen.add(page);out.append({'title':title[:260],'url':page[:1200],'snippet':'','image_url':img[:1200],'search_provider':'ebay_public_direct'})
  if len(out)>=limit:break
 return out
'''
s=s[:start]+new+s[end:]
old="""  irows=_bing_image_rows(iq,src,12)\n  for rr in irows:\n   if isinstance(rr,dict): raw.append(dict(rr))\n  diag['image_results']+=len(irows);diag['raw_results']+=len(irows)\n"""
new2="""  irows=_bing_image_rows(iq,src,12)\n  if src.get('id')=='ebay_public':\n   direct=_ebay_public_rows(game,12)\n   existing={str(x.get('url') or '') for x in irows}\n   irows.extend(x for x in direct if str(x.get('url') or '') not in existing)\n  for rr in irows:\n   if isinstance(rr,dict):\n    item=dict(rr)\n    item['_expected_company']=_company(str(item.get('title') or '')) or 'PSA'\n    raw.append(item)\n  diag['image_results']+=len(irows);diag['raw_results']+=len(irows)\n"""
if old not in s:raise SystemExit('image integration block not found')
s=s.replace(old,new2,1)
P.write_text(s,encoding='utf-8')
print('graded photo image parser v2 applied')
