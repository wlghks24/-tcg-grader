#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timezone
from copy import deepcopy
from html import unescape
from pathlib import Path
import json,re,time,urllib.request

CACHE=Path(__file__).with_name('grading_costs_cache.json')
CACHE_TTL=6*60*60
UA='Mozilla/5.0 TCG-Grader/1.0'

# Official-source baseline verified 2026-08-29. Variable checkout shipping is never fabricated.
COMPANIES={
 'PSA':{
  'source':'https://www.psacard.com/submit','currency':'USD','shipping':'checkout_calculated','insurance':'tier_max_insured_value',
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
    with urllib.request.urlopen(req,timeout=12) as r:
        return _text(r.read(2_000_000).decode('utf-8','ignore'))

def _near_price(text,name,currency):
    # Search a short window after the service label; accept only plausible official prices.
    m=re.search(re.escape(name)+r'.{0,220}',text,re.I)
    if not m:return None
    win=m.group(0)
    if currency=='KRW':
        vals=[int(v.replace(',','')) for v in re.findall(r'([0-9]{1,3}(?:,[0-9]{3})+)\s*원',win)]
        return next((v for v in vals if 3000<=v<=500000),None)
    vals=[float(v.replace(',','')) for v in re.findall(r'\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',win)]
    return next((v for v in vals if 5<=v<=20000),None)

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
    # Detect temporary pause wording for BGS Base/Standard without inventing availability.
    if name=='BGS':
        low=text.lower()
        paused=('temporarily paused' in low or 'sold out' in low)
        if paused:
            for svc in out['services']:
                if svc['name'] in ('Base','Base + Subgrades','Standard'):svc['availability']='paused'
    return out

def _load_cache():
    try:
        d=json.loads(CACHE.read_text(encoding='utf-8'))
        if time.time()-float(d.get('_epoch',0))<CACHE_TTL:return d
    except Exception:pass
    return None

def _save_cache(data):
    try:
        tmp=CACHE.with_suffix('.json.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(CACHE)
    except Exception:pass

def get_grading_costs(force:bool=False):
    if not force:
        cached=_load_cache()
        if cached:
            cached['cache']='hit';return cached
    companies={k:_refresh_company(k,v) for k,v in COMPANIES.items()}
    now=datetime.now(timezone.utc).isoformat(timespec='seconds')
    data={'ok':True,'checked_at':now,'refresh_hours':6,'companies':companies,
          'notice':'공식 페이지를 최대 6시간 간격으로 다시 확인합니다. 파싱에 실패한 항목은 마지막 공식 검증값을 유지합니다. 국제/국내 배송비와 일부 보험료는 목적지·수량·신고가액에 따라 체크아웃/택배사에서 달라지므로 실제 결제값을 사용합니다.',
          '_epoch':time.time(),'cache':'refresh'}
    _save_cache(data);return data
