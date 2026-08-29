#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detailed public-source query planning + adaptive source learning.

This module does not bypass login walls or private APIs. It separates discovery
providers (search engines) from evidence sources (marketplaces/social/public pages)
and learns which source/query combinations are productive for each game/purpose.
"""
from __future__ import annotations

import json, math, re, time
from pathlib import Path
from typing import Iterable

ROOT=Path(__file__).resolve().parent
LEARNING=ROOT/'detailed_collection_learning.json'

GAMES={
 'pokemon':('Pokemon','Pokemon TCG','포켓몬 카드','포켓몬카드','ポケモンカード'),
 'onepiece':('One Piece Card Game','One Piece TCG','원피스 카드','원피스카드','ワンピースカード'),
 'naruto':('Naruto Card Game','Naruto TCG','나루토 카드','나루토카드','NARUTO カード'),
}

EVIDENCE_SOURCES=(
 {'id':'ebay','domains':('ebay.com',),'weight':0.92,'kind':'market'},
 {'id':'amazon_us','domains':('amazon.com',),'weight':0.68,'kind':'market'},
 {'id':'amazon_jp','domains':('amazon.co.jp',),'weight':0.70,'kind':'market'},
 {'id':'kream','domains':('kream.co.kr',),'weight':0.84,'kind':'market'},
 {'id':'daangn','domains':('daangn.com',),'weight':0.68,'kind':'market'},
 {'id':'bunjang','domains':('bunjang.co.kr',),'weight':0.70,'kind':'market'},
 {'id':'joongna','domains':('joongna.com',),'weight':0.68,'kind':'market'},
 {'id':'collectory','domains':('collectory.cc',),'weight':0.80,'kind':'market'},
 {'id':'tcgplayer','domains':('tcgplayer.com',),'weight':0.78,'kind':'market'},
 {'id':'cardmarket','domains':('cardmarket.com',),'weight':0.76,'kind':'market'},
 {'id':'mercari_jp','domains':('jp.mercari.com',),'weight':0.74,'kind':'market'},
 {'id':'yahoo_jp','domains':('auctions.yahoo.co.jp',),'weight':0.72,'kind':'market'},
 {'id':'x','domains':('x.com','twitter.com'),'weight':0.48,'kind':'social'},
 {'id':'instagram','domains':('instagram.com',),'weight':0.48,'kind':'social'},
 {'id':'naver','domains':('blog.naver.com','cafe.naver.com','m.blog.naver.com'),'weight':0.52,'kind':'community'},
)

PURPOSE_TERMS={
 'graded_photo':(
  'PSA graded card','BGS graded card','CGC graded card','TAG graded card','BRG graded card',
  'slab card','Gem Mint 10','Pristine 10','등급 카드','감정 카드','그레이딩 카드'
 ),
 'market':('sold','sale','price','market price','거래','판매','시세','실거래','落札','相場'),
 'box':('booster box','BOX','sealed box','박스','미개봉','ボックス'),
 'hit':('SAR','SEC','SP','parallel','alt art','super parallel','HIT','고레어','최고가 카드'),
 'release':('release','launch','preorder','restock','출시','발매','예약','재발매','発売','再販'),
 'event':('promo','collab','event','movie','프로모','콜라보','행사','영화','イベント','コラボ'),
}


def _load():
 try:
  d=json.loads(LEARNING.read_text(encoding='utf-8'))
  return d if isinstance(d,dict) else {}
 except Exception:return {}

def _save(d):
 tmp=LEARNING.with_suffix('.tmp')
 tmp.write_text(json.dumps(d,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 tmp.replace(LEARNING)

def source_by_id(source_id:str):
 for s in EVIDENCE_SOURCES:
  if s['id']==source_id:return s
 return None

def build_queries(game:str,purpose:str='graded_photo',company:str='')->list[tuple[str,str]]:
 names=GAMES.get(game,GAMES['pokemon'])
 terms=list(PURPOSE_TERMS.get(purpose,PURPOSE_TERMS['graded_photo']))
 if company:
  company=company.upper().strip()
  terms=[f'{company} graded card',f'{company} 10',f'{company} 9',f'{company} slab']+terms[:3]
 d=_load();stats=d.get('source_query_stats',{}) if isinstance(d,dict) else {}
 rows=[]
 for src in EVIDENCE_SOURCES:
  learned=stats.get(src['id'],{}) if isinstance(stats,dict) else {}
  score=float(learned.get('score',0.0))
  for domain in src['domains'][:1]:
   # Mix English/Korean/Japanese names so regional listings are not starved.
   for name in (names[0],names[2],names[4]):
    for term in terms[:4]:
     rows.append((src['id'],f'site:{domain} {name} {term}'))
  if score>0.6:
   # Productive sources get one extra broader query learned from prior success.
   rows.append((src['id'],f'site:{src["domains"][0]} {names[0]} {company or purpose}'))
 return rows

def canonical_key(title:str,url:str='')->str:
 t=re.sub(r'[^a-z0-9가-힣ぁ-んァ-ヶ一-龥]+',' ',str(title or '').lower())
 t=re.sub(r'\b(psa|bgs|cgc|tag|brg|gem mint|pristine|slab)\b',' ',t)
 t=' '.join(t.split())[:180]
 return t or str(url or '')[:180]

def evidence_confidence(source_ids:Iterable[str], official_verified:bool=False)->float:
 ids=[]
 for sid in source_ids:
  if sid and sid not in ids:ids.append(sid)
 base=0.0
 for sid in ids:
  s=source_by_id(sid)
  if s:base+=float(s['weight'])
 # Cross-source corroboration matters more than repeated hits from one source.
 confidence=1.0-math.exp(-base/max(1.0,len(ids))) if ids else 0.0
 confidence+=min(0.25,max(0,len(ids)-1)*0.06)
 if official_verified:confidence=max(confidence,0.98)
 return round(min(0.99,confidence),4)

def record_query_result(source_id:str,query:str,raw:int=0,accepted:int=0,images:int=0,errors:int=0,elapsed:float=0.0):
 d=_load();d.setdefault('schema_version',1);d['updated_at']=int(time.time())
 stats=d.setdefault('source_query_stats',{})
 s=stats.setdefault(source_id,{'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'elapsed_total':0.0,'score':0.5,'queries':{}})
 s['runs']=int(s.get('runs',0))+1;s['raw']=int(s.get('raw',0))+int(raw);s['accepted']=int(s.get('accepted',0))+int(accepted)
 s['images']=int(s.get('images',0))+int(images);s['errors']=int(s.get('errors',0))+int(errors);s['elapsed_total']=float(s.get('elapsed_total',0.0))+float(elapsed)
 q=s.setdefault('queries',{});qk=query[:220];qr=q.setdefault(qk,{'runs':0,'raw':0,'accepted':0})
 qr['runs']+=1;qr['raw']+=int(raw);qr['accepted']+=int(accepted)
 success=(int(accepted)+0.35*int(images))/(max(1,int(raw)))
 error_penalty=min(0.5,int(errors)*0.08)
 old=float(s.get('score',0.5));s['score']=round(max(0.05,min(0.99,old*0.82+(success-error_penalty)*0.18)),4)
 # Keep file bounded: top 80 query histories/source by accepted then raw.
 if len(q)>80:
  keep=sorted(q.items(),key=lambda kv:(kv[1].get('accepted',0),kv[1].get('raw',0),kv[1].get('runs',0)),reverse=True)[:80]
  s['queries']=dict(keep)
 _save(d)

def source_priority(source_id:str)->float:
 s=source_by_id(source_id);base=float(s['weight']) if s else 0.4
 d=_load();learned=(d.get('source_query_stats',{}) or {}).get(source_id,{}) if isinstance(d,dict) else {}
 return round(base*0.65+float(learned.get('score',0.5))*0.35,4)
