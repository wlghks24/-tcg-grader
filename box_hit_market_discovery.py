#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from html import unescape
import json, os, re

BASE=Path(__file__).resolve().parent
OUT=BASE/'box_hit_market_candidates.json'
LEARNING=BASE/'box_hit_market_learning.json'
UA='Mozilla/5.0 TCG-Grader/1.0'

SOURCES=[
 ('ebay','eBay','ebay.com',0.96),('amazon_us','Amazon US','amazon.com',0.74),('amazon_jp','Amazon JP','amazon.co.jp',0.77),
 ('kream','KREAM','kream.co.kr',0.93),('daangn','당근','daangn.com',0.78),('bunjang','번개장터','bunjang.co.kr',0.84),
 ('joongna','중고나라','joongna.com',0.82),('collectory','Collectory','collectory.cc',0.91),('tcgplayer','TCGplayer','tcgplayer.com',0.90),
 ('cardmarket','Cardmarket','cardmarket.com',0.87),('mercari_jp','Mercari JP','jp.mercari.com',0.85),('yahoo_jp','Yahoo Japan','auctions.yahoo.co.jp',0.83),
]
GAMES={
 'Pokémon':('pokemon','포켓몬','ポケモン'),
 'ONE PIECE':('one piece','원피스','ワンピース'),
 'NARUTO':('naruto','나루토'),
}
BOX_WORDS=('booster box','display box','sealed box',' booster ',' box ','박스','부스터팩','부스터 팩','box','ボックス','ブースター')
HIT_WORDS=('sar','sr','sec','sp','manga','manga rare','parallel','promo','프로모','패러렐','시크릿','alt art','special art','illustration rare','bwr','ur','コミパラ','パラレル')
NEGATIVE=('sleeve','binder','deck box','storage box','case only','empty box','빈박스','박스만','보관함','플레이매트')
REGION_HINTS={'KR':('korean','korea','한국','한글판','kr '),'JP':('japanese','japan','일본','일판','jp ','日本','日版'),'US':('english','eng ','usa','us ','미국','영문판')}


