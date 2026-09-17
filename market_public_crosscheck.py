#!/usr/bin/env python3
"""Public market cross-checks for Collectory and KREAM.

Uses only public HTML pages; no login, private API, anti-bot bypass, or account data.
Collected values are reference cross-checks. They never overwrite the primary
verified price unless a caller explicitly chooses to do so.

Performance policy:
- at most one in-flight request per source host;
- different source hosts may run concurrently;
- short-lived observations are reused to absorb duplicate/manual trigger storms;
- each source has a bounded wall-clock budget and unfinished work is deferred;
- latency/cache/load-shed metrics are emitted so optimizations can be measured.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import http.client
import json
import re
import time
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
SOURCE_ORDER=('Collectory','KREAM')
# HTTP protocol failures (including IncompleteRead) are source-level network failures.
# Never use partial bodies as verified prices; preserve the previous observation and
# continue checking the remaining public sources instead of aborting market_prices.
NETWORK_ERRORS=(urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, ValueError, http.client.HTTPException)
HEADERS={'User-Agent':'TCG-Grader-Public-Market-Crosscheck/1.1'}


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


def _parse_time(value)->dt.datetime|None:
    text=str(value or '').strip()
    if not text:return None
    try:parsed=dt.datetime.fromisoformat(text.replace('Z','+00:00'))
    except (TypeError,ValueError):return None
    if parsed.tzinfo is None:parsed=parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _fresh_observation(observation:dict|None, now:dt.datetime, ttl_seconds:int)->bool:
    if not isinstance(observation,dict):return False
    stamped=_parse_time(observation.get('observed_at'))
    if stamped is None:return False
    age=(now-stamped).total_seconds()
    # Future timestamps beyond a small clock-skew window are never trusted as cache hits.
    return -300 <= age <= ttl_seconds


def _percentile_ms(values:list[float], q:float)->float:
    if not values:return 0.0
    ordered=sorted(max(0.0,float(v)) for v in values)
    index=int(round((len(ordered)-1)*max(0.0,min(1.0,q))))
    return round(ordered[index],3)


def _run_source_batch(source:str, jobs:list[tuple[dict,str,str]], fetcher:Callable[[str],str],
                      observed_at:str, budget_seconds:int)->dict:
    """Run one source serially with a wall-clock budget and defer overflow safely."""
    parser=parse_collectory if source=='Collectory' else parse_kream
    began=time.monotonic()
    observations=[];errors=[];latencies=[];processed=0
    for index,(row,term,url) in enumerate(jobs):
        # Never start another external request once this provider's budget is spent.
        # The current request remains bounded by its own HTTP timeout; unfinished rows
        # are retried by the rotating cursor on a later collection cycle.
        if index and time.monotonic()-began >= budget_seconds:
            break
        request_started=time.monotonic()
        try:
            text=html_to_text(fetcher(url))
            result=parser(text,row,url)
            if result:
                result['observed_at']=observed_at;result['query']=term
                observations.append((row['key'],result))
        except NETWORK_ERRORS as exc:
            errors.append(f'{source}:{row["key"]}:{type(exc).__name__}')
        finally:
            processed+=1
            latencies.append((time.monotonic()-request_started)*1000.0)
    duration_ms=(time.monotonic()-began)*1000.0
    deferred=max(0,len(jobs)-processed)
    return {
        'source':source,'checked':processed,'matched':len(observations),'errors':errors,
        'observations':observations,'latencies_ms':latencies,'duration_ms':round(duration_ms,3),
        'deferred':deferred,'budget_seconds':budget_seconds,'budget_exhausted':deferred>0,
    }


def crosscheck_market_db(db:dict, fetcher:Callable[[str],str]|None=None)->dict:
    fetcher=fetcher or _public_fetch
    rows=_query_rows(db)
    cap=env_int('TCG_MARKET_CROSSCHECK_QUERIES',4,1,20)
    cache_ttl=env_int('TCG_MARKET_CROSSCHECK_CACHE_SECONDS',900,60,3600)
    source_workers=env_int('TCG_MARKET_CROSSCHECK_SOURCE_WORKERS',2,1,len(SOURCE_ORDER))
    source_budget=env_int('TCG_MARKET_CROSSCHECK_SOURCE_BUDGET_SECONDS',90,15,240)
    state=_load_json(STATE,{'cursor':0})
    cursor=max(0,int(state.get('cursor') or 0))
    if rows:
        chosen=[rows[(cursor+i)%len(rows)] for i in range(min(cap,len(rows)))]
    else:chosen=[]
    now_dt=dt.datetime.now(dt.timezone.utc)
    now=now_dt.isoformat(timespec='seconds')
    started=time.monotonic()

    previous_by_key={}
    jobs_by_source={source:[] for source in SOURCE_ORDER}
    source_stats={source:{'checked':0,'matched':0,'errors':0,'cache_hits':0,'duration_ms':0.0,
                          'request_p50_ms':0.0,'request_p95_ms':0.0,'request_max_ms':0.0,
                          'deferred':0,'budget_seconds':source_budget,'budget_exhausted':False}
                  for source in SOURCE_ORDER}
    cache_hits=0

    for row in chosen:
        term=_search_term(row)
        entry=db.setdefault('entries',{}).setdefault(row['key'],{})
        previous={x.get('source'):x for x in entry.get('source_crosschecks',[])
                  if isinstance(x,dict) and x.get('source')}
        previous_by_key[row['key']]=previous
        if len(norm(term))<2:continue
        urls=_urls(term)
        for source in SOURCE_ORDER:
            prior=previous.get(source)
            if _fresh_observation(prior,now_dt,cache_ttl):
                source_stats[source]['cache_hits']+=1;cache_hits+=1
                continue
            jobs_by_source[source].append((row,term,urls[source]))

    # One serial worker per source gives cross-host concurrency without ever sending
    # concurrent requests to the same provider. Each worker also has a wall-clock
    # budget so high fan-out cannot consume the whole parent collection deadline.
    source_results={}
    active_sources=[source for source in SOURCE_ORDER if jobs_by_source[source]]
    if source_workers == 1 or len(active_sources) <= 1:
        for source in active_sources:
            source_results[source]=_run_source_batch(source,jobs_by_source[source],fetcher,now,source_budget)
    else:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(source_workers,len(active_sources)),thread_name_prefix='market-crosscheck'
        ) as pool:
            futures={pool.submit(_run_source_batch,source,jobs_by_source[source],fetcher,now,source_budget):source
                     for source in active_sources}
            for future in concurrent.futures.as_completed(futures):
                source=futures[future]
                source_results[source]=future.result()

    errors=[];matched=0;checked=0;all_latencies=[];deferred=0
    for source in SOURCE_ORDER:
        result=source_results.get(source)
        if not result:continue
        latencies=result['latencies_ms'];all_latencies.extend(latencies)
        checked+=result['checked'];matched+=result['matched'];errors.extend(result['errors'])
        deferred+=result['deferred']
        source_stats[source].update({
            'checked':result['checked'],'matched':result['matched'],'errors':len(result['errors']),
            'duration_ms':result['duration_ms'],'request_p50_ms':_percentile_ms(latencies,.50),
            'request_p95_ms':_percentile_ms(latencies,.95),
            'request_max_ms':round(max(latencies),3) if latencies else 0.0,
            'deferred':result['deferred'],'budget_seconds':result['budget_seconds'],
            'budget_exhausted':result['budget_exhausted'],
        })
        for key,observation in result['observations']:
            previous_by_key.setdefault(key,{})[source]=observation

    for row in chosen:
        entry=db.setdefault('entries',{}).setdefault(row['key'],{})
        checks=list(previous_by_key.get(row['key'],{}).values())
        checks.sort(key=lambda x:(x.get('source',''),-float(x.get('confidence') or 0)))
        if checks:entry['source_crosschecks']=checks

    # If a provider exhausted its budget, advance only past the prefix that every
    # active provider had a chance to process. This keeps deferred rows near the
    # front of the next cycle instead of starving them for a full cursor rotation.
    max_deferred=max((int(result.get('deferred') or 0) for result in source_results.values()),default=0)
    advance=max(1,len(chosen)-max_deferred) if chosen else 0
    next_cursor=(cursor+advance)%max(1,len(rows))
    state={'cursor':next_cursor,'updated_at':now,'total_targets':len(rows),
           'last_advance':advance,'last_deferred_requests':deferred}
    atomic_write_json(STATE,state,suffix='.crosscheck.tmp')
    duration_ms=(time.monotonic()-started)*1000.0
    potential_requests=sum(1 for row in chosen if len(norm(_search_term(row)))>=2)*len(SOURCE_ORDER)
    summary={'updated_at':now,'targets_total':len(rows),'targets_checked':len(chosen),'requests_checked':checked,
             'matches':matched,'sources':source_stats,'errors':errors[:50],
             'duration_ms':round(duration_ms,3),'request_p50_ms':_percentile_ms(all_latencies,.50),
             'request_p95_ms':_percentile_ms(all_latencies,.95),
             'request_max_ms':round(max(all_latencies),3) if all_latencies else 0.0,
             'cache_hits':cache_hits,'cache_ttl_seconds':cache_ttl,
             'external_requests_saved':max(0,potential_requests-checked-deferred),
             'requests_deferred':deferred,'source_budget_seconds':source_budget,
             'cursor_advance':advance,
             'source_workers':min(source_workers,max(1,len(active_sources))) if active_sources else 0,
             'worker_policy':'max-one-inflight-request-per-source + bounded-source-budget',
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
