#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detailed public-source query planning + adaptive source learning.

This module does not bypass login walls or private APIs. It separates discovery
providers (search engines) from evidence sources (marketplaces/social/public pages)
and learns which source/query combinations are productive for each game/purpose.
"""
from __future__ import annotations

import hashlib, json, math, re, threading, time
from pathlib import Path
from typing import Any, Iterable

from safe_runtime import atomic_write_json, atomic_write_text, exclusive_file_lock, safe_read_text

ROOT=Path(__file__).resolve().parent
LEARNING=ROOT/'detailed_collection_learning.json'
LEARNING_BACKUP=ROOT/'detailed_collection_learning.json.bak'
LEARNING_LOCK=threading.RLock()
MAX_QUERY_HISTORY=240
MAX_VERIFIED_TERMS=60
MAX_FEEDBACK_EVENTS=2000
RECENT_HALF_LIFE_SECONDS=14*86400
SOURCE_ALIASES={'ebay_public':'ebay','ebay_api':'ebay'}

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


def _load_path(path:Path)->dict:
 try:
  d=json.loads(safe_read_text(path,max_bytes=3_000_000))
  return d if isinstance(d,dict) else {}
 except Exception:return {}

def _load():
 with LEARNING_LOCK:
  primary=_load_path(LEARNING)
  return primary or _load_path(LEARNING_BACKUP)

def _save_unlocked(d:dict):
 previous=_load_path(LEARNING)
 if previous:
  atomic_write_text(LEARNING_BACKUP,json.dumps(previous,ensure_ascii=False,separators=(',',':'))+'\n',suffix='.learning-backup.tmp')
 atomic_write_json(LEARNING,d,suffix='.detailed-learning.tmp')

def _save(d):
 with LEARNING_LOCK,exclusive_file_lock(LEARNING):_save_unlocked(d)

def _number(value:Any,default:float=0.0)->float:
 try:value=float(value)
 except (TypeError,ValueError,OverflowError):return default
 return value if math.isfinite(value) else default

def _source_id(value:Any)->str:
 value=str(value or 'unknown')[:80]
 return SOURCE_ALIASES.get(value,value)

def _dict(value:Any)->dict:
 return value if isinstance(value,dict) else {}

def _decay_recent(row:dict,now:int)->dict:
 recent=row.get('recent') if isinstance(row.get('recent'),dict) else {}
 last=max(0,int(_number(recent.get('updated_at') or row.get('last_at'))))
 factor=0.5**(max(0,now-last)/RECENT_HALF_LIFE_SECONDS) if last else 1.0
 for key in ('runs','raw','accepted','images','verified','quarantined','errors','elapsed_total'):
  recent[key]=round(max(0.0,_number(recent.get(key)))*factor,6)
 recent['updated_at']=now;row['recent']=recent
 return recent

def _recent_add(row:dict,now:int,**increments:Any):
 recent=_decay_recent(row,now)
 for key,value in increments.items():recent[key]=round(min(1_000_000.0,max(0.0,_number(recent.get(key)))+max(0.0,_number(value))),6)

def _query_score(row:dict,total_runs:int,now:int|None=None)->float:
 current=now or int(time.time());recent=row.get('recent') if isinstance(row.get('recent'),dict) else None
 metrics=dict(recent) if recent is not None else row
 if recent is not None:
  recent_at=max(0,int(_number(recent.get('updated_at'))));factor=0.5**(max(0,current-recent_at)/RECENT_HALF_LIFE_SECONDS) if recent_at else 1.0
  for key in ('runs','raw','accepted','images','verified','quarantined','errors','elapsed_total'):metrics[key]=max(0.0,_number(metrics.get(key)))*factor
 runs=max(0.0,_number(metrics.get('runs')));raw=max(0.0,_number(metrics.get('raw')))
 accepted=max(0.0,_number(metrics.get('accepted')));images=max(0.0,_number(metrics.get('images')))
 verified=max(0.0,_number(metrics.get('verified')));errors=max(0.0,_number(metrics.get('errors')))
 elapsed=max(0.0,_number(metrics.get('elapsed_total')))
 acceptance=min(1.0,accepted/max(1,raw));image_rate=min(1.0,images/max(1,raw));verified_rate=min(1.0,verified/max(1,accepted))
 error_rate=min(1.0,errors/max(1,runs));latency=min(1.0,(elapsed/max(1,runs))/20.0)
 exploration=min(0.45,0.18*math.sqrt(math.log(max(2,total_runs)+1)/(runs+1)))
 unseen_bonus=0.30 if runs==0 else 0.0
 last=max(0,int(_number(row.get('last_feedback_at') or row.get('last_at'))))
 freshness=1.0 if not last else 0.5**(max(0,current-last)/(30*86400))
 empirical=0.40*acceptance+0.18*image_rate+0.28*verified_rate-0.25*error_rate-0.06*latency
 return round(empirical*freshness+exploration+unseen_bonus,6)

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
 verified_terms=d.get('verified_terms',{}) if isinstance(d.get('verified_terms'),dict) else {}
 game_terms=verified_terms.get(game,{}) if isinstance(verified_terms.get(game),dict) else {}
 learned_identifiers=[term for term,_ in sorted(game_terms.items(),key=lambda pair:(-_number(pair[1]),pair[0]))
                      if isinstance(term,str) and term in _verified_identifiers(term)][:3]
 rows=[]
 for src in EVIDENCE_SOURCES:
  learned=_dict(stats.get(src['id'])) if isinstance(stats,dict) else {}
  score=_number(learned.get('score'),0.0);candidates=[]
  for domain in src['domains'][:1]:
   # Mix English/Korean/Japanese names so regional listings are not starved.
   for name in (names[0],names[2],names[4]):
    for term in terms[:4]:
     candidates.append(f'site:{domain} {name} {term}')
   for identifier in learned_identifiers:
    candidates.append(f'site:{domain} {names[0]} {identifier} {company or purpose}')
  if score>0.6:
   # Productive sources get one extra broader query learned from prior success.
   candidates.append(f'site:{src["domains"][0]} {names[0]} {company or purpose}')
  candidates=list(dict.fromkeys(candidates))
  query_stats=_dict(learned.get('queries'))
  total_runs=max(0,int(_number(learned.get('runs'))))
  candidates.sort(key=lambda query:(-_query_score(_dict(query_stats.get(query[:300])),total_runs),
                                    int(_number(_dict(query_stats.get(query[:300])).get('runs'))),query))
  rows.extend((src['id'],query) for query in candidates)
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

def _bounded_count(value:Any,limit:int=1_000_000)->int:
 return max(0,min(limit,int(_number(value))))

def _add_count(value:Any,increment:Any,limit:int=1_000_000)->int:
 return _bounded_count(_bounded_count(value,limit)+_bounded_count(increment,limit),limit)

def _apply_query_observation(source:dict,observation:dict,now:int):
 raw=_bounded_count(observation.get('raw'));accepted=_bounded_count(observation.get('accepted'))
 images=_bounded_count(observation.get('images'));errors=_bounded_count(observation.get('errors'),10_000)
 elapsed=max(0.0,min(3600.0,_number(observation.get('elapsed'))));query=str(observation.get('query') or '')[:300]
 source['runs']=_add_count(source.get('runs'),1);source['raw']=_add_count(source.get('raw'),raw)
 source['accepted']=_add_count(source.get('accepted'),accepted);source['images']=_add_count(source.get('images'),images)
 source['errors']=_add_count(source.get('errors'),errors);source['elapsed_total']=round(min(86_400_000.0,max(0.0,_number(source.get('elapsed_total')))+elapsed),3)
 source['last_at']=now
 if query:
  queries=source.setdefault('queries',{})
  if not isinstance(queries,dict):queries={};source['queries']=queries
  row=queries.setdefault(query,{'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'elapsed_total':0.0,'verified':0,'quarantined':0})
  if not isinstance(row,dict):row={};queries[query]=row
  row['runs']=_add_count(row.get('runs'),1);row['raw']=_add_count(row.get('raw'),raw)
  row['accepted']=_add_count(row.get('accepted'),accepted);row['images']=_add_count(row.get('images'),images)
  row['errors']=_add_count(row.get('errors'),errors);row['elapsed_total']=round(min(86_400_000.0,max(0.0,_number(row.get('elapsed_total')))+elapsed),3);row['last_at']=now
  _recent_add(row,now,runs=1,raw=raw,accepted=accepted,images=images,errors=errors,elapsed_total=elapsed)
 _recent_add(source,now,runs=1,raw=raw,accepted=accepted,images=images,errors=errors,elapsed_total=elapsed)
 success=(accepted+0.35*images)/max(1,raw);error_penalty=min(0.5,errors*0.08)
 old=_number(source.get('score'),0.5);source['score']=round(max(0.05,min(0.99,old*0.82+(success-error_penalty)*0.18)),4)

def record_collection_cycle(source_id:str,game:str,observations:list[dict],*,raw:int=0,accepted:int=0,images:int=0,errors:int=0,elapsed:float=0.0):
 source_id=_source_id(source_id);game=game if game in GAMES else 'unknown';now=int(time.time())
 with LEARNING_LOCK,exclusive_file_lock(LEARNING):
  d=_load_path(LEARNING) or _load_path(LEARNING_BACKUP);d['schema_version']=3;d['updated_at']=now
  stats=d.setdefault('source_query_stats',{})
  if not isinstance(stats,dict):stats={};d['source_query_stats']=stats
  source=stats.setdefault(source_id,{'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'elapsed_total':0.0,'score':0.5,'queries':{}})
  if not isinstance(source,dict):source={'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'elapsed_total':0.0,'score':0.5,'queries':{}};stats[source_id]=source
  for observation in (observations if isinstance(observations,list) else [])[:20]:
   if isinstance(observation,dict):_apply_query_observation(source,observation,now)
  queries=source.get('queries',{}) if isinstance(source.get('queries'),dict) else {}
  if len(queries)>MAX_QUERY_HISTORY:
   total_runs=max(1,_bounded_count(source.get('runs')))
   clean=((query,_dict(row)) for query,row in queries.items() if isinstance(query,str))
   keep=sorted(clean,key=lambda pair:(_query_score(pair[1],total_runs),_bounded_count(pair[1].get('runs')),int(_number(pair[1].get('last_at')))),reverse=True)[:MAX_QUERY_HISTORY]
   source['queries']=dict(keep)
  route_key=f'{source_id}|{game}';routes=d.setdefault('graded_photo_routes',{})
  if not isinstance(routes,dict):routes={};d['graded_photo_routes']=routes
  route=routes.setdefault(route_key,{'source_id':source_id,'game':game,'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'verified':0,'consecutive_failures':0})
  if not isinstance(route,dict):route={'source_id':source_id,'game':game,'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'verified':0,'consecutive_failures':0};routes[route_key]=route
  route['runs']=_add_count(route.get('runs'),1);route['raw']=_add_count(route.get('raw'),raw)
  route['accepted']=_add_count(route.get('accepted'),accepted);route['images']=_add_count(route.get('images'),images)
  route['errors']=_add_count(route.get('errors'),errors);route['elapsed_total']=round(min(86_400_000.0,max(0.0,_number(route.get('elapsed_total')))+max(0.0,min(3600.0,_number(elapsed)))),3)
  failed=_bounded_count(accepted)==0 and (_bounded_count(errors)>0 or _bounded_count(raw)==0)
  route['consecutive_failures']=_add_count(route.get('consecutive_failures'),1,1000) if failed else 0
  route['last_at']=now;route['last_status']='recovery_needed' if failed else 'productive'
  _recent_add(route,now,runs=1,raw=raw,accepted=accepted,images=images,errors=errors,elapsed_total=elapsed)
  _save_unlocked(d)

def record_query_result(source_id:str,query:str,raw:int=0,accepted:int=0,images:int=0,errors:int=0,elapsed:float=0.0):
 record_collection_cycle(source_id,'unknown',[{'query':query,'raw':raw,'accepted':accepted,'images':images,'errors':errors,'elapsed':elapsed}],raw=raw,accepted=accepted,images=images,errors=errors,elapsed=elapsed)

def route_run_count(source_id:str,game:str)->int:
 source_id=_source_id(source_id);d=_load();routes=_dict(d.get('graded_photo_routes')) if isinstance(d,dict) else {};route=_dict(routes.get(f'{source_id}|{game}'))
 return _bounded_count(route.get('runs')) if isinstance(route,dict) else 0

def _verified_identifiers(text:str,certification_id:str='')->list[str]:
 values=[];cert=re.sub(r'[^A-Z0-9]','',str(certification_id or '').upper())
 # Require a card-number-like separator, a long promo prefix, or a collector
 # fraction.  This intentionally rejects grade labels such as "PSA 10".
 pattern=r'(?<![A-Z0-9])(?:[A-Z][A-Z0-9]{0,9}(?:-[A-Z0-9]{1,10}){1,2}|[A-Z]{2,6}\d{3,4}|\d{1,3}/\d{2,3})(?![A-Z0-9])'
 for match in re.findall(pattern,str(text or '').upper()):
  value=re.sub(r'\s+','',match)[:24];compact=re.sub(r'[^A-Z0-9]','',value)
  if 3<=len(value)<=24 and compact!=cert and value not in values:values.append(value)
 return values[:8]

def record_official_feedback(rows:Iterable[dict])->dict:
 feedback=[row for row in rows if isinstance(row,dict) and row.get('_learning_query')]
 if not feedback:return {'rows_observed':0,'official_verified':0,'identifiers_learned':0,'duplicates_ignored':0}
 now=int(time.time());verified_count=0;learned_count=0;duplicates=0;observed=0
 with LEARNING_LOCK,exclusive_file_lock(LEARNING):
  d=_load_path(LEARNING) or _load_path(LEARNING_BACKUP);d['schema_version']=3;d['updated_at']=now
  stats=d.setdefault('source_query_stats',{});terms=d.setdefault('verified_terms',{})
  events=d.setdefault('official_feedback_events',{})
  if not isinstance(stats,dict):stats={};d['source_query_stats']=stats
  if not isinstance(terms,dict):terms={};d['verified_terms']=terms
  if not isinstance(events,dict):events={};d['official_feedback_events']=events
  for item in feedback:
   source_id=_source_id(item.get('source_id'));query=str(item.get('_learning_query') or '')[:300]
   company=str(item.get('company') or '').upper()[:12];cert=re.sub(r'[^A-Z0-9]','',str(item.get('certification_id') or '').upper())[:48]
   stable='|'.join((source_id,query,company,cert,str(item.get('url') or item.get('image_sha256') or '')[:1200],str(item.get('official_result') is True),','.join(sorted(str(x) for x in (item.get('evidence_conflicts') or [])))))
   event_id=hashlib.sha256(stable.encode('utf-8','ignore')).hexdigest()
   if event_id in events:duplicates+=1;continue
   events[event_id]=now;observed+=1
   source=stats.setdefault(source_id,{'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'elapsed_total':0.0,'score':0.5,'queries':{}})
   if not isinstance(source,dict):source={'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'elapsed_total':0.0,'score':0.5,'queries':{}};stats[source_id]=source
   queries=source.setdefault('queries',{})
   if not isinstance(queries,dict):queries={};source['queries']=queries
   query_row=queries.setdefault(query,{'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'elapsed_total':0.0,'verified':0,'quarantined':0})
   if not isinstance(query_row,dict):query_row={};queries[query]=query_row
   verified=bool(item.get('official_result') is True and not item.get('evidence_conflicts'))
   key='verified' if verified else 'quarantined';query_row[key]=_add_count(query_row.get(key),1);query_row['last_feedback_at']=now
   _recent_add(query_row,now,**{key:1})
   game=str(item.get('game') or '')
   if game in GAMES:
    routes=d.setdefault('graded_photo_routes',{})
    if not isinstance(routes,dict):routes={};d['graded_photo_routes']=routes
    route=routes.setdefault(f'{source_id}|{game}',{'source_id':source_id,'game':game,'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'verified':0,'consecutive_failures':0})
    if not isinstance(route,dict):route={'source_id':source_id,'game':game,'runs':0,'raw':0,'accepted':0,'images':0,'errors':0,'verified':0,'consecutive_failures':0};routes[f'{source_id}|{game}']=route
    if verified:route['verified']=_add_count(route.get('verified'),1);_recent_add(route,now,verified=1)
   if not verified:continue
   verified_count+=1;game_terms=terms.setdefault(game,{}) if game in GAMES else None
   if game_terms is not None and not isinstance(game_terms,dict):game_terms={};terms[game]=game_terms
   if game_terms is not None:
    for identifier in _verified_identifiers(str(item.get('title') or ''),str(item.get('certification_id') or '')):
     game_terms[identifier]=_add_count(game_terms.get(identifier),1);learned_count+=1
  for game,game_terms in list(terms.items()):
   if not isinstance(game_terms,dict):terms[game]={};continue
   terms[game]=dict(sorted(game_terms.items(),key=lambda pair:(-_number(pair[1]),pair[0]))[:MAX_VERIFIED_TERMS])
  totals=d.setdefault('official_feedback_totals',{})
  if not isinstance(totals,dict):totals={};d['official_feedback_totals']=totals
  if len(events)>MAX_FEEDBACK_EVENTS:
   d['official_feedback_events']=dict(sorted(events.items(),key=lambda pair:_number(pair[1]),reverse=True)[:MAX_FEEDBACK_EVENTS])
  totals['rows_observed']=_add_count(totals.get('rows_observed'),observed)
  totals['official_verified']=_add_count(totals.get('official_verified'),verified_count);totals['identifiers_learned']=_add_count(totals.get('identifiers_learned'),learned_count);totals['last_at']=now
  totals['duplicates_ignored']=_add_count(totals.get('duplicates_ignored'),duplicates)
  _save_unlocked(d)
 return {'rows_observed':observed,'official_verified':verified_count,'identifiers_learned':learned_count,'duplicates_ignored':duplicates}

def learning_snapshot()->dict:
 d=_load();stats=d.get('source_query_stats',{}) if isinstance(d.get('source_query_stats'),dict) else {};routes=d.get('graded_photo_routes',{}) if isinstance(d.get('graded_photo_routes'),dict) else {}
 terms=d.get('verified_terms',{}) if isinstance(d.get('verified_terms'),dict) else {};totals=d.get('official_feedback_totals',{}) if isinstance(d.get('official_feedback_totals'),dict) else {}
 return {'version':3,'source_profiles':len(stats),'queries_tracked':sum(len(s.get('queries',{})) for s in stats.values() if isinstance(s,dict) and isinstance(s.get('queries'),dict)),
         'query_runs':sum(_bounded_count(s.get('runs')) for s in stats.values() if isinstance(s,dict)),'routes_tracked':len(routes),
         'productive_routes':sum(_bounded_count(r.get('accepted'))>0 for r in routes.values() if isinstance(r,dict)),
         'recovery_routes':sum(_bounded_count(r.get('consecutive_failures'))>0 for r in routes.values() if isinstance(r,dict)),
         'official_feedback':_bounded_count(totals.get('official_verified')),
         'duplicate_feedback_ignored':_bounded_count(totals.get('duplicates_ignored')),
         'verified_identifiers':{game:[term for term,_ in sorted(_dict(terms.get(game)).items(),key=lambda pair:(-_number(pair[1]),pair[0]))[:5]] for game in GAMES},
         'policy':{'verified_feedback_only':True,'query_learning_cannot_change_trust':True,'exploration_retained':True,'recency_decay_enabled':True,'idempotent_feedback':True,'cross_process_lock':True,'state_backup_enabled':True}}

def source_priority(source_id:str)->float:
 source_id=_source_id(source_id)
 s=source_by_id(source_id);base=float(s['weight']) if s else 0.4
 d=_load();learned=_dict(_dict(d.get('source_query_stats')).get(source_id)) if isinstance(d,dict) else {}
 last=max(0,int(_number(learned.get('last_at'))));freshness=1.0 if not last else 0.5**(max(0,int(time.time())-last)/(30*86400))
 learned_score=0.5+(_number(learned.get('score'),0.5)-0.5)*freshness
 return round(base*0.65+max(0.05,min(0.99,learned_score))*0.35,4)
