#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quarantine-first graded-card photo discovery across public marketplaces.

Public/search-visible material is collected as reference candidates only. Seller
text, slab labels, or marketplace metadata never become calibration truth by
itself. A candidate is promoted to verified_reference only when the local
verified-certification registry independently matches company/cert/grade.

This module intentionally does NOT write learning_store.json and does NOT change
raw-card calibration. Slab photos may improve corpus coverage, label recognition,
provider coverage and QA, but cumulative grading correction still requires an
independent raw prediction paired to an official result.
"""
from __future__ import annotations

import json, os, re, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json
import multi_market_price_collector as market

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'graded_photo_candidates.json'
LEARNING=ROOT/'graded_photo_source_learning.json'
VERIFIED=ROOT/'verified_certifications.json'
UA='Mozilla/5.0 TCG-Grader-GradedPhotoCollector/1.0'
COMPANIES=('PSA','BGS','CGC','TAG','BRG')
GAMES=('pokemon','onepiece','naruto')
MAX_ROWS=180
MAX_PER_SOURCE=12
MAX_PAGE_BYTES=1_200_000

SOURCES=(
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
)

COMPANY_PATTERNS={
 'PSA':re.compile(r'\bPSA\b',re.I),'BGS':re.compile(r'\b(?:BGS|BECKETT)\b',re.I),
 'CGC':re.compile(r'\bCGC\b',re.I),'TAG':re.compile(r'\bTAG\b',re.I),'BRG':re.compile(r'\bBRG\b',re.I),
}
GAME_PATTERNS={'pokemon':re.compile(r'pokemon|pokémon|포켓몬',re.I),'onepiece':re.compile(r'one\s*piece|원피스',re.I),'naruto':re.compile(r'naruto|나루토',re.I)}
GRADE_RE=re.compile(r'\b(?:PSA|BGS|CGC|TAG|BRG|BECKETT)\s*(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)\b',re.I)
CERT_RE=re.compile(r'(?:cert(?:ification)?|인증(?:번호)?|cert\.?\s*#?)\s*[:#-]?\s*([A-Za-z0-9._/-]{6,24})',re.I)
OG_IMAGE_RE=re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)',re.I)
OG_IMAGE_RE_ALT=re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\']',re.I)


def _now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

def _load(path:Path, default):
 try:
  d=json.loads(path.read_text(encoding='utf-8'))
  return d if isinstance(d,type(default)) else default
 except Exception:return default

def _company(text:str)->str:
 for c,p in COMPANY_PATTERNS.items():
  if p.search(text or ''): return c
 return ''

def _grade(text:str, company:str)->float|None:
 if not company:return None
 m=GRADE_RE.search(text or '')
 if not m:return None
 try:g=float(m.group(1))
 except Exception:return None
 return g if 1<=g<=10 else None

def _game(text:str)->str:
 for g,p in GAME_PATTERNS.items():
  if p.search(text or ''):return g
 return 'unknown'

def _cert(text:str)->str:
 m=CERT_RE.search(text or '')
 return (m.group(1).replace(' ','')[:40] if m else '')

def _registry():
 d=_load(VERIFIED,{})
 rows=d.get('certifications',[]) if isinstance(d,dict) else []
 out={}
 for r in rows if isinstance(rows,list) else []:
  if not isinstance(r,dict):continue
  c=str(r.get('company') or '').upper(); cert=str(r.get('certification_id') or r.get('cert_no') or '').strip()
  try:g=float(r.get('grade') if r.get('grade') is not None else r.get('actual'))
  except Exception:continue
  if c in COMPANIES and cert and (r.get('verified') is True or r.get('officially_verified') is True or r.get('official_result') is True):out[(c,cert)]=g
 return out

def _verified_status(company,cert,grade,registry):
 if not company or not cert or grade is None:return False
 actual=registry.get((company,cert))
 return actual is not None and abs(float(actual)-float(grade))<1e-9

def _allowed_host(host:str, domain:str)->bool:
 host=(host or '').lower().split(':')[0]
 domain=domain.lower()
 return host==domain or host.endswith('.'+domain)

def _og_image(url:str,domain:str)->str:
 try:
  u=urllib.parse.urlsplit(url)
  if u.scheme!='https' or not _allowed_host(u.hostname or '',domain):return ''
  req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.7'})
  with urllib.request.urlopen(req,timeout=10) as r:
   raw=r.read(MAX_PAGE_BYTES+1)
  if len(raw)>MAX_PAGE_BYTES:return ''
  text=raw.decode('utf-8','ignore')
  m=OG_IMAGE_RE.search(text) or OG_IMAGE_RE_ALT.search(text)
  if not m:return ''
  img=urllib.parse.urljoin(url,m.group(1).strip())
  p=urllib.parse.urlsplit(img)
  return img[:1200] if p.scheme=='https' else ''
 except Exception:return ''

def _google_cse(query:str,limit:int=10)->list[dict[str,Any]]:
 key=os.environ.get('GOOGLE_CSE_KEY','').strip(); cx=os.environ.get('GOOGLE_CSE_CX','').strip()
 if not key or not cx:return []
 params=urllib.parse.urlencode({'key':key,'cx':cx,'q':query,'num':max(1,min(10,limit))})
 req=urllib.request.Request('https://www.googleapis.com/customsearch/v1?'+params,headers={'User-Agent':UA})
 try:
  with urllib.request.urlopen(req,timeout=12) as r:d=json.loads(r.read(2_000_000).decode('utf-8','ignore'))
 except Exception:return []
 out=[]
 for x in d.get('items',[]) if isinstance(d,dict) else []:
  if not isinstance(x,dict):continue
  image=''
  pm=x.get('pagemap') if isinstance(x.get('pagemap'),dict) else {}
  imgs=pm.get('cse_image') if isinstance(pm.get('cse_image'),list) else []
  if imgs and isinstance(imgs[0],dict):image=str(imgs[0].get('src') or '')[:1200]
  out.append({'title':str(x.get('title') or '')[:260],'url':str(x.get('link') or '')[:1200],'snippet':str(x.get('snippet') or '')[:700],'image_url':image,'search_provider':'google_cse'})
 return out

def _discover_source(src:dict,company:str,game:str)->list[dict]:
 game_term={'pokemon':'Pokemon','onepiece':'One Piece','naruto':'Naruto'}[game]
 q=f'site:{src["domain"]} {game_term} {company} graded card'
 rows=_google_cse(q,MAX_PER_SOURCE)
 if not rows:
  try:rows=[{**r,'search_provider':'bing_rss'} for r in market._rss(q,MAX_PER_SOURCE)]
  except Exception:rows=[]
 out=[]
 for r in rows:
  url=str(r.get('url') or '')
  p=urllib.parse.urlsplit(url)
  if p.scheme!='https' or not _allowed_host(p.hostname or '',src['domain']):continue
  blob=' '.join([str(r.get('title') or ''),str(r.get('snippet') or '')])
  c=_company(blob);g=_grade(blob,c);cert=_cert(blob)
  if c!=company or g is None:continue
  image=str(r.get('image_url') or '') or _og_image(url,src['domain'])
  out.append({'source_id':src['id'],'source':src['name'],'search_provider':r.get('search_provider'),'url':url[:1200],'title':str(r.get('title') or '')[:260],
              'snippet':str(r.get('snippet') or '')[:700],'image_url':image[:1200],'company':c,'grade':g,'certification_id':cert,'game':_game(blob),'mode':'slab','source_weight':src['weight']})
 return out

def _ebay_candidates()->list[dict]:
 token=os.environ.get('EBAY_OAUTH_TOKEN','').strip()
 if not token:return []
 try:
  from ebay_grader_learning import discover
  rows=discover(token,per_query=4,max_items=40,pause=0.05)
 except Exception:return []
 out=[]
 for x in rows:
  out.append({'source_id':'ebay','source':'eBay Browse API','search_provider':'ebay_api','url':x.item_url,'title':x.title,'snippet':'','image_url':x.image_urls[0] if x.image_urls else '',
              'image_urls':list(x.image_urls),'company':x.company,'grade':x.grade,'certification_id':x.certification_id,'game':x.game,'mode':'slab','source_weight':0.98,'structured_label':x.structured_label})
 return out

def _load_learning():return _load(LEARNING,{})

def _save_learning(stats:dict):
 d=_load_learning();src=d.setdefault('sources',{})
 for sid,x in stats.items():
  r=src.setdefault(sid,{'runs':0,'candidates':0,'image_hits':0,'verified_hits':0,'errors':0})
  r['runs']=int(r.get('runs',0))+1;r['candidates']=int(r.get('candidates',0))+int(x.get('candidates',0));r['image_hits']=int(r.get('image_hits',0))+int(x.get('image_hits',0));r['verified_hits']=int(r.get('verified_hits',0))+int(x.get('verified_hits',0));r['errors']=int(r.get('errors',0))+int(x.get('errors',0));r['last_at']=_now()
 d['updated_at']=_now();atomic_write_json(LEARNING,d,suffix='.graded-photo-learning.tmp')

def collect()->dict:
 registry=_registry();rows=[];stats={};errors=[]
 # eBay official API path first.
 try:
  e=_ebay_candidates();rows.extend(e);stats['ebay']={'candidates':len(e),'image_hits':sum(bool(x.get('image_url')) for x in e),'verified_hits':0,'errors':0}
 except Exception as exc:stats['ebay']={'candidates':0,'image_hits':0,'verified_hits':0,'errors':1};errors.append('ebay:'+type(exc).__name__)
 for src in SOURCES:
  found=[];err=0
  for company in COMPANIES:
   for game in GAMES:
    try:found.extend(_discover_source(src,company,game))
    except Exception as exc:err+=1;errors.append(src['id']+':'+type(exc).__name__)
  # bounded per source and URL-deduped
  seen={}
  for x in found:
   if x['url'] not in seen:seen[x['url']]=x
  found=list(seen.values())[:MAX_PER_SOURCE]
  rows.extend(found);stats[src['id']]={'candidates':len(found),'image_hits':sum(bool(x.get('image_url')) for x in found),'verified_hits':0,'errors':err}
 # Dedupe by cert first, then URL/image.
 dedup={}
 for x in rows:
  key=(x.get('company'),x.get('certification_id')) if x.get('certification_id') else (x.get('url') or x.get('image_url'))
  if not key:continue
  old=dedup.get(key)
  if not old or float(x.get('source_weight',0))>float(old.get('source_weight',0)):dedup[key]=x
 rows=list(dedup.values())[:MAX_ROWS]
 verified_count=0
 for x in rows:
  ok=_verified_status(x.get('company'),x.get('certification_id'),x.get('grade'),registry)
  x['official_result']=bool(ok);x['status']='verified_reference' if ok else 'quarantine_candidate'
  x['learning_eligibility']='reference_only_missing_raw_prediction' if ok else 'not_eligible_unverified'
  if ok:
   verified_count+=1;stats.setdefault(x.get('source_id','unknown'),{'candidates':0,'image_hits':0,'verified_hits':0,'errors':0})['verified_hits']+=1
 payload={'schema_version':1,'created_at':_now(),'records':rows,'summary':{'total_candidates':len(rows),'with_image_url':sum(bool(x.get('image_url')) for x in rows),'verified_references':verified_count,'quarantined':len(rows)-verified_count,'sources':len({x.get('source_id') for x in rows})},
          'source_stats':stats,'errors':errors[:80],'google_cse_configured':bool(os.environ.get('GOOGLE_CSE_KEY') and os.environ.get('GOOGLE_CSE_CX')),
          'ebay_oauth_configured':bool(os.environ.get('EBAY_OAUTH_TOKEN')),
          'policy':{'public_only':True,'login_bypass':False,'seller_label_is_official':False,'official_registry_match_required':True,'slab_raw_isolated':True,'raw_calibration_modified':False,'image_bytes_auto_cached':False}}
 atomic_write_json(OUT,payload,suffix='.graded-photo.tmp');_save_learning(stats);return payload

def main():
 p=collect();print(json.dumps(p['summary'],ensure_ascii=False));return p

if __name__=='__main__':main()
