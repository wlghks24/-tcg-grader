#!/usr/bin/env python3
"""Public market cross-checks for Collectory and KREAM.

Uses only public HTML pages; no login, private API, anti-bot bypass, or account data.
Collected values are reference cross-checks. They never overwrite the primary
verified price unless a caller explicitly chooses to do so.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from safe_runtime import atomic_write_json, env_int, html_to_text, safe_read_text, safe_urlopen

ROOT=Path(__file__).resolve().parent
WATCH=ROOT/'market_watch.json'
STATE=ROOT/'market_public_crosscheck_state.json'
ALLOWED={'collectory.cc','www.collectory.cc','kream.co.kr','www.kream.co.kr'}
NETWORK_ERRORS=(urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, ValueError)
HEADERS={'User-Agent':'TCG-Grader-Public-Market-Crosscheck/1.0'}


def norm(value:str)->str:
    value=unicodedata.normalize('NFKC',str(value or '')).lower()
    return re.sub(r'[^0-9a-z가-힣]+','',value)


def _load_json(path:Path, default):
    try:
        return json.loads(safe_read_text(path))
    except (OSError,ValueError,TypeError):
        return default


def _public_fetch(url:str)->str:
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' or (parsed.hostname or '').lower() not in ALLOWED:
        raise ValueError('허용되지 않은 공개 시세 출처')
    req=urllib.request.Request(url,headers=HEADERS)
    with safe_urlopen(req,timeout=env_int('TCG_MARKET_CROSSCHECK_TIMEOUT',12,5,30),allowed_hosts=ALLOWED) as r:
        return r.read(2_000_000).decode('utf-8','replace')


def _price_to_krw(token:str)->int|None:
    if not token:return None
    m=re.search(r'(?:₩\s*|)([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})\s*원?',token)
    if not m:return None
    try:return int(m.group(1).replace(',',''))
    except ValueError:return None


def _query_rows(db:dict)->list[dict]:
    rows=[];seen=set()
    # Existing market entries first: they are the cards/products the UI already knows.
    for key,val in (db.get('entries') or {}).items():
        if not isinstance(val,dict):continue
        region=(str(key).split('|',1)[0] if '|' in str(key) else '')
        row={
            'key':str(key),'region':region,'game':val.get('game',''),
            'card_name':val.get('card_name',''),'card_number':val.get('card_number',''),
            'product_name':val.get('product_name',''),'product_code':val.get('product_code',''),
            'name':str(key).split('|')[1] if '|' in str(key) else str(key),
        }
        ident=(row['key'],row['card_number'],row['product_code'])
        if ident not in seen:rows.append(row);seen.add(ident)
    watch=_load_json(WATCH,{'items':[]})
    for item in watch.get('items',[]):
        if not isinstance(item,dict):continue
        key=f"{item.get('region','')}|{item.get('name','')}|{item.get('asset','')}"
        row={
            'key':key,'region':item.get('region',''),'game':item.get('game',''),
            'card_name':item.get('card_name',''),'card_number':item.get('card_number',''),
            'product_name':item.get('native') or item.get('name',''),
            'product_code':item.get('product_code',''),'name':item.get('name',''),
        }
        ident=(row['key'],row['card_number'],row['product_code'])
        if ident not in seen:rows.append(row);seen.add(ident)
    # Prefer exact identifiers, then shorter stable names.
    rows.sort(key=lambda x:(0 if x['card_number'] else 1 if x['product_code'] else 2, len(x.get('name') or '')))
    return rows


def _search_term(row:dict)->str:
    if row.get('card_number'):
        return ' '.join(x for x in (row.get('card_name'),row.get('card_number')) if x).strip()
    if row.get('product_code'):
        return ' '.join(x for x in (row.get('product_code'),row.get('name')) if x).strip()
    return str(row.get('card_name') or row.get('name') or row.get('product_name') or '').strip()


def _anchor(row:dict)->tuple[str,str]:
    for field in ('card_number','product_code','card_name','name'):
        v=str(row.get(field) or '').strip()
        if v:return field,v
    return 'name',''


def _match_confidence(text:str,row:dict)->tuple[float,str]:
    raw=unicodedata.normalize('NFKC',text or '')
    card_number=str(row.get('card_number') or '').strip()
    product_code=str(row.get('product_code') or '').strip()
    card_name=str(row.get('card_name') or '').strip()
    name=str(row.get('name') or '').strip()
    if card_number and card_number.lower() in raw.lower():
        if card_name and norm(card_name) in norm(raw):return .99,'card_number+card_name'
        return .97,'card_number'
    if product_code and product_code.lower() in raw.lower():
        if name and norm(name) in norm(raw):return .96,'product_code+name'
        return .92,'product_code'
    target=norm(card_name or name)
    if len(target)>=5 and target in norm(raw):return .82,'name'
    return 0.0,'none'


def _window(text:str,row:dict, radius:int=260)->str:
    field,anchor=_anchor(row)
    if not anchor:return text[:radius*2]
    low=text.lower();needle=anchor.lower();i=low.find(needle)
    if i<0:return text[:radius*2]
    return text[max(0,i-radius):min(len(text),i+len(anchor)+radius)]


def parse_collectory(text:str,row:dict,url:str)->dict|None:
    confidence,matched_by=_match_confidence(text,row)
    if confidence<.80:return None
    win=_window(text,row,360)
    prices=re.findall(r'₩\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})',win)
    if not prices:
        prices=re.findall(r'([0-9]{1,3}(?:,[0-9]{3})+)\s*원',win)
    if not prices:return None
    raw=int(prices[0].replace(',',''))
    grade=None
    gm=re.search(r'🏅\s*(10|9|8|7|6|5|4|3|2|1)',win)
    if gm:grade=int(gm.group(1))
    return {'source':'Collectory','price_krw':raw,'display':f'₩{raw:,}','grade_hint':grade,
            'confidence':confidence,'matched_by':matched_by,'url':url,'excerpt':re.sub(r'\s+',' ',win)[:500]}


def parse_kream(text:str,row:dict,url:str)->dict|None:
    confidence,matched_by=_match_confidence(text,row)
    if confidence<.80:return None
    win=_window(text,row,420)
    # KREAM search/product pages normally expose prices as 123,000원 (or ₩123,000).
    vals=[]
    for pat in (r'₩\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{4,})',r'([0-9]{1,3}(?:,[0-9]{3})+)\s*원'):
        vals += [int(x.replace(',','')) for x in re.findall(pat,win)]
    vals=[v for v in vals if 100<=v<=500_000_000]
    if not vals:return None
    trades=None
    tm=re.search(r'거래\s*([0-9,]+)',win)
    if tm:
        try:trades=int(tm.group(1).replace(',',''))
        except ValueError:trades=None
    return {'source':'KREAM','price_krw':vals[0],'display':f'₩{vals[0]:,}','trades':trades,
            'confidence':confidence,'matched_by':matched_by,'url':url,'excerpt':re.sub(r'\s+',' ',win)[:500]}


def _urls(term:str)->dict[str,str]:
    q=urllib.parse.quote_plus(term)
    return {
        'Collectory':f'https://collectory.cc/cards?search={q}',
        'KREAM':f'https://kream.co.kr/search?keyword={q}',
    }


def crosscheck_market_db(db:dict, fetcher:Callable[[str],str]|None=None)->dict:
    fetcher=fetcher or _public_fetch
    rows=_query_rows(db)
    cap=env_int('TCG_MARKET_CROSSCHECK_QUERIES',4,1,20)
    state=_load_json(STATE,{'cursor':0})
    cursor=max(0,int(state.get('cursor') or 0))
    if rows:
        chosen=[rows[(cursor+i)%len(rows)] for i in range(min(cap,len(rows)))]
    else:chosen=[]
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    errors=[];matched=0;checked=0
    source_stats={'Collectory':{'checked':0,'matched':0,'errors':0},'KREAM':{'checked':0,'matched':0,'errors':0}}
    for row in chosen:
        term=_search_term(row)
        if len(norm(term))<2:continue
        entry=db.setdefault('entries',{}).setdefault(row['key'],{})
        checks=[]
        # Preserve previous source observations when a source is temporarily inaccessible.
        previous={x.get('source'):x for x in entry.get('source_crosschecks',[]) if isinstance(x,dict) and x.get('source')}
        for source,url in _urls(term).items():
            parser=parse_collectory if source=='Collectory' else parse_kream
            checked+=1;source_stats[source]['checked']+=1
            try:
                text=html_to_text(fetcher(url))
                result=parser(text,row,url)
                if result:
                    result['observed_at']=now;result['query']=term
                    previous[source]=result;matched+=1;source_stats[source]['matched']+=1
            except NETWORK_ERRORS as exc:
                source_stats[source]['errors']+=1
                errors.append(f'{source}:{row["key"]}:{type(exc).__name__}')
        checks=list(previous.values())
        checks.sort(key=lambda x:(x.get('source',''),-float(x.get('confidence') or 0)))
        if checks:entry['source_crosschecks']=checks
    next_cursor=(cursor+len(chosen))%max(1,len(rows))
    state={'cursor':next_cursor,'updated_at':now,'total_targets':len(rows)}
    atomic_write_json(STATE,state,suffix='.crosscheck.tmp')
    summary={'updated_at':now,'targets_total':len(rows),'targets_checked':len(chosen),'requests_checked':checked,
             'matches':matched,'sources':source_stats,'errors':errors[:50],
             'policy':'공개 HTML 교차확인 · 로그인/비공개 API/우회 없음 · 단독값으로 주 시세 자동 덮어쓰기 금지'}
    db['public_market_crosscheck']=summary
    return summary


def self_test()->dict:
    row={'key':'KR|인페르노X|HIT','card_name':'메가리자몽X ex','card_number':'116/080','name':'메가리자몽X ex'}
    c='🇰🇷 메가리자몽X ex 116/080 MUR 현재 시세 ₩375,000 최저 ₩340,000 🏅10'
    k='Pokemon TCG 메가리자몽X ex 인페르노X 116/080 390,000원 관심 120 · 거래 45'
    a=parse_collectory(c,row,'https://collectory.cc/cards?search=x')
    b=parse_kream(k,row,'https://kream.co.kr/search?keyword=x')
    assert a and a['price_krw']==375000 and a['confidence']>=.97
    assert b and b['price_krw']==390000 and b['trades']==45 and b['confidence']>=.97
    assert parse_kream('전혀 다른 카드 10,000원',row,'https://kream.co.kr/search?keyword=x') is None
    return {'ok':True,'collectory':a['price_krw'],'kream':b['price_krw']}


if __name__=='__main__':
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='self-test':
        print(json.dumps(self_test(),ensure_ascii=False));raise SystemExit(0)
    print(json.dumps(self_test(),ensure_ascii=False))
