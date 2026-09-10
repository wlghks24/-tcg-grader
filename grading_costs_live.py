#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timezone
from copy import deepcopy
from html import unescape
from pathlib import Path
import json,re,time,urllib.request

from safe_runtime import atomic_write_json, safe_read_text, safe_urlopen

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'grading_costs_cache.json'
WATCH=ROOT/'grading_company_updates.json'
CACHE_TTL=6*60*60
UA='Mozilla/5.0 TCG-Grader/1.1'
ALLOWED_HOSTS={
 'www.psacard.com','psacard.com','www.beckett.com','beckett.com',
 'www.cgccards.com','cgccards.com','taggrading.com','www.taggrading.com',
 'break.co.kr','www.break.co.kr',
}
PREFERRED_MARKET={'PSA':'US','BGS':'US','CGC':'US','TAG':'US','BRG':'KR'}

# Last-known official baselines are fail-safe fallbacks only. The scheduled official
# watcher can overlay verified changes without mutating source code.
COMPANIES={
 'PSA':{
  'source':'https://www.psacard.com/services/tradingcardgrading','currency':'USD','shipping':'checkout_calculated','insurance':'tier_max_insured_value',
  'services':[{'name':'Regular','fee':79.99,'max_insured_value':1500},{'name':'Express','fee':149.00,'max_insured_value':2500},{'name':'Super Express','fee':349.00,'max_insured_value':5000},{'name':'Walk-Through','fee':599.00,'max_insured_value':10000},{'name':'Premium +','fee':999.00,'max_insured_value':25000}],
 },
 'BGS':{
  'source':'https://www.beckett.com/grading','currency':'USD','shipping':'checkout_calculated','insurance':'return_shipping_and_insurance_variable',
  'services':[{'name':'Base','fee':14.95,'availability':'paused'},{'name':'Base + Subgrades','fee':17.95,'availability':'paused'},{'name':'Standard','fee':34.95,'availability':'paused'},{'name':'Express','fee':79.95,'availability':'open'},{'name':'Priority','fee':124.95,'availability':'open'}],
 },
 'CGC':{
  'source':'https://www.cgccards.com/submit/services-fees/cgc-grading/?view=cards','currency':'USD','shipping':'checkout_calculated','insurance':'declared_value_tier',
  'services':[{'name':'Bulk','fee':17.00,'min_cards':25,'max_value':500},{'name':'Economy','fee':20.00,'max_value':1000},{'name':'Standard','fee':55.00,'max_value':3000},{'name':'Express','fee':100.00,'max_value':10000},{'name':'WalkThrough','fee':300.00,'max_value':100000}],
 },
 'TAG':{
  'source':'https://taggrading.com/pages/pricing','currency':'USD','shipping':'return_shipping_flat_at_checkout','insurance':'included_by_tier',
  'services':[{'name':'Basic','fee':22.00,'min_cards':10,'insurance_per_card':300},{'name':'Standard','fee':39.00,'insurance_per_card':500},{'name':'Express','fee':59.00,'insurance_per_card':1000},{'name':'Priority','fee':149.00,'insurance_per_card':2500},{'name':'Walkthrough','fee':299.00,'insurance_per_card':5000}],
  'extras':[{'name':'Submission Kit','fee':49.95,'currency':'USD','coverage_order':1000,'region':'US only'},{'name':'Return Shipping Insurance','fee':14.99,'currency':'USD','coverage_order':1000}],
 },
 'BRG':{
  'source':'https://break.co.kr/','currency':'KRW','shipping':'domestic_carrier_actual','insurance':'carrier_actual',
  'services':[{'name':'Regular','fee':19800},{'name':'Express','fee':39800},{'name':'Bulk','fee':13800,'min_cards':20},{'name':'Reholder','fee':9800},{'name':'BRG GEN','fee':9800}],
  'extras':[{'name':'오토 등급','fee':3000,'currency':'KRW'}],
 },
}

def _text(html:str)->str:
    html=re.sub(r'(?is)<script.*?</script>|<style.*?</style>',' ',html)
    html=re.sub(r'(?s)<[^>]+>',' ',html)
    return re.sub(r'\s+',' ',unescape(html)).strip()

def _fetch(url:str)->str:
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept-Language':'en-US,en;q=0.8,ko;q=0.6'})
    with safe_urlopen(req,timeout=12,allowed_hosts=ALLOWED_HOSTS,max_redirects=2) as r:
        return _text(r.read(2_000_000).decode('utf-8','ignore'))

def _near_price(text,name,currency):
    # Search a short window after the service label; accept only plausible official prices.
    m=re.search(re.escape(name)+r'.{0,260}',text,re.I)
    if not m:return None
    win=m.group(0)
    if currency=='KRW':
        vals=[int(v.replace(',','')) for v in re.findall(r'([0-9]{1,3}(?:,[0-9]{3})+)\s*원',win)]
        return next((v for v in vals if 3000<=v<=5000000),None)
    if currency=='JPY':
        vals=[int(v.replace(',','')) for v in re.findall(r'[￥¥]\s*([0-9][0-9,]*)',win)]
        return next((v for v in vals if 500<=v<=20000000),None)
    vals=[float(v.replace(',','')) for v in re.findall(r'\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',win)]
    return next((v for v in vals if 5<=v<=50000),None)