def _atomic(path,data):
    tmp=Path(str(path)+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def _rss(query,limit=10):
    url='https://www.bing.com/search?format=rss&q='+quote_plus(query)
    req=Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.8,ja;q=0.7'})
    with urlopen(req,timeout=12) as r:raw=r.read(1_500_000)
    root=ET.fromstring(raw);out=[]
    for item in root.findall('.//item')[:limit]:
        title=unescape(item.findtext('title') or '').strip();link=(item.findtext('link') or '').strip()
        desc=re.sub(r'<[^>]+>',' ',unescape(item.findtext('description') or ''));desc=re.sub(r'\s+',' ',desc).strip()
        out.append({'title':title[:260],'url':link[:900],'snippet':desc[:700],'date':(item.findtext('pubDate') or '')[:80]})
    return out

def _game(text):
    low=text.lower()
    for game,words in GAMES.items():
        if any(w.lower() in low for w in words):return game
    return ''

def _region(text,source_id):
    low=' '+text.lower()+' '
    for region,words in REGION_HINTS.items():
        if any(w.lower() in low for w in words):return region
    if source_id in ('amazon_jp','mercari_jp','yahoo_jp'):return 'JP'
    if source_id in ('kream','daangn','bunjang','joongna'):return 'KR'
    return 'US'

def _asset(text):
    low=' '+text.lower()+' '
    if any(x in low for x in NEGATIVE):return ''
    hit=any(x in low for x in HIT_WORDS);box=any(x in low for x in BOX_WORDS)
    if hit and not box:return 'HIT'
    if box and not hit:return 'BOX'
    if hit and box:
        # listing title usually puts the exact card rarity after the set name; prioritize card signal.
        return 'HIT' if re.search(r'\b(?:SAR|SEC|SP|SR|UR|BWR)\b|manga rare|parallel|promo|패러렐|프로모',text,re.I) else 'BOX'
    return ''

def _clean_name(title,game,asset):
    s=re.sub(r'\s+',' ',title).strip()
    s=re.sub(r'(?i)\b(new|sealed|authentic|official|pokemon|one piece|naruto|card game|tcg|ccg)\b',' ',s)
    s=re.sub(r'(?i)\b(korean|japanese|english|korea|japan|usa)\b',' ',s)
    s=re.sub(r'(?i)\b(booster box|display box|sealed box)\b',' ',s)
    s=re.sub(r'\s+',' ',s).strip(' -|:/·')
    return (s[:110] or f'{game} {asset}')

def _key_tokens(name):
    words=[w.lower() for w in re.findall(r'[A-Za-z0-9가-힣ァ-ヶ一-龠]+',name) if len(w)>=2]
    stop={'pokemon','one','piece','naruto','card','game','tcg','booster','box','sealed','official','japanese','korean','english'}
    return tuple(sorted(w for w in words if w not in stop)[:10])

def _ebay_api(query):
    token=os.environ.get('EBAY_OAUTH_TOKEN','').strip()
    if not token:return []
    url='https://api.ebay.com/buy/browse/v1/item_summary/search?q='+quote_plus(query)+'&limit=40'
    req=Request(url,headers={'Authorization':'Bearer '+token,'X-EBAY-C-MARKETPLACE-ID':'EBAY_US','User-Agent':UA})
    with urlopen(req,timeout=15) as r:d=json.loads(r.read(2_000_000).decode('utf-8','ignore'))
    out=[]
    for x in d.get('itemSummaries') or []:
        image=((x.get('image') or {}).get('imageUrl') or '')
        out.append({'title':str(x.get('title') or '')[:260],'url':str(x.get('itemWebUrl') or '')[:900],'snippet':'','date':'',
                    'image_url':image if image.startswith('https://') else '','verified_api':True})
    return out

def discover_market_catalog():
    raw=[];errors=[];source_stats=defaultdict(lambda:{'queries':0,'results':0,'accepted':0,'errors':0})
    # Broad discovery intentionally samples each game/asset instead of only already-known catalog names.
    query_templates=[('BOX','{game} trading card booster box'),('HIT','{game} card SAR SR SEC SP manga rare parallel promo')]
    for game in GAMES:
        for wanted,template in query_templates:
            game_query='Pokemon' if game=='Pokémon' else game
            base=template.format(game=game_query)
            if wanted=='BOX' and game=='NARUTO':base='Naruto Card Game booster box cards'
            if wanted=='HIT' and game=='NARUTO':base='Naruto Card Game rare promo parallel card'
            try:
                for r in _ebay_api(base):raw.append({**r,'source_id':'ebay','source':'eBay','weight':0.96,'query_asset':wanted})
            except Exception as e:errors.append('eBay API:'+type(e).__name__)
            for sid,name,domain,weight in SOURCES:
                source_stats[sid]['queries']+=1
                try:rows=_rss(f'site:{domain} {base}',8)
                except Exception as e:
                    source_stats[sid]['errors']+=1;errors.append(name+':'+type(e).__name__);continue
                source_stats[sid]['results']+=len(rows)
                for r in rows:
                    host=(urlparse(r.get('url','')).hostname or '').lower()
                    if domain not in host:continue
                    raw.append({**r,'source_id':sid,'source':name,'weight':weight,'query_asset':wanted})
    grouped={}
    for r in raw:
        blob=(r.get('title','')+' '+r.get('snippet','')).strip();game=_game(blob);asset=_asset(blob)
        if not game or not asset:continue
        # Require agreement with the discovery query to reduce accessory/noise contamination.
        if asset!=r.get('query_asset'):continue
        name=_clean_name(r.get('title',''),game,asset);tokens=_key_tokens(name)
        if len(tokens)<1:continue
        region=_region(blob,r.get('source_id',''))
        key=(region,game,asset,tokens)
        rec=grouped.setdefault(key,{'country':region,'game':game,'asset':asset,'name':name,'sources':{},'urls':[], 'images':[], 'score':0.0})
        sid=r.get('source_id');rec['sources'][sid]=r.get('source');rec['score']+=float(r.get('weight') or 0)
        if r.get('url') and r['url'] not in rec['urls']:rec['urls'].append(r['url'])
        if r.get('image_url','').startswith('https://') and r['image_url'] not in rec['images']:rec['images'].append(r['image_url'])
        source_stats[sid]['accepted']+=1
    candidates=[]
    for rec in grouped.values():
        source_count=len(rec['sources']);verified_image=bool(rec['images'])
        # Promotion gate: 2 independent public sources, or eBay API image plus one public result.
        promoted=source_count>=2 or (verified_image and 'ebay' in rec['sources'])
        rec['source_count']=source_count;rec['promoted']=promoted;rec['image_url']=rec['images'][0] if rec['images'] else ''
        rec['source_names']=list(rec['sources'].values());rec['source_urls']=rec.pop('urls')[:8];rec.pop('images',None);rec.pop('sources',None)
        rec['score']=round(rec['score'],3);candidates.append(rec)
    candidates.sort(key=lambda x:(not x['promoted'],-x['source_count'],-x['score']))
    payload={'version':1,'updated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'candidates':candidates[:180],
             'summary':{'total':len(candidates),'promoted':sum(1 for x in candidates if x['promoted']),'with_image':sum(1 for x in candidates if x['image_url']),
                        'source_count':len([x for x in source_stats if source_stats[x]['results']])},'source_stats':dict(source_stats),'errors':errors[:40],
             'notice':'공개 검색결과와 공식 API가 제공되는 경우에만 사용합니다. 2개 이상 독립 출처 또는 eBay API 이미지 근거가 있는 후보만 카탈로그 승격 대상으로 표시합니다.'}
    _atomic(OUT,payload);_atomic(LEARNING,{'updated_at':payload['updated_at'],'source_stats':dict(source_stats)})
    return payload

def merge_market_catalog(db):
    payload=discover_market_catalog();entries=db.setdefault('entries',{})
    added=0;updated=0
    for x in payload.get('candidates',[]):
        if not x.get('promoted'):continue
        country=x['country'];asset=x['asset'];name=x['name'];key=f'{country}|{name}|{asset}'
        row=entries.setdefault(key,{})
        was=bool(row)
        row.setdefault('display','가격 확인 중');row.setdefault('kind','다중마켓 자동발견 후보');row.setdefault('market',' · '.join(x.get('source_names') or []))
        row.setdefault('transactions',f"독립 공개출처 {x.get('source_count',0)}곳 교차발견")
        row.setdefault('source',(x.get('source_urls') or [''])[0]);row.setdefault('source_date',datetime.now(timezone.utc).date().isoformat())
        row.setdefault('game',x.get('game'));row.setdefault('product_name',name);row['asset']=asset;row['discovered_market']=True
        row['source_crosschecks']=[{'source':s} for s in (x.get('source_names') or [])]
        if x.get('image_url') and not row.get('image_url'):row['image_url']=x['image_url']
        row['preference_signal']=min(100,45+x.get('source_count',0)*12+int(min(25,x.get('score',0)*2)))
        if asset=='HIT':row.setdefault('card_name',name)
        if was:updated+=1
        else:added+=1
    db['box_hit_market_discovery']={'updated_at':payload.get('updated_at'),'added':added,'updated':updated,**payload.get('summary',{})}
    return payload

if __name__=='__main__':
    print(json.dumps(discover_market_catalog(),ensure_ascii=False,indent=2))
