#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urljoin
from urllib.request import Request
from xml.etree import ElementTree as ET
from html import unescape
import json, os, re

from safe_runtime import safe_urlopen

BASE=Path(__file__).resolve().parent
OUT=BASE/'box_hit_market_candidates.json'
LEARNING=BASE/'box_hit_market_learning.json'
UA='Mozilla/5.0 TCG-Grader/1.1'

SOURCES=[
 ('ebay','eBay','ebay.com',0.96),('amazon_us','Amazon US','amazon.com',0.74),('amazon_jp','Amazon JP','amazon.co.jp',0.77),
 ('kream','KREAM','kream.co.kr',0.93),('daangn','당근','daangn.com',0.78),('bunjang','번개장터','bunjang.co.kr',0.84),
 ('joongna','중고나라','joongna.com',0.82),('collectory','Collectory','collectory.cc',0.91),('tcgplayer','TCGplayer','tcgplayer.com',0.90),
 ('cardmarket','Cardmarket','cardmarket.com',0.87),('mercari_jp','Mercari JP','jp.mercari.com',0.85),('yahoo_jp','Yahoo Japan','auctions.yahoo.co.jp',0.83),
 ('snkrdunk','SNKRDUNK','snkrdunk.com',0.91),('justtcg','JustTCG','justtcg.com',0.91),
 ('tcgdex','TCGdex','tcgdex.net',0.89),('pavilion','Pavilion TCG','pavilion-tcg.com',0.90),
]
SOURCE_HOSTS={sid:domain for sid,_name,domain,_weight in SOURCES}
GAMES={
 'Pokémon':('pokemon','포켓몬','ポケモン'),
 'ONE PIECE':('one piece','원피스','ワンピース'),
 'NARUTO':('naruto','나루토'),
}
BOX_WORDS=('booster box','display box','sealed box',' booster ',' box ','박스','부스터팩','부스터 팩','box','ボックス','ブースター','팩 세트','box set')
HIT_WORDS=('sar','sr','sec','sp','manga','manga rare','parallel','promo','프로모','패러렐','시크릿','alt art','special art','illustration rare','bwr','ur','コミパラ','パラレル','leader parallel','gold card')
NEGATIVE=('sleeve','binder','deck box','storage box','case only','empty box','빈박스','박스만','보관함','플레이매트','proxy','custom','digital')
REGION_HINTS={'KR':('korean','korea','한국','한글판','kr '),'JP':('japanese','japan','일본','일판','jp ','日本','日版'),'US':('english','eng ','usa','us ','미국','영문판')}
REGION_TERMS={
 'KR':('korean','한국판','한글판'),
 'JP':('japanese','일본판','日版'),
 'US':('english','미국판','영문판'),
}


def _atomic(path,data):
    tmp=Path(str(path)+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def _rss(query,limit=12):
    url='https://www.bing.com/search?format=rss&q='+quote_plus(query)
    req=Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.8,ja;q=0.7'})
    with safe_urlopen(req,timeout=12,allowed_hosts={'www.bing.com','bing.com'}) as r:raw=r.read(1_500_000)
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
        return 'HIT' if re.search(r'\b(?:SAR|SEC|SP|SR|UR|BWR)\b|manga rare|parallel|promo|패러렐|프로모|コミパラ',text,re.I) else 'BOX'
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
    stop={'pokemon','one','piece','naruto','card','game','tcg','booster','box','sealed','official','japanese','korean','english','new'}
    return tuple(sorted(dict.fromkeys(w for w in words if w not in stop))[:12])

def _ebay_api(query):
    token=os.environ.get('EBAY_OAUTH_TOKEN','').strip()
    if not token:return []
    url='https://api.ebay.com/buy/browse/v1/item_summary/search?q='+quote_plus(query)+'&limit=50'
    req=Request(url,headers={'Authorization':'Bearer '+token,'X-EBAY-C-MARKETPLACE-ID':'EBAY_US','User-Agent':UA})
    with safe_urlopen(req,timeout=15,allowed_hosts={'api.ebay.com'}) as r:d=json.loads(r.read(2_000_000).decode('utf-8','ignore'))
    out=[]
    for x in d.get('itemSummaries') or []:
        image=((x.get('image') or {}).get('imageUrl') or '')
        out.append({'title':str(x.get('title') or '')[:260],'url':str(x.get('itemWebUrl') or '')[:900],'snippet':'','date':'',
                    'image_url':image if image.startswith('https://') else '','verified_api':True})
    return out

def _page_image(url,source_id):
    """Best-effort public product image recovery from ordinary metadata only."""
    if not url.startswith('https://'):return ''
    host=(urlparse(url).hostname or '').lower();expected=SOURCE_HOSTS.get(source_id,'')
    if host!=expected and not host.endswith('.'+expected):return ''
    try:
        req=Request(url,headers={'User-Agent':UA,'Accept-Language':'ko-KR,ko;q=0.8,en;q=0.7,ja;q=0.6'})
        with safe_urlopen(req,timeout=8,allowed_hosts={host,expected}) as r:
            ctype=(r.headers.get('Content-Type') or '').lower()
            if 'html' not in ctype:return ''
            raw=r.read(700_000).decode('utf-8','ignore')
    except Exception:return ''
    patterns=(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)',
    )
    for pat in patterns:
        m=re.search(pat,raw,re.I)
        if not m:continue
        candidate=unescape(m.group(1)).strip();candidate=urljoin(url,candidate)
        if not candidate.startswith('https://'):continue
        low=candidate.lower()
        if any(x in low for x in ('logo','icon','avatar','sprite','favicon','banner')):continue
        return candidate[:1200]
    return ''

