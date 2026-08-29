#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quarantine-first graded-card photo discovery across public marketplaces.

v4 combines official APIs when configured, public search fallbacks, bounded image
validation/OCR and strict grading-company certification lookup.  One failed
provider cannot suppress the other providers, and every failure is visible in the
dashboard diagnostics.
Marketplace/search-visible rows are candidates only.  Nothing becomes calibration
truth unless the local verified-certification registry matches company+cert+grade.
"""
from __future__ import annotations

import concurrent.futures
import base64
import collections
import html
import json, math, os, re, urllib.parse, urllib.request, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, safe_read_text, safe_urlopen, safe_urlopen_no_redirect
from detailed_collection_intelligence import (
 build_queries, canonical_key, evidence_confidence, learning_snapshot,
 record_collection_cycle, record_official_feedback, route_run_count, source_priority,
)
from graded_photo_evidence import enrich_rows, normalize_cert
from grading_cert_verifier import lookup_url, verify_cert

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'graded_photo_candidates.json'
LEARNING=ROOT/'graded_photo_source_learning.json'
VERIFIED=ROOT/'verified_certifications.json'
OFFICIAL_CACHE=ROOT/'graded_photo_official_cache.json'
REFERENCE_LEARNING=ROOT/'graded_photo_reference_learning.json'
LIBRARY_OFFICIAL=ROOT/'library_official_cert_registry.json'
LIBRARY_CANDIDATES=ROOT/'library_slab_candidates.json'
LIBRARY_REFERENCES=ROOT/'library_verified_slab_references.json'
UA='Mozilla/5.0 TCG-Grader-GradedPhotoCollector/4.0'
COMPANIES=('PSA','BGS','CGC','TAG','BRG')
GAMES=('pokemon','onepiece','naruto')
GAME_DISPLAY_NAMES={'pokemon':'포켓몬','onepiece':'원피스','naruto':'나루토'}
MAX_ROWS=600
MAX_PER_SOURCE=24
MAX_IMAGE_PROBES_PER_SOURCE=3
MAX_PAGE_BYTES=1_000_000
RUN_SOURCE_LIMIT=6
RUN_WAIT_SECONDS=300
os.environ.setdefault('TCG_HTTP_TIMEOUT','5')

SOURCE_ID_ALIASES={'ebay_public':'ebay'}
BOOTSTRAP_SOURCE_IDS=('ebay_public','amazon_us','amazon_jp','kream','daangn','collectory')

SOURCES=(
 {'id':'ebay_public','name':'eBay 공개검색','domain':'ebay.com','weight':0.90},
 {'id':'amazon_us','name':'Amazon US','domain':'amazon.com','weight':0.65},
 {'id':'amazon_jp','name':'Amazon JP','domain':'amazon.co.jp','weight':0.68},
 {'id':'kream','name':'KREAM','domain':'kream.co.kr','weight':0.82},
 {'id':'daangn','name':'당근','domain':'daangn.com','weight':0.64},
 {'id':'bunjang','name':'번개장터','domain':'bunjang.co.kr','weight':0.68},
 {'id':'joongna','name':'중고나라','domain':'joongna.com','weight':0.66},
 {'id':'collectory','name':'Collectory','domain':'collectory.cc','weight':0.78},
 {'id':'tcgplayer','name':'TCGplayer','domain':'tcgplayer.com','weight':0.74},
 {'id':'cardmarket','name':'Cardmarket','domain':'cardmarket.com','weight':0.72},
 {'id':'mercari_jp','name':'Mercari JP','domain':'jp.mercari.com','weight':0.72},
 {'id':'yahoo_jp','name':'Yahoo! Auctions JP','domain':'auctions.yahoo.co.jp','weight':0.70},
 {'id':'x','name':'X 공개게시물','domain':'x.com','weight':0.48},
 {'id':'instagram','name':'Instagram 공개게시물','domain':'instagram.com','weight':0.48},
 {'id':'naver','name':'Naver 공개블로그/카페','domain':'blog.naver.com','weight':0.52},
)

COMPANY_PATTERNS={
 'PSA':re.compile(r'\bPSA\b',re.I),
 'BGS':re.compile(r'\b(?:BGS|BECKETT)\b',re.I),
 'CGC':re.compile(r'\bCGC\b',re.I),
 'TAG':re.compile(r'\bTAG\b',re.I),
 'BRG':re.compile(r'\bBRG\b',re.I),
}
GAME_PATTERNS={
 'pokemon':re.compile(r'pokemon|pokémon|포켓몬|ポケモン',re.I),
 'onepiece':re.compile(r'one\s*piece|원피스|ワンピース',re.I),
 'naruto':re.compile(r'naruto|나루토|ナルト',re.I),
}
DIRECT_GRADE_RE=re.compile(r'\b(?:PSA|BGS|CGC|TAG|BRG|BECKETT)\s*(?:GRADE\s*)?(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)\b',re.I)
LABEL_GRADE_RE=re.compile(r'\b(?:GEM\s*MINT|PRISTINE|BLACK\s*LABEL|MINT|NEAR\s*MINT)\s*(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)\b',re.I)
KOREAN_GRADE_RE=re.compile(r'(?:등급|그레이드|감정)\s*(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)',re.I)
CERT_RE=re.compile(r'(?:cert(?:ification)?|인증(?:번호)?|cert\.?\s*#?)\s*[:#-]?\s*([A-Za-z0-9._/-]{6,24})',re.I)
OG_IMAGE_RE=re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',re.I)
OG_IMAGE_RE_ALT=re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',re.I)

_SEARCHER=None

def _now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def _load(path:Path,default):
 try:
  d=json.loads(safe_read_text(path,max_bytes=20_000_000))
  return d if isinstance(d,type(default)) else default
 except Exception:return default

def _finite_number(value,default=0.0):
 try:number=float(value)
 except (TypeError,ValueError,OverflowError):return default
 return number if math.isfinite(number) else default

def _candidate_key(item:dict):
 company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
 if company and cert:
  grade=item.get('grade');grade_key='unknown' if grade is None else f'{_finite_number(grade,-999.0):.3f}'
  return ('cert',company,cert,grade_key)
 return ('url',str(item.get('url') or ''))

def _company(text:str)->str:
 for c,p in COMPANY_PATTERNS.items():
  if p.search(text or ''):return c
 return ''

def _grade(text:str,company:str)->float|None:
 if not company:return None
 for pat in (DIRECT_GRADE_RE,LABEL_GRADE_RE,KOREAN_GRADE_RE):
  m=pat.search(text or '')
  if not m:continue
  try:g=float(m.group(1))
  except Exception:continue
  if 1<=g<=10:return g
 return None

def _game(text:str,expected:str='')->str:
 for g,p in GAME_PATTERNS.items():
  if p.search(text or ''):return g
 return expected if expected in GAMES else 'unknown'

def _cert(text:str)->str:
 m=CERT_RE.search(text or '')
 return m.group(1).replace(' ','')[:40] if m else ''

def _registry():
 rows=[]
 for path in (VERIFIED,LIBRARY_OFFICIAL):
  d=_load(path,{})
  values=d.get('certifications',[]) if isinstance(d,dict) else []
  if isinstance(values,list):rows.extend(values)
 out={}
 for r in rows:
  if not isinstance(r,dict):continue
  c=str(r.get('company') or '').upper();cert=normalize_cert(r.get('certification_id') or r.get('cert_no'))
  try:g=float(r.get('grade') if r.get('grade') is not None else r.get('actual'))
  except Exception:continue
  if c in COMPANIES and cert and (r.get('verified') is True or r.get('officially_verified') is True or r.get('official_result') is True):out[(c,cert)]=g
 return out

def _library_verified_evidence()->dict[tuple[str,str],dict]:
 """Return fingerprints/OCR only for library photos already officially verified."""
 out={}
 reference_data=_load(LIBRARY_REFERENCES,{})
 references=reference_data.get('certifications',[]) if isinstance(reference_data,dict) else []
 for item in references if isinstance(references,list) else []:
  if not isinstance(item,dict) or item.get('official_result') is not True:continue
  company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
  if company in COMPANIES and cert:
   out[(company,cert)]={'image_sha256':str(item.get('source_sha256') or '')[:64]}
 candidate_data=_load(LIBRARY_CANDIDATES,{})
 candidates=candidate_data.get('records',[]) if isinstance(candidate_data,dict) else []
 for item in candidates if isinstance(candidates,list) else []:
  if not isinstance(item,dict) or item.get('official_result') is not True:continue
  company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
  if company not in COMPANIES or not cert:continue
  evidence=out.setdefault((company,cert),{})
  evidence.update({'image_sha256':str(item.get('sha256') or evidence.get('image_sha256') or '')[:64],
                   'image_perceptual_hash':str(item.get('perceptual_hash') or '')[:32],
                   'ocr_label_text':str(item.get('ocr_label_text') or '')[:1200],
                   'source_asset_name':str(item.get('source_name') or '')[:180]})
 return out

def _registry_seed_rows()->list[dict]:
 rows=[];seen=set();library_evidence=_library_verified_evidence()
 for path in (VERIFIED,LIBRARY_OFFICIAL):
  data=_load(path,{})
  values=data.get('certifications',[]) if isinstance(data,dict) else []
  for item in values if isinstance(values,list) else []:
   if not isinstance(item,dict):continue
   company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id') or item.get('cert_no'))
   try:grade=float(item.get('grade') if item.get('grade') is not None else item.get('actual'))
   except (TypeError,ValueError,OverflowError):continue
   verified=item.get('verified') is True or item.get('officially_verified') is True or item.get('official_result') is True
   key=(company,cert)
   if not verified or company not in COMPANIES or not cert or not 1<=grade<=10 or key in seen:continue
   seen.add(key)
   official=str(item.get('official_reference_url') or lookup_url(company,cert))
   evidence=library_evidence.get(key,{})
   rows.append({'source_id':'official_registry','source':f'{company} 공식 인증조회','search_provider':'official_registry',
                'url':official,'title':str(item.get('card_name') or f'{company} cert {cert}')[:260],'snippet':'',
                'image_url':str(item.get('image_url') or '')[:1200],'company':company,'grade':grade,
                'certification_id':cert,'game':str(item.get('game') or 'unknown'),'mode':'slab','source_weight':1.0,
                'official_result':True,'official_reference_url':official,'verification_method':'persisted_official_registry',
                'status':'verified_reference','learning_eligibility':'reference_learning_only',
                'image_sha256':evidence.get('image_sha256'),'image_perceptual_hash':evidence.get('image_perceptual_hash'),
                'image_validated':bool(evidence.get('image_sha256')),'image_probe_status':'validated' if evidence.get('image_sha256') else 'not_available',
                'ocr_label_text':evidence.get('ocr_label_text',''),'source_asset_name':evidence.get('source_asset_name',''),
                'image_evidence_source':'prevalidated_library_photo' if evidence.get('image_sha256') else 'not_available'})
 return rows

def _verified_status(company,cert,grade,registry):
 if not company or not cert or grade is None:return False
 actual=registry.get((company,cert))
 return actual is not None and abs(float(actual)-float(grade))<1e-9

def _allowed_host(host:str,domain:str)->bool:
 host=(host or '').lower().split(':')[0];domain=domain.lower()
 return host==domain or host.endswith('.'+domain)

def _unwrap_target_url(value:str,domain:str)->tuple[str,bool]:
 raw=str(value or '').strip()
 if not raw:return '',False
 current=raw
 changed=False
 for _ in range(4):
  try:p=urllib.parse.urlsplit(current)
  except ValueError:return '',changed
  host=(p.hostname or '').lower()
  if p.scheme=='https' and _allowed_host(host,domain):return current,changed
  qs=urllib.parse.parse_qs(p.query)
  target=''
  for key in ('uddg','url','target','r','q'):
   vals=qs.get(key)
   if vals and str(vals[0]).startswith(('http://','https://')):
    target=urllib.parse.unquote(str(vals[0]));break
  if not target and qs.get('u'):
   cand=str(qs['u'][0])
   try:
    decoded=urllib.parse.unquote(cand)
    if decoded.startswith(('http://','https://')):target=decoded
    elif decoded.startswith('a1'):
     token=decoded[2:];token += '='*((4-len(token)%4)%4)
     b=base64.urlsafe_b64decode(token.encode('ascii')).decode('utf-8','ignore')
     if b.startswith(('http://','https://')):target=b
   except Exception:pass
  if not target:
   # Last-resort extraction from an encoded tracking URL, still revalidated below.
   decoded=urllib.parse.unquote(current)
   m=re.search(r'https%?3A(?:%2F|/){2}[^&\s]+',current,re.I)
   if m:
    try:target=urllib.parse.unquote(m.group(0))
    except Exception:target=''
   elif 'https://' in decoded and decoded!=current:
    pos=decoded.find('https://');target=decoded[pos:]
  if not target or target==current:break
  current=target;changed=True
 try:p=urllib.parse.urlsplit(current)
 except ValueError:return '',changed
 if p.scheme=='https' and _allowed_host(p.hostname or '',domain):return current,changed
 return '',changed

def _og_image(url:str,domain:str)->str:
 try:
  u=urllib.parse.urlsplit(url)
  if u.scheme!='https' or not _allowed_host(u.hostname or '',domain):return ''
  req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.7,ja;q=0.5'})
  allowed={str(u.hostname or '').lower(),domain.lower(),'www.'+domain.lower()}
  with safe_urlopen(req,timeout=7,allowed_hosts=allowed,max_redirects=2) as r:raw=r.read(MAX_PAGE_BYTES+1)
  if len(raw)>MAX_PAGE_BYTES:return ''
  text=raw.decode('utf-8','ignore');m=OG_IMAGE_RE.search(text) or OG_IMAGE_RE_ALT.search(text)
  if not m:return ''
  img=urllib.parse.urljoin(url,m.group(1).strip())
  return img[:1200] if urllib.parse.urlsplit(img).scheme=='https' else ''
 except Exception:return ''

def _google_cse(query:str,limit:int=10)->list[dict[str,Any]]:
 key=(os.environ.get('GOOGLE_CSE_KEY') or os.environ.get('GOOGLE_CSE_API_KEY') or '').strip()
 cx=(os.environ.get('GOOGLE_CSE_CX') or os.environ.get('GOOGLE_CSE_ID') or '').strip()
 if not key or not cx:return []
 params=urllib.parse.urlencode({'key':key,'cx':cx,'q':query,'num':max(1,min(10,limit))})
 req=urllib.request.Request('https://www.googleapis.com/customsearch/v1?'+params,headers={'User-Agent':UA})
 try:
  with safe_urlopen(req,timeout=10,allowed_hosts={'www.googleapis.com'},max_redirects=1) as r:d=json.loads(r.read(2_000_000).decode('utf-8','ignore'))
 except Exception:return []
 out=[]
 for x in d.get('items',[]) if isinstance(d,dict) else []:
  if not isinstance(x,dict):continue
  image='';pm=x.get('pagemap') if isinstance(x.get('pagemap'),dict) else {};imgs=pm.get('cse_image') if isinstance(pm.get('cse_image'),list) else []
  if imgs and isinstance(imgs[0],dict):image=str(imgs[0].get('src') or '')[:1200]
  out.append({'title':str(x.get('title') or '')[:260],'url':str(x.get('link') or '')[:1200],'snippet':str(x.get('snippet') or '')[:700],'image_url':image,'search_provider':'google_cse'})
 return out

def _google_cse_images(query:str,limit:int=10)->list[dict[str,Any]]:
 key=(os.environ.get('GOOGLE_CSE_KEY') or os.environ.get('GOOGLE_CSE_API_KEY') or '').strip()
 cx=(os.environ.get('GOOGLE_CSE_CX') or os.environ.get('GOOGLE_CSE_ID') or '').strip()
 if not key or not cx:return []
 params=urllib.parse.urlencode({'key':key,'cx':cx,'q':query,'searchType':'image','safe':'active','num':max(1,min(10,limit))})
 req=urllib.request.Request('https://www.googleapis.com/customsearch/v1?'+params,headers={'User-Agent':UA})
 try:
  with safe_urlopen(req,timeout=10,allowed_hosts={'www.googleapis.com'},max_redirects=1) as r:data=json.loads(r.read(2_000_000).decode('utf-8','ignore'))
 except Exception:return []
 out=[]
 for item in data.get('items',[]) if isinstance(data,dict) else []:
  if not isinstance(item,dict):continue
  meta=item.get('image') if isinstance(item.get('image'),dict) else {}
  page=str(meta.get('contextLink') or '')
  image=str(item.get('link') or '')
  if not page.startswith('https://') or not image.startswith('https://'):continue
  out.append({'title':str(item.get('title') or '')[:260],'url':page[:1200],'snippet':str(item.get('snippet') or '')[:700],
              'image_url':image[:1200],'search_provider':'google_cse_images'})
 return out

def _searcher():
 global _SEARCHER
 if _SEARCHER is None:
  from multi_channel_agent import MultiChannelCollector
  _SEARCHER=MultiChannelCollector()
 return _SEARCHER

def _query_rows(query:str,limit:int)->tuple[list[dict],list[str]]:
 errors=[];merged=[];seen=set()
 def add(rows):
  for row in rows or []:
   if not isinstance(row,dict):continue
   url=str(row.get('url') or '').strip()
   key=url or (str(row.get('title') or ''),str(row.get('search_provider') or ''))
   if not key or key in seen:continue
   seen.add(key);merged.append(row)
 # Never let one provider suppress the others. Run independent providers in
 # parallel so a blocked Bing/DDG route does not multiply every source timeout.
 def google():return _google_cse(query,limit),None
 def bing():
  rows,err,_,_= _searcher()._search_bing_rss(query,limit);return rows,err
 def duck():
  rows,err,_,_= _searcher()._search_ddg(query,limit);return rows,err
 providers={'google_cse':google,'bing_rss':bing,'duckduckgo':duck}
 with concurrent.futures.ThreadPoolExecutor(max_workers=3,thread_name_prefix='graded-photo-search') as pool:
  future_map={pool.submit(fn):name for name,fn in providers.items()}
  for future in concurrent.futures.as_completed(future_map):
   name=future_map[future]
   try:
    rows,err=future.result()
    if err:errors.append(name+':'+str(err)[:160])
    add(rows)
   except Exception as exc:errors.append(name+':'+type(exc).__name__)
 return merged[:max(limit*3,limit)],errors

def _bing_image_rows(query:str,src:dict,limit:int=10)->list[dict]:
 try:
  url='https://www.bing.com/images/search?'+urllib.parse.urlencode({'q':query,'form':'HDRSC3'})
  req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.8,en;q=0.7'})
  with safe_urlopen(req,timeout=8,allowed_hosts={'www.bing.com','bing.com'},max_redirects=2) as r: raw=r.read(1_800_000)
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
  with safe_urlopen(req,timeout=8,allowed_hosts={'www.ebay.com','ebay.com'},max_redirects=2) as r:text=r.read(1_800_000).decode('utf-8','ignore')
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

def _queries(src:dict,game:str)->tuple[tuple[str,str],...]:
    sid=str(src.get('id') or '')
    planned=[]
    # Detailed multilingual source-specific planner. Keep the run bounded by
    # prioritising productive sources/queries while still exploring all graders.
    for company in COMPANIES:
        for qsid,q in build_queries(game,'graded_photo',company):
            if qsid==sid:
                planned.append((company,q))
                break
    # Social/community sources get two contextual discovery queries in addition
    # to grader names, because public posts often omit the word "graded".
    if sid in {'x','instagram','naver'}:
        g={'pokemon':'Pokemon 포켓몬','onepiece':'One Piece 원피스','naruto':'Naruto 나루토'}[game]
        planned.extend([('PSA',f'site:{src["domain"]} {g} PSA 10'),('BGS',f'site:{src["domain"]} {g} slab card')])
    return tuple(planned[:7])

def _discover_source_game(src:dict,game:str)->tuple[list[dict],list[str],int,dict]:
 raw=[];errors=[];queries=0;observations=[]
 detailed_started=time.monotonic()
 query_sid=SOURCE_ID_ALIASES.get(str(src.get('id') or ''),str(src.get('id') or 'unknown'))
 diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0,'image_results':0,'google_image_results':0}
 for expected_company,q in _queries(src,game):
  queries+=1;query_started=time.monotonic()
  try:
   qrows,err=_query_rows(q,10)
   relevant=0
   for rr in qrows:
    if isinstance(rr,dict):
     blob=' '.join([str(rr.get('title') or ''),str(rr.get('snippet') or '')]);company=_company(blob)
     if company and (expected_company=='ALL' or company==expected_company):relevant+=1
     item=dict(rr);item['_expected_company']=expected_company;item['_learning_query']=q[:300];raw.append(item)
   errors.extend(err);diag['raw_results']+=len(qrows)
   observations.append({'query':q,'raw':len(qrows),'accepted':relevant,'images':sum(bool(row.get('image_url')) for row in qrows if isinstance(row,dict)),'errors':len(err),'elapsed':time.monotonic()-query_started})
  except Exception as exc:
   errors.append(type(exc).__name__);observations.append({'query':q,'raw':0,'accepted':0,'images':0,'errors':1,'elapsed':time.monotonic()-query_started})
 # One compact image-search per game/source. Bing image rows expose the actual
 # marketplace page (purl) and source image (murl), which avoids search redirect loss.
 image_started=time.monotonic();iq=''
 try:
  gname={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]
  iq=f'site:{src["domain"]} {gname} PSA BGS CGC TAG BRG graded card slab'
  irows=_bing_image_rows(iq,src,12)
  grows=_google_cse_images(iq,10)
  for item in grows:
   page=str(item.get('url') or '')
   try:host=(urllib.parse.urlsplit(page).hostname or '').lower()
   except ValueError:continue
   if _allowed_host(host,src['domain']):irows.append(item)
  diag['google_image_results']+=len(grows)
  if src.get('id')=='ebay_public':
   direct=_ebay_public_rows(game,12)
   existing={str(x.get('url') or '') for x in irows}
   irows.extend(x for x in direct if str(x.get('url') or '') not in existing)
  for rr in irows:
   if isinstance(rr,dict):
    item=dict(rr)
    item['_expected_company']=_company(str(item.get('title') or '')) or 'PSA'
    item['_learning_query']=iq[:300]
    raw.append(item)
  diag['image_results']+=len(irows);diag['raw_results']+=len(irows)
  observations.append({'query':iq,'raw':len(irows),'accepted':sum(bool(_company(str(item.get('title') or ''))) for item in irows if isinstance(item,dict)),'images':sum(bool(item.get('image_url')) for item in irows if isinstance(item,dict)),'errors':0,'elapsed':time.monotonic()-image_started})
 except Exception as exc:
  errors.append('bing_images:'+type(exc).__name__)
  observations.append({'query':iq or f'{game}:image_search','raw':0,'accepted':0,'images':0,'errors':1,'elapsed':time.monotonic()-image_started})
 candidates={}
 for r in raw:
  raw_url=str(r.get('url') or '')
  url,resolved=_unwrap_target_url(raw_url,src['domain'])
  if not url:continue
  if resolved:diag['resolved_redirects']+=1
  item=dict(r);item['url']=url;item['_raw_url']=raw_url
  candidates.setdefault(url,item)
 diag['domain_matches']=len(candidates)
 out=[]
 for idx,(url,r) in enumerate(list(candidates.items())[:MAX_PER_SOURCE]):
  blob=' '.join([str(r.get('title') or ''),str(r.get('snippet') or '')])
  c=_company(blob) or str(r.get('_expected_company') or '').upper()
  if c not in COMPANIES:continue
  diag['company_matches']+=1
  g=_grade(blob,c);cert=_cert(blob);image=str(r.get('image_url') or '')
  if not image and idx<MAX_IMAGE_PROBES_PER_SOURCE:image=_og_image(url,src['domain'])
  out.append({'source_id':src['id'],'source':src['name'],'search_provider':r.get('search_provider'),'url':url[:1200],
              'title':str(r.get('title') or '')[:260],'snippet':str(r.get('snippet') or '')[:700],'image_url':image[:1200],
              'company':c,'grade':g,'certification_id':cert,'game':_game(blob,game),'mode':'slab','source_weight':src['weight'],
              'grade_from_search':g is not None,'_learning_query':str(r.get('_learning_query') or '')[:300]})
 try:
  record_collection_cycle(query_sid,game,observations,raw=diag.get('raw_results',0),accepted=len(out),images=sum(bool(x.get('image_url')) for x in out),errors=len(errors),elapsed=time.monotonic()-detailed_started)
 except Exception:
  pass
 try:
  record_query_result(str(src.get('id') or 'unknown'), f'{game}:graded_photo', raw=diag.get('raw_results',0), accepted=len(out), images=sum(bool(x.get('image_url')) for x in out), errors=len(errors), elapsed=time.monotonic()-detailed_started)
 except Exception:
  pass
 return out,errors,queries,diag

def _collect_public_source(src:dict):
 found_by_game={};errors=[];queries=0;diag={'raw_results':0,'domain_matches':0,'company_matches':0,'resolved_redirects':0,'image_results':0,'google_image_results':0}
 for game in GAMES:
  rows,err,q,d=_discover_source_game(src,game);found_by_game[game]=rows;errors.extend(err);queries+=q
  for k in diag: diag[k]+=int(d.get(k,0))
 # A busy Pokemon query must not consume the whole per-source cap before
 # ONE PIECE and NARUTO are considered.  Round-robin across games while still
 # deduplicating the same marketplace page.
 selected=[];seen=set();positions={game:0 for game in GAMES}
 while len(selected)<MAX_PER_SOURCE:
  progressed=False
  for game in GAMES:
   rows=found_by_game.get(game,[]);pos=positions[game]
   while pos<len(rows):
    item=rows[pos];pos+=1;url=str(item.get('url') or '')
    if not url or url in seen:continue
    seen.add(url);selected.append(item);progressed=True;break
   positions[game]=pos
   if len(selected)>=MAX_PER_SOURCE:break
  if not progressed:break
 diag['game_candidates']={game:sum(str(x.get('game') or '')==game for x in selected) for game in GAMES}
 return src['id'],selected,errors,queries,diag

def _ebay_access_token()->str:
 token=os.environ.get('EBAY_OAUTH_TOKEN','').strip()
 if token:return token
 client_id=os.environ.get('EBAY_CLIENT_ID','').strip();secret=os.environ.get('EBAY_CLIENT_SECRET','').strip()
 if not client_id or not secret:return ''
 credentials=base64.b64encode(f'{client_id}:{secret}'.encode('utf-8')).decode('ascii')
 body=urllib.parse.urlencode({'grant_type':'client_credentials','scope':'https://api.ebay.com/oauth/api_scope'}).encode('ascii')
 request=urllib.request.Request('https://api.ebay.com/identity/v1/oauth2/token',data=body,method='POST',
                                headers={'Authorization':'Basic '+credentials,'Content-Type':'application/x-www-form-urlencoded','User-Agent':UA})
 try:
  with safe_urlopen_no_redirect(request,timeout=10,allowed_hosts={'api.ebay.com'}) as response:
   data=json.loads(response.read(200_000).decode('utf-8','ignore'))
  value=str(data.get('access_token') or '') if isinstance(data,dict) else ''
  return value[:5000]
 except Exception:return ''

def _ebay_candidates()->list[dict]:
 token=_ebay_access_token()
 if not token:return []
 try:
  from ebay_grader_learning import discover
  rows=discover(token,per_query=4,max_items=40,pause=0.05)
 except Exception:return []
 out=[]
 for x in rows:
  out.append({'source_id':'ebay','source':'eBay Browse API','search_provider':'ebay_api','url':x.item_url,'title':x.title,'snippet':'',
              'image_url':x.image_urls[0] if x.image_urls else '','image_urls':list(x.image_urls),'company':x.company,'grade':x.grade,
              'certification_id':x.certification_id,'game':x.game,'mode':'slab','source_weight':0.98})
 return out

def _save_learning(stats:dict):
 d=_load(LEARNING,{});src=d.setdefault('sources',{})
 for sid,x in stats.items():
  r=src.setdefault(sid,{'runs':0,'candidates':0,'image_hits':0,'verified_hits':0,'errors':0,'queries':0})
  for k in ('runs','candidates','image_hits','verified_hits','errors','queries'):
   add=1 if k=='runs' else int(x.get(k,0));r[k]=int(r.get(k,0))+add
  r['last_at']=_now()
 d['updated_at']=_now();atomic_write_json(LEARNING,d,suffix='.graded-photo-learning.tmp')

def _adaptive_timeout_seconds(state:dict)->int:
    a=state.get('adaptive_timeout') if isinstance(state.get('adaptive_timeout'),dict) else {}
    runs=int(a.get('completed_runs',0) or 0)
    recent=a.get('recent',[]) if isinstance(a.get('recent'),list) else []
    recent=recent[-8:]
    timeout_rate=(sum(1 for x in recent if isinstance(x,dict) and int(x.get('timed_out_sources',0) or 0)>0)/len(recent)) if recent else 0.0
    elapsed=[float(x.get('elapsed_seconds',0) or 0) for x in recent if isinstance(x,dict) and float(x.get('elapsed_seconds',0) or 0)>0]
    avg=(sum(elapsed)/len(elapsed)) if elapsed else 0.0
    if runs < 3: base=3600
    elif runs < 8: base=1800
    elif runs < 15: base=900
    elif runs < 30: base=300
    else: base=120
    if timeout_rate >= 0.50: base=max(base,3600)
    elif timeout_rate >= 0.25: base=max(base,1800)
    if avg>0: base=max(base,min(3600,int(avg*2.2+30)))
    return max(120,min(3600,int(base)))

def _record_adaptive_timeout(state:dict,elapsed:float,timed_out:int,total_candidates:int,raw_results:int)->int:
    a=state.setdefault('adaptive_timeout',{})
    recent=a.setdefault('recent',[])
    recent.append({'at':_now(),'elapsed_seconds':round(float(elapsed),1),'timed_out_sources':int(timed_out),'total_candidates':int(total_candidates),'raw_results':int(raw_results)})
    a['recent']=recent[-12:]
    a['completed_runs']=int(a.get('completed_runs',0) or 0)+1
    a['last_elapsed_seconds']=round(float(elapsed),1)
    a['last_timed_out_sources']=int(timed_out)
    a['last_candidates']=int(total_candidates)
    a['last_raw_results']=int(raw_results)
    return _adaptive_timeout_seconds(state)

def _official_verify_rows(rows:list[dict],registry:dict,max_live:int=10)->tuple[list[dict],dict]:
 cache=_load(OFFICIAL_CACHE,{})
 entries=cache.get('entries',{}) if isinstance(cache.get('entries'),dict) else {}
 now=time.time();live=0;stats={'registry_matches':0,'live_attempts':0,'live_verified':0,'conflicts':0,'unavailable':0}
 output=[]
 for raw in rows:
  item=dict(raw);company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
  try:grade=float(item.get('grade')) if item.get('grade') is not None else None
  except (TypeError,ValueError,OverflowError):grade=None
  if company not in COMPANIES or not cert or grade is None:
   output.append(item);continue
  item['certification_id']=cert
  registered=registry.get((company,cert))
  if registered is not None:
   if abs(float(registered)-grade)<1e-9:
    item.update({'official_result':True,'official_reference_url':lookup_url(company,cert),
                 'verification_method':'persisted_official_registry','official_grade':float(registered)})
    stats['registry_matches']+=1
   else:
    item['evidence_conflicts']=sorted(set((item.get('evidence_conflicts') or [])+['official_grade_conflict']))
    item['official_grade']=float(registered);stats['conflicts']+=1
   output.append(item);continue
  key=f'{company}:{cert}'
  cached=entries.get(key) if isinstance(entries.get(key),dict) else None
  fresh=bool(cached and now-float(cached.get('checked_epoch',0) or 0)<7*86400)
  if fresh:
   result=cached.get('result') if isinstance(cached.get('result'),dict) else {}
  elif live<max_live:
   result=verify_cert(company,cert,expected_grade=grade,timeout=10);live+=1;stats['live_attempts']+=1
   entries[key]={'checked_epoch':now,'result':result}
  else:
   result={}
  if result.get('verified') is True:
   item.update({'official_result':True,'official_reference_url':result.get('official_url') or lookup_url(company,cert),
                'verification_method':'live_official_lookup','official_grade':float(result.get('grade'))})
   stats['live_verified']+=1
  elif result.get('conflict') is True:
   item['evidence_conflicts']=sorted(set((item.get('evidence_conflicts') or [])+['official_grade_conflict']))
   item['official_grade']=result.get('grade');stats['conflicts']+=1
  elif result:
   item['official_lookup_status']=str(result.get('lookup_error') or result.get('notice') or 'not_verified')[:180]
   stats['unavailable']+=1
  output.append(item)
 cache={'schema_version':1,'updated_at':_now(),'entries':dict(list(entries.items())[-500:])}
 atomic_write_json(OFFICIAL_CACHE,cache,suffix='.official-cache.tmp')
 return output,stats

def _resolve_cert_conflicts(rows:list[dict])->list[dict]:
 groups={}
 for item in rows:
  company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
  if company in COMPANIES and cert:groups.setdefault((company,cert),[]).append(item)
 for group in groups.values():
  official=[x for x in group if x.get('official_result') is True and x.get('official_grade') is not None]
  official_grade=float(official[0]['official_grade']) if official else None
  seen_grades=set()
  for item in group:
   try:
    if item.get('grade') is not None:seen_grades.add(float(item.get('grade')))
   except (TypeError,ValueError,OverflowError):pass
  if len(seen_grades)<=1:continue
  for item in group:
   try:value=float(item.get('grade')) if item.get('grade') is not None else None
   except (TypeError,ValueError,OverflowError):value=None
   if official_grade is None or value is None or abs(value-official_grade)>1e-9:
    item['evidence_conflicts']=sorted(set((item.get('evidence_conflicts') or [])+['cross_source_grade_conflict']))
    item['official_result']=False
 return rows

def _resolve_image_conflicts(rows:list[dict])->tuple[list[dict],dict]:
 groups={}
 for item in rows:
  digest=str(item.get('image_sha256') or '').lower()
  if re.fullmatch(r'[0-9a-f]{64}',digest):groups.setdefault(digest,[]).append(item)
 duplicate_groups=0;conflicts=0
 for group in groups.values():
  if len(group)<2:continue
  duplicate_groups+=1;labels=set();official_labels=set()
  for item in group:
   company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
   grade=None if item.get('grade') is None else _finite_number(item.get('grade'),-999.0)
   label=(company,cert,grade)
   if company and cert and grade!=-999.0:labels.add(label)
   if item.get('official_result') is True:official_labels.add(label)
  if len(labels)<=1:continue
  trusted_label=next(iter(official_labels)) if len(official_labels)==1 else None
  for item in group:
   company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
   grade=None if item.get('grade') is None else _finite_number(item.get('grade'),-999.0)
   label=(company,cert,grade)
   if trusted_label is not None and item.get('official_result') is True and label==trusted_label:continue
   existing=item.get('evidence_conflicts') if isinstance(item.get('evidence_conflicts'),list) else []
   item['evidence_conflicts']=sorted(set(str(x) for x in existing+['duplicate_image_label_conflict'] if x))
   item['official_result']=False;conflicts+=1
 return rows,{'exact_duplicate_image_groups':duplicate_groups,'image_label_conflicts':conflicts}

def _save_reference_learning(rows:list[dict])->dict:
 current=_load(REFERENCE_LEARNING,{})
 existing=current.get('references',[]) if isinstance(current.get('references'),list) else []
 merged={}
 for item in existing+rows:
  if not isinstance(item,dict) or item.get('official_result') is not True:continue
  company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
  if company not in COMPANIES or not cert or item.get('evidence_conflicts'):continue
  try:grade=float(item.get('official_grade') if item.get('official_grade') is not None else item.get('grade'))
  except (TypeError,ValueError,OverflowError):continue
  merged[(company,cert)]={'company':company,'certification_id':cert,'official_grade':grade,
                          'card_name':str(item.get('title') or '')[:260],'game':str(item.get('game') or 'unknown'),
                          'official_reference_url':str(item.get('official_reference_url') or item.get('url') or '')[:1200],
                          'image_sha256':str(item.get('image_sha256') or '')[:64],
                          'learning_scope':'slab_label_and_source_reference_only'}
 payload={'schema_version':1,'updated_at':_now(),'references':list(merged.values())[-500:],
          'summary':{'reference_learning_count':len(merged),'raw_grade_calibration_rows_written':0},
          'policy':{'official_match_required':True,'raw_and_slab_isolated':True,'same_image_prediction_training':False}}
 atomic_write_json(REFERENCE_LEARNING,payload,suffix='.reference-learning.tmp');return payload

def collect()->dict:
 run_started=time.monotonic();registry=_registry();stats={};errors=[]
 is_android='com.termux' in os.environ.get('PREFIX','')
 previous_payload=_load(OUT,{})
 previous_rows=previous_payload.get('records',[]) if isinstance(previous_payload,dict) else []
 if not isinstance(previous_rows,list):previous_rows=[]
 previous_rows=[dict(x) for x in previous_rows if isinstance(x,dict)]
 seeds=_registry_seed_rows();rows=previous_rows+seeds;previous_count=len(previous_rows)
 ebay_rows=_ebay_candidates();rows.extend(ebay_rows)
 stats['ebay_api']={'candidates':len(ebay_rows),'image_hits':sum(bool(x.get('image_url')) for x in ebay_rows),
                    'verified_hits':0,'errors':0,'queries':1 if ebay_rows else 0,
                    'configured':bool(os.environ.get('EBAY_OAUTH_TOKEN') or (os.environ.get('EBAY_CLIENT_ID') and os.environ.get('EBAY_CLIENT_SECRET')))}
 state=_load(LEARNING,{})
 adaptive_timeout_seconds=_adaptive_timeout_seconds(state)
 first_bootstrap=not bool(state.get('initial_collection_completed'))
 try:cursor=int(state.get('source_cursor',0))%len(SOURCES)
 except Exception:cursor=0
 if first_bootstrap:
  bootstrap_limit=3 if is_android else len(BOOTSTRAP_SOURCE_IDS)
  active=[next(x for x in SOURCES if x['id']==sid) for sid in BOOTSTRAP_SOURCE_IDS[:bootstrap_limit]]
  state['initial_collection_started_at']=state.get('initial_collection_started_at') or _now()
  state['source_cursor']=len(active)%len(SOURCES)
 else:
  batch_limit=3 if is_android else RUN_SOURCE_LIMIT
  active=[SOURCES[(cursor+i)%len(SOURCES)] for i in range(min(batch_limit,len(SOURCES)))]
  state['source_cursor']=(cursor+len(active))%len(SOURCES)
 state['last_active_sources']=[x['id'] for x in active]
 atomic_write_json(LEARNING,state,suffix='.graded-photo-cursor.tmp')

 pool=concurrent.futures.ThreadPoolExecutor(max_workers=min(len(active),3 if is_android else 6),thread_name_prefix='graded-photo')
 futures={pool.submit(_collect_public_source,src):src for src in active}
 run_timeout=max(120,min(RUN_WAIT_SECONDS,adaptive_timeout_seconds))
 done,pending=concurrent.futures.wait(futures,timeout=run_timeout)
 for future in done:
  src=futures[future]
  try:
   sid,found,source_errors,queries,diag=future.result();rows.extend(found)
   stats[sid]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),
               'verified_hits':0,'errors':len(source_errors),'queries':queries,**diag}
   errors.extend(f'{sid}:{value}' for value in source_errors[:4])
  except Exception as exc:
   sid=src['id'];stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0}
   errors.append(sid+':'+type(exc).__name__)
 for future in pending:
  src=futures[future];future.cancel();sid=src['id']
  stats[sid]={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1,'queries':0,'timed_out':True}
  errors.append(sid+':run_timeout')
 pool.shutdown(wait=True,cancel_futures=True)

 # First dedup keeps the best source while retaining every independent source id.
 dedup={};source_sets={}
 for raw in rows:
  item=dict(raw);company=str(item.get('company') or '').upper();cert=normalize_cert(item.get('certification_id'))
  if cert:item['certification_id']=cert
  key=_candidate_key(item)
  if not key[-1]:continue
  source_sets.setdefault(key,set()).add(str(item.get('source_id') or ''))
  old=dedup.get(key)
  if old is None or _finite_number(item.get('source_weight'))>_finite_number(old.get('source_weight')):dedup[key]=item
 rows=list(dedup.values())[:MAX_ROWS]
 for item in rows:
  key=_candidate_key(item)
  item['_dedup_sources']=sorted(x for x in source_sets.get(key,set()) if x)

 try:probe_limit=int(os.environ.get('TCG_GRADED_IMAGE_PROBE_LIMIT','6' if is_android else '12'))
 except (TypeError,ValueError,OverflowError):probe_limit=6 if is_android else 12
 rows,image_stats=enrich_rows(rows,limit=max(0,min(probe_limit,24)),workers=2 if is_android else 4)
 image_stats['prevalidated_library']=sum(x.get('image_evidence_source')=='prevalidated_library_photo' for x in rows)
 rows,official_stats=_official_verify_rows(rows,registry,max_live=5 if is_android else 10)
 rows=_resolve_cert_conflicts(rows)
 rows,image_conflict_stats=_resolve_image_conflicts(rows);official_stats.update(image_conflict_stats)
 try:
  learning_feedback=record_official_feedback(rows);collection_learning=learning_snapshot()
 except Exception as exc:
  learning_feedback={'rows_observed':0,'official_verified':0,'identifiers_learned':0,'error':type(exc).__name__}
  collection_learning={'version':2,'error':'snapshot_unavailable','policy':{'query_learning_cannot_change_trust':True}}

 # Cross-source corroboration remains advisory; only official matching can verify.
 groups={}
 for item in rows:
  item.pop('_learning_query',None)
  key=canonical_key(str(item.get('title') or ''),str(item.get('url') or ''))
  groups.setdefault(key,set()).update(item.pop('_dedup_sources',[]) or [str(item.get('source_id') or '')])
 for item in rows:
  key=canonical_key(str(item.get('title') or ''),str(item.get('url') or ''))
  ids=sorted(value for value in groups.get(key,set()) if value)
  item['cross_source_count']=len(ids);item['cross_sources']=ids[:16]
  verified=bool(item.get('official_result') is True and not item.get('evidence_conflicts'))
  reasons=[]
  if item.get('evidence_conflicts'):reasons.extend(str(x) for x in item.get('evidence_conflicts') if x)
  if not item.get('certification_id'):reasons.append('certification_unresolved')
  if item.get('grade') is None:reasons.append('grade_unresolved')
  if not item.get('image_url'):reasons.append('image_url_missing')
  elif item.get('image_probe_status')=='failed':reasons.append('image_validation_failed')
  if not verified:reasons.append('official_verification_missing')
  item['quarantine_reasons']=sorted(set(reasons))
  item['status']='verified_reference' if verified else 'quarantine_candidate'
  item['learning_eligibility']='reference_learning_only' if verified else 'not_eligible_unverified'
  item['evidence_confidence']=evidence_confidence(ids or [item.get('source_id')],verified)
  if verified:
   sid=str(item.get('source_id') or 'unknown')
   stats.setdefault(sid,{'candidates':0,'image_hits':0,'verified_hits':0,'errors':0,'queries':0})
   stats[sid]['verified_hits']=int(stats[sid].get('verified_hits',0))+1

 reference_learning=_save_reference_learning(rows)
 verified_count=sum(item.get('status')=='verified_reference' for item in rows)
 game_stats={}
 for game in GAMES:
  game_rows=[item for item in rows if item.get('game')==game]
  game_stats[game]={'name':GAME_DISPLAY_NAMES[game],'candidates':len(game_rows),
                    'with_image_url':sum(bool(item.get('image_url')) for item in game_rows),
                    'validated_images':sum(bool(item.get('image_validated')) for item in game_rows),
                    'ocr_readable':sum(bool(item.get('ocr_label_text')) for item in game_rows),
                    'verified_references':sum(item.get('status')=='verified_reference' for item in game_rows),
                    'quarantined':sum(item.get('status')!='verified_reference' for item in game_rows)}
 provider_counts=collections.Counter(str(item.get('search_provider') or 'unknown') for item in rows)
 for source in SOURCES:
  stats.setdefault(source['id'],{'candidates':0,'image_hits':0,'verified_hits':0,'errors':0,'queries':0,'not_run_this_cycle':True})
 google_configured=bool((os.environ.get('GOOGLE_CSE_KEY') or os.environ.get('GOOGLE_CSE_API_KEY')) and
                        (os.environ.get('GOOGLE_CSE_CX') or os.environ.get('GOOGLE_CSE_ID')))
 ebay_configured=bool(os.environ.get('EBAY_OAUTH_TOKEN') or (os.environ.get('EBAY_CLIENT_ID') and os.environ.get('EBAY_CLIENT_SECRET')))
 payload={'schema_version':4,'engine':'v123-verified-multisource-photo-collection','created_at':_now(),'records':rows,
          'summary':{'total_candidates':len(rows),'with_image_url':sum(bool(x.get('image_url')) for x in rows),
                     'validated_images':sum(bool(x.get('image_validated')) for x in rows),'ocr_readable':sum(bool(x.get('ocr_label_text')) for x in rows),
                     'certifications_resolved':sum(bool(x.get('certification_id')) for x in rows),'verified_references':verified_count,
                     'reference_learning_count':int((reference_learning.get('summary') or {}).get('reference_learning_count',0)),
                     'raw_grade_calibration_eligible':0,'quarantined':len(rows)-verified_count,
                     'sources':len({x.get('source_id') for x in rows if x.get('source_id')}),'status':'ok' if rows else 'no_candidates',
                     'queries_attempted':sum(int(x.get('queries',0) or 0) for x in stats.values()),'markets_this_run':[x['id'] for x in active],
                     'timed_out_sources':sum(bool(x.get('timed_out')) for x in stats.values()),'initial_bootstrap_collection':first_bootstrap,
                     'previous_candidates':previous_count,'registry_seed_count':len(seeds),
                     'raw_results':sum(int(x.get('raw_results',0) or 0) for x in stats.values()),
                     'domain_matches':sum(int(x.get('domain_matches',0) or 0) for x in stats.values()),
                     'company_matches':sum(int(x.get('company_matches',0) or 0) for x in stats.values()),
                     'resolved_redirects':sum(int(x.get('resolved_redirects',0) or 0) for x in stats.values()),
                     'image_results':sum(int(x.get('image_results',0) or 0) for x in stats.values()),
                     'google_image_results':sum(int(x.get('google_image_results',0) or 0) for x in stats.values()),
                     'exact_duplicate_image_groups':int(image_conflict_stats.get('exact_duplicate_image_groups',0)),
                     'image_label_conflicts':int(image_conflict_stats.get('image_label_conflicts',0)),
                     'adaptive_timeout_seconds':adaptive_timeout_seconds,'elapsed_seconds':0.0,'next_timeout_seconds':adaptive_timeout_seconds},
          'image_probe_stats':image_stats,'official_verification_stats':official_stats,
          'collection_learning_stats':collection_learning,'collection_learning_feedback':learning_feedback,
          'game_stats':game_stats,
          'provider_stats':dict(sorted(provider_counts.items(),key=lambda pair:(-pair[1],pair[0]))),
          'source_stats':stats,'errors':errors[:100],
          'configuration':{'google_cse_configured':google_configured,'google_cse_note':'existing customers only; public search fallbacks stay enabled',
                           'ebay_oauth_configured':ebay_configured,'ebay_client_credentials_supported':True,
                           'games_targeted':list(GAMES),'game_collection_balance':'round_robin_per_source',
                           'collection_learning_version':2,'query_strategy':'verified-feedback bandit with bounded exploration',
                           'amazon_mode':'public search fallback; deprecated PA-API is not called',
                           'kream_daangn_mode':'public search-index candidates only; login bypass disabled'},
          'policy':{'public_only':True,'login_bypass':False,'seller_label_is_official':False,'official_registry_match_required':True,
                    'slab_raw_isolated':True,'raw_calibration_modified':False,'image_bytes_auto_cached':False,
                    'duplicate_image_training':False,'conflicting_labels_quarantined':True,
                    'collection_learning_cannot_change_trust':True,'verified_feedback_only':True}}
 elapsed_seconds=round(time.monotonic()-run_started,1);payload['summary']['elapsed_seconds']=elapsed_seconds
 timed_out=int(payload['summary'].get('timed_out_sources',0) or 0)
 learning_state=_load(LEARNING,{})
 next_timeout=_record_adaptive_timeout(learning_state,elapsed_seconds,timed_out,len(rows),int(payload['summary'].get('raw_results',0) or 0))
 payload['summary']['next_timeout_seconds']=next_timeout
 learning_state['last_adaptive_timeout_seconds']=adaptive_timeout_seconds;learning_state['next_adaptive_timeout_seconds']=next_timeout
 if first_bootstrap:
  learning_state['initial_collection_completed']=True;learning_state['initial_collection_completed_at']=_now()
 atomic_write_json(LEARNING,learning_state,suffix='.graded-photo-adaptive.tmp')
 atomic_write_json(OUT,payload,suffix='.graded-photo.tmp');_save_learning(stats);return payload

def main():
 p=collect();print(json.dumps(p['summary'],ensure_ascii=False));return p

if __name__=='__main__':main()
