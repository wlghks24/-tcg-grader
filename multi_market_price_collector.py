#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
from html import unescape
from xml.etree import ElementTree as ET
import json, os, re, statistics, time

BASE=Path(__file__).resolve().parent
CACHE=BASE/'multi_market_price_cache.json'
LEARNING=BASE/'multi_market_source_learning.json'
FX=BASE/'exchange_rates.json'
CACHE_TTL=15*60
UA='Mozilla/5.0 TCG-Grader/1.0'

SOURCES=[
 {'id':'ebay','name':'eBay','domain':'ebay.com','weight':0.95,'kind':'글로벌 마켓'},
 {'id':'amazon_us','name':'Amazon US','domain':'amazon.com','weight':0.72,'kind':'판매가'},
 {'id':'amazon_jp','name':'Amazon JP','domain':'amazon.co.jp','weight':0.75,'kind':'판매가'},
 {'id':'kream','name':'KREAM','domain':'kream.co.kr','weight':0.92,'kind':'국내 거래/호가'},
 {'id':'daangn','name':'당근','domain':'daangn.com','weight':0.76,'kind':'지역 중고'},
 {'id':'bunjang','name':'번개장터','domain':'bunjang.co.kr','weight':0.82,'kind':'국내 중고'},
 {'id':'joongna','name':'중고나라','domain':'joongna.com','weight':0.80,'kind':'국내 중고'},
 {'id':'collectory','name':'Collectory','domain':'collectory.cc','weight':0.90,'kind':'카드시세'},
 {'id':'tcgplayer','name':'TCGplayer','domain':'tcgplayer.com','weight':0.88,'kind':'TCG 마켓'},
 {'id':'cardmarket','name':'Cardmarket','domain':'cardmarket.com','weight':0.86,'kind':'유럽 TCG'},
 {'id':'mercari_jp','name':'Mercari JP','domain':'jp.mercari.com','weight':0.84,'kind':'일본 중고'},
 {'id':'yahoo_jp','name':'Yahoo! Auctions JP','domain':'auctions.yahoo.co.jp','weight':0.82,'kind':'일본 경매'},
]

PRICE_PATTERNS=[
 ('KRW',re.compile(r'(?:₩\s*|KRW\s*)([0-9][0-9,]{2,})',re.I)),
 ('KRW',re.compile(r'([0-9][0-9,]{2,})\s*원')),
 ('JPY',re.compile(r'(?:¥|￥|JPY\s*)([0-9][0-9,]{2,})',re.I)),
 ('USD',re.compile(r'(?:US\s*)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',re.I)),
]

SOLD_WORDS=('sold','completed','판매완료','거래완료','낙찰','체결')

def _safe_json(path,default):
    try:
        value=json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value,type(default)) else default
    except Exception:return default