def _refresh_company(name,cfg):
    out=deepcopy(cfg); out['source_ok']=False; out['live_updates']=0
    try:text=_fetch(cfg['source'])
    except Exception as e:
        out['source_error']=type(e).__name__;return out
    out['source_ok']=True
    for svc in out.get('services',[]):
        p=_near_price(text,svc['name'],cfg['currency'])
        if p is not None and abs(float(p)-float(svc['fee']))/max(float(svc['fee']),1)<5:
            svc['fee']=p;svc['live_verified']=True;out['live_updates']+=1
    if name=='BGS':
        low=text.lower()
        if 'temporarily paused' in low or 'sold out' in low:
            for svc in out['services']:
                if svc['name'] in ('Base','Base + Subgrades','Standard'):svc['availability']='paused'
    return out

def _watch_signature():
    try:
        st=WATCH.stat();return f'{st.st_mtime_ns}:{st.st_size}'
    except OSError:return 'missing'

def _load_watch():
    try:
        data=json.loads(safe_read_text(WATCH,max_bytes=8_000_000))
        if not isinstance(data,dict) or not data.get('policy',{}).get('official_sources_only'):return {}
        return data
    except (OSError,ValueError,TypeError,UnicodeError,json.JSONDecodeError):return {}

def _merge_watch(companies,watch):
    if not watch:return
    watched=watch.get('companies',{}) if isinstance(watch.get('companies'),dict) else {}
    changes=watch.get('history',[]) if isinstance(watch.get('history'),list) else []
    for name,out in companies.items():
        company=watched.get(name,{}) if isinstance(watched.get(name),dict) else {}
        markets=company.get('markets',{}) if isinstance(company.get('markets'),dict) else {}
        out['regional_markets']=deepcopy(markets)
        preferred=PREFERRED_MARKET.get(name)
        market=markets.get(preferred,{}) if isinstance(markets.get(preferred),dict) else {}
        rows=market.get('services',[]) if isinstance(market.get('services'),list) else []
        by_name={str(s.get('name')):s for s in out.get('services',[]) if isinstance(s,dict) and s.get('name')}
        for observed in rows:
            if not isinstance(observed,dict) or not observed.get('verified_official_source') or not observed.get('name'):continue
            key=str(observed['name']);target=by_name.get(key)
            if target is None:
                target={'name':key};out.setdefault('services',[]).append(target);by_name[key]=target
            for field in ('fee','turnaround_business_days','max_declared_or_insured_value','availability'):
                if field in observed:target[field]=observed[field]
            target['live_verified']=True;target['watch_source']=observed.get('source')
        # Only an explicit verified removal record can retire a fallback service.
        removed={str(c.get('service')) for c in changes if isinstance(c,dict) and c.get('company')==name and c.get('type')=='service_removed' and c.get('verified_official_source')}
        for svc in out.get('services',[]):
            if str(svc.get('name')) in removed:svc['availability']='retired'
        out['watch_source_health']=deepcopy(company.get('source_health',[]))

def _load_cache():
    try:
        d=json.loads(safe_read_text(CACHE,max_bytes=4_000_000))
        if d.get('_watch_signature')!=_watch_signature():return None
        if time.time()-float(d.get('_epoch',0))<CACHE_TTL:return d
    except (OSError,ValueError,TypeError,UnicodeError,json.JSONDecodeError):pass
    return None

def _save_cache(data):
    try:atomic_write_json(CACHE,data,suffix='.grading-costs.tmp')
    except (OSError,ValueError,TypeError):pass

def get_grading_costs(force:bool=False):
    if not force:
        cached=_load_cache()
        if cached:
            cached['cache']='hit';return cached
    companies={k:_refresh_company(k,v) for k,v in COMPANIES.items()}
    watch=_load_watch();_merge_watch(companies,watch)
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    data={
        'ok':True,'checked_at':now,'refresh_hours':6,'companies':companies,
        'watch_checked_at':watch.get('checked_at') if watch else None,
        'recent_changes':deepcopy(watch.get('recent_changes',[])) if watch else [],
        'grading_events':deepcopy(watch.get('announcements',[])) if watch else [],
        'watch_summary':deepcopy(watch.get('summary',{})) if watch else {},
        'notice':'공식 업체 페이지를 주기적으로 확인하며, 가격·서비스명·예상 납기·접수중지/재개·공식 이벤트 변경을 별도 이력으로 검증합니다. 공식 파싱 실패 시 마지막 검증값을 유지하고 커뮤니티/인스타 게시물만으로는 자동 변경하지 않습니다. 배송비와 일부 보험료는 실제 체크아웃/택배사 값을 사용합니다.',
        '_epoch':time.time(),'_watch_signature':_watch_signature(),'cache':'refresh',
    }
    _save_cache(data);return data