def _queries(game,wanted):
    g='Pokemon' if game=='Pokémon' else game
    base=[]
    if wanted=='BOX':
        base=[f'{g} trading card booster box',f'{g} sealed booster box',f'{g} booster pack box']
        if game=='Pokémon':base += ['포켓몬 카드 박스','ポケモンカード BOX']
        elif game=='ONE PIECE':base += ['원피스 카드 부스터 박스','ワンピースカード ブースターボックス']
        else:base += ['나루토 카드 박스','Naruto Card Game box set']
    else:
        base=[f'{g} card SAR SR SEC SP manga rare parallel promo',f'{g} chase card alt art promo',f'{g} rare card parallel']
        if game=='Pokémon':base += ['포켓몬 SAR SR 프로모 카드','ポケモン SAR SR プロモ']
        elif game=='ONE PIECE':base += ['원피스 만화 패러렐 프로모 카드','ワンピース コミパラ パラレル']
        else:base += ['나루토 희귀 프로모 카드','Naruto rare promo card']
    return list(dict.fromkeys(base))

def _source_supports_game(source_id,game):
    if source_id=='tcgdex':return game=='Pokémon'
    if source_id in ('justtcg','pavilion','snkrdunk'):return game in ('Pokémon','ONE PIECE')
    return True

def discover_market_catalog():
    raw=[];errors=[];source_stats=defaultdict(lambda:{'queries':0,'results':0,'accepted':0,'images':0,'errors':0})
    for game in GAMES:
        for wanted in ('BOX','HIT'):
            for base in _queries(game,wanted):
                try:
                    for r in _ebay_api(base):raw.append({**r,'source_id':'ebay','source':'eBay','weight':0.96,'query_asset':wanted})
                except Exception as e:errors.append('eBay API:'+type(e).__name__)
                for sid,name,domain,weight in SOURCES:
                    if not _source_supports_game(sid,game):continue
                    source_stats[sid]['queries']+=1
                    try:rows=_rss(f'site:{domain} {base}',12)
                    except Exception as e:
                        source_stats[sid]['errors']+=1;errors.append(name+':'+type(e).__name__);continue
                    source_stats[sid]['results']+=len(rows)
                    for r in rows:
                        host=(urlparse(r.get('url','')).hostname or '').lower()
                        if host!=domain and not host.endswith('.'+domain):continue
                        raw.append({**r,'source_id':sid,'source':name,'weight':weight,'query_asset':wanted})
    grouped={}
    for r in raw:
        blob=(r.get('title','')+' '+r.get('snippet','')).strip();game=_game(blob);asset=_asset(blob)
        if not game or not asset or asset!=r.get('query_asset'):continue
        name=_clean_name(r.get('title',''),game,asset);tokens=_key_tokens(name)
        if len(tokens)<1:continue
        region=_region(blob,r.get('source_id',''))
        key=(region,game,asset,tokens)
        rec=grouped.setdefault(key,{'country':region,'game':game,'asset':asset,'name':name,'sources':{},'urls':[], 'images':[], 'score':0.0})
        sid=r.get('source_id');rec['sources'][sid]=r.get('source');rec['score']+=float(r.get('weight') or 0)
        if r.get('url') and r['url'] not in rec['urls']:rec['urls'].append(r['url'])
        if r.get('image_url','').startswith('https://') and r['image_url'] not in rec['images']:
            rec['images'].append(r['image_url']);source_stats[sid]['images']+=1
        source_stats[sid]['accepted']+=1
    # Recover a bounded number of missing images from public product metadata.
    image_budget=36
    for rec in sorted(grouped.values(),key=lambda x:-len(x['sources'])):
        if rec['images'] or image_budget<=0:continue
        for u in rec['urls'][:3]:
            host=(urlparse(u).hostname or '').lower();sid=next((s for s,d in SOURCE_HOSTS.items() if host==d or host.endswith('.'+d)),'')
            if not sid:continue
            img=_page_image(u,sid)
            if img:
                rec['images'].append(img);source_stats[sid]['images']+=1;image_budget-=1;break
    candidates=[]
    for rec in grouped.values():
        source_count=len(rec['sources']);verified_image=bool(rec['images'])
        promoted=source_count>=2 or (verified_image and 'ebay' in rec['sources'])
        rec['source_count']=source_count;rec['promoted']=promoted;rec['image_url']=rec['images'][0] if rec['images'] else ''
        rec['source_names']=list(rec['sources'].values());rec['source_urls']=rec.pop('urls')[:8];rec.pop('images',None);rec.pop('sources',None)
        rec['score']=round(rec['score'],3);candidates.append(rec)
    candidates.sort(key=lambda x:(not x['promoted'],-x['source_count'],-bool(x['image_url']),-x['score']))
    payload={'version':2,'updated_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'candidates':candidates[:260],
             'summary':{'total':len(candidates),'promoted':sum(1 for x in candidates if x['promoted']),'with_image':sum(1 for x in candidates if x['image_url']),
                        'source_count':len([x for x in source_stats if source_stats[x]['results']])},'source_stats':dict(source_stats),'errors':errors[:60],
             'notice':'공개 검색결과와 공식 API/공개 상품 메타데이터만 사용합니다. 2개 이상 독립 출처 또는 eBay API 이미지 근거가 있는 후보만 카탈로그 승격 대상으로 표시합니다.'}
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