def _atomic(path,data):
    try:
        tmp=Path(str(path)+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
    except Exception:pass

def _fx():
    d=_safe_json(FX,{})
    rates=d.get('rates') if isinstance(d,dict) else {}
    return {'USD':float((rates or {}).get('USD_KRW') or 0),'JPY':float((rates or {}).get('JPY_KRW') or 0),'KRW':1.0}

def _to_krw(amount,currency,fx):
    rate=fx.get(currency,0)
    return int(round(float(amount)*rate)) if rate and amount else 0

def _extract_price(text,fx):
    values=[]
    for currency,pat in PRICE_PATTERNS:
        for m in pat.finditer(text or ''):
            try:a=float(m.group(1).replace(',',''))
            except Exception:continue
            krw=_to_krw(a,currency,fx)
            if 100<=krw<=100_000_000:values.append((krw,a,currency))
    if not values:return None
    # Search snippets sometimes include unrelated shipping/discount values. Prefer the largest plausible card price.
    krw,a,c=max(values,key=lambda x:x[0])
    return {'price_krw':krw,'price_native':a,'currency':c}

def _rss(query,limit=8):
    url='https://www.bing.com/search?format=rss&q='+quote_plus(query)
    req=Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.7,ja;q=0.5'})
    with urlopen(req,timeout=12) as r: raw=r.read(1_500_000)
    root=ET.fromstring(raw)
    out=[]
    for item in root.findall('.//item')[:limit]:
        title=unescape(item.findtext('title') or '').strip()
        link=(item.findtext('link') or '').strip()
        desc=re.sub(r'<[^>]+>',' ',unescape(item.findtext('description') or ''))
        desc=re.sub(r'\s+',' ',desc).strip()
        date=(item.findtext('pubDate') or '').strip()
        out.append({'title':title[:240],'url':link[:800],'snippet':desc[:600],'date':date[:80]})
    return out

def _ebay_api(query,region,fx):
    token=os.environ.get('EBAY_OAUTH_TOKEN','').strip()
    if not token:return []
    marketplace='EBAY_US' if region!='JP' else 'EBAY_US'
    url='https://api.ebay.com/buy/browse/v1/item_summary/search?q='+quote_plus(query)+'&limit=20'
    req=Request(url,headers={'Authorization':'Bearer '+token,'X-EBAY-C-MARKETPLACE-ID':marketplace,'User-Agent':UA})
    with urlopen(req,timeout=15) as r:d=json.loads(r.read(2_000_000).decode('utf-8','ignore'))
    rows=[]
    for x in (d.get('itemSummaries') or []):
        p=x.get('price') or {};cur=str(p.get('currency') or 'USD').upper()
        try:amt=float(p.get('value'))
        except Exception:continue
        krw=_to_krw(amt,cur,fx)
        if not krw:continue
        rows.append({'source':'eBay','source_id':'ebay','title':str(x.get('title') or '')[:240],'url':str(x.get('itemWebUrl') or '')[:800],
                     'price_krw':krw,'price_native':amt,'currency':cur,'price_kind':'판매중','verified_api':True,'date':''})
    return rows

def _learning():
    d=_safe_json(LEARNING,{})
    return d if isinstance(d,dict) else {}

def _health(source_id,learn):
    s=(learn.get('sources') or {}).get(source_id,{})
    runs=max(1,int(s.get('runs') or 0));hits=int(s.get('hits') or 0);errors=int(s.get('errors') or 0)
    return max(.75,min(1.15,0.90+(hits/runs)*.18-(errors/runs)*.12))

def _save_learning(stats):
    old=_learning();src=old.setdefault('sources',{})
    for sid,x in stats.items():
        row=src.setdefault(sid,{'runs':0,'hits':0,'errors':0})
        row['runs']=int(row.get('runs',0))+1;row['hits']=int(row.get('hits',0))+int(x.get('hits',0));row['errors']=int(row.get('errors',0))+int(x.get('error',0));row['last_at']=datetime.now(timezone.utc).isoformat(timespec='seconds')
    old['updated_at']=datetime.now(timezone.utc).isoformat(timespec='seconds');_atomic(LEARNING,old)

def _cache_key(query,region,game):return re.sub(r'\s+',' ',f'{query}|{region}|{game}').strip().lower()

def _cached(key):
    d=_safe_json(CACHE,{})
    row=(d.get('items') or {}).get(key) if isinstance(d,dict) else None
    if isinstance(row,dict) and time.time()-float(row.get('_epoch',0))<CACHE_TTL:return row
    return None

def _save_cache(key,data):
    d=_safe_json(CACHE,{})
    if not isinstance(d,dict):d={}
    items=d.setdefault('items',{});items[key]=data
    # bounded cache
    if len(items)>80:
        for k,_ in sorted(items.items(),key=lambda kv:float(kv[1].get('_epoch',0)))[:-60]:items.pop(k,None)
    _atomic(CACHE,d)

def search_multi_market(query,region='ALL',game='ALL',force=False):
    query=re.sub(r'[\x00-\x1f\x7f]',' ',str(query or '')).strip()[:160]
    region=str(region or 'ALL').upper();game=str(game or 'ALL')[:40]
    if not query:return {'ok':False,'error':'검색어가 필요합니다.','items':[]}
    key=_cache_key(query,region,game)
    if not force:
        c=_cached(key)
        if c:return {**c,'cache':'hit'}
    fx=_fx();learn=_learning();items=[];stats={};errors=[]
    # eBay API first when configured; RSS discovery remains as fallback/extra coverage.
    try:
        api_rows=_ebay_api(query,region,fx);items.extend(api_rows);stats['ebay']={'hits':len(api_rows),'error':0}
    except Exception as e:
        stats['ebay']={'hits':0,'error':1};errors.append('eBay API:'+type(e).__name__)
    for src in SOURCES:
        sid=src['id'];stats.setdefault(sid,{'hits':0,'error':0})
        q=f'site:{src["domain"]} {query}'
        if game not in ('ALL',''):q+=' '+game
        try:rows=_rss(q,6)
        except Exception as e:
            stats[sid]['error']=1;errors.append(src['name']+':'+type(e).__name__);continue
        seen=0
        for r in rows:
            host=(urlparse(r['url']).hostname or '').lower()
            if src['domain'] not in host:continue
            p=_extract_price(r['title']+' '+r['snippet'],fx)
            if not p:continue
            blob=(r['title']+' '+r['snippet']).lower();kind='실거래/완료 신호' if any(w in blob for w in SOLD_WORDS) else src['kind']
            weight=float(src['weight'])*_health(sid,learn)*(1.08 if kind=='실거래/완료 신호' else 1.0)
            items.append({'source':src['name'],'source_id':sid,'title':r['title'],'url':r['url'],'snippet':r['snippet'],'date':r['date'],
                          **p,'price_kind':kind,'verified_api':False,'score':round(weight,3)})
            seen+=1
        stats[sid]['hits']+=seen
    # Dedupe URL + near-identical title/price.
    dedup={}
    for x in items:
        url=x.get('url') or '';title=re.sub(r'\W+','',str(x.get('title') or '').lower())[:80];bucket=int(x.get('price_krw',0)//1000)
        k=url or f'{x.get("source_id")}|{title}|{bucket}'
        old=dedup.get(k)
        if not old or float(x.get('score',1))>float(old.get('score',1)):dedup[k]=x
    items=list(dedup.values());items.sort(key=lambda x:(-float(x.get('score',1)),-int(x.get('price_krw',0))))
    prices=[int(x['price_krw']) for x in items if int(x.get('price_krw',0))>0]
    summary={'count':len(prices),'median_krw':int(statistics.median(prices)) if prices else 0,'min_krw':min(prices) if prices else 0,'max_krw':max(prices) if prices else 0,
             'source_count':len({x.get('source_id') for x in items})}
    data={'ok':True,'query':query,'region':region,'game':game,'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'refresh_minutes':15,
          'summary':summary,'items':items[:60],'errors':errors,'source_stats':stats,
          'notice':'여러 공개 마켓/검색결과를 교차수집합니다. 판매중 가격과 실거래 신호를 구분하며, 로그인·비공개 API를 우회하지 않습니다. 최종 거래가는 원문에서 확인하세요.',
          '_epoch':time.time(),'cache':'refresh'}
    _save_learning(stats);_save_cache(key,data);return data

if __name__=='__main__':
    import sys
    print(json.dumps(search_multi_market(' '.join(sys.argv[1:]) or '피카츄',force=True),ensure_ascii=False,indent=2))
