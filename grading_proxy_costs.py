#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
from datetime import datetime, timezone
from html import unescape
import json, os, re, time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

BASE=os.path.dirname(os.path.abspath(__file__))
CACHE=os.path.join(BASE,'grading_proxy_costs_cache.json')
REFRESH_SECONDS=6*60*60

# Publicly visible Korean submission/proxy services. Numeric values are only
# stored when the provider publicly exposes them. Dynamic/login quotes stay null.
BASELINE=[
 {"provider":"HOBBY KOREA","grader":"PSA","official_dealer":True,
  "source":"https://hobbykorea.com/GRADING","pricing_type":"total_service_price",
  "services":[{"name":"Regular","price_krw":160000},{"name":"Express","price_krw":300000},{"name":"Super Express","price_krw":700000},{"name":"Reholder","price_krw":27000}],
  "note":"PSA 공식 딜러. 공개 페이지 표시 원화가격. 고가카드 업차지/추가비용은 별도 확인."},
 {"provider":"TCAVOL 트카볼","grader":"BGS","official_dealer":False,
  "source":"https://tradingcardsvault.com/GradingConsignmentGuide","pricing_type":"total_service_price",
  "services":[{"name":"Base","price_krw":47000},{"name":"Standard","price_krw":79000},{"name":"Priority","price_krw":269000}],
  "extras":[{"name":"고급클리닝","price_krw":12000},{"name":"개인발송","price_krw":120000}],
  "note":"공개 등급대행 가이드 기준. 이벤트/접수상태에 따라 달라질 수 있음."},
 {"provider":"CARD LAB BUSAN","grader":"PSA","official_dealer":False,
  "source":"https://cardlabbusan.com/","pricing_type":"proxy_fee_plus_actual",
  "proxy_fee_from_krw":35000,"services":[],"note":"대행수수료 35,000원~ + 인증사/운임/보험 실비."},
 {"provider":"CARD LAB BUSAN","grader":"CGC","official_dealer":False,
  "source":"https://cardlabbusan.com/","pricing_type":"proxy_fee_plus_actual",
  "proxy_fee_from_krw":30000,"services":[],"note":"대행수수료 30,000원~ + 인증사/운임/보험 실비."},
 {"provider":"CARD LAB BUSAN","grader":"BRG","official_dealer":False,
  "source":"https://cardlabbusan.com/","pricing_type":"proxy_fee_plus_actual",
  "proxy_fee_from_krw":20000,"services":[],"note":"대행수수료 20,000원~ + 인증사/운임/보험 실비."},
 {"provider":"KADO","grader":"PSA","official_dealer":False,
  "source":"https://app.kado.trade/en/grading","pricing_type":"dynamic_quote","services":[],"note":"대행가격은 신청 화면에서 동적 견적. 반환 배송비 별도 안내."},
 {"provider":"KADO","grader":"BGS","official_dealer":False,
  "source":"https://app.kado.trade/en/grading","pricing_type":"dynamic_quote","services":[],"note":"지원 등급사 안내 확인. 공개 정적 금액은 확인되지 않아 실시간 견적 사용."},
 {"provider":"KADO","grader":"CGC","official_dealer":False,
  "source":"https://app.kado.trade/en/grading","pricing_type":"dynamic_quote","services":[],"note":"지원 등급사 안내 확인. 공개 정적 금액은 확인되지 않아 실시간 견적 사용."},
 {"provider":"TRAINERS","grader":"PSA","official_dealer":False,"source":"https://grading.trainers.kr/","pricing_type":"dynamic_quote","services":[],"note":"온라인/매장 접수 지원. 공개 정적 금액은 미확인."},
 {"provider":"TRAINERS","grader":"BGS","official_dealer":False,"source":"https://grading.trainers.kr/","pricing_type":"dynamic_quote","services":[],"note":"온라인/매장 접수 지원. 공개 정적 금액은 미확인."},
 {"provider":"TRAINERS","grader":"CGC","official_dealer":False,"source":"https://grading.trainers.kr/","pricing_type":"dynamic_quote","services":[],"note":"온라인/매장 접수 지원. 공개 정적 금액은 미확인."},
 {"provider":"TRAINERS","grader":"BRG","official_dealer":False,"source":"https://grading.trainers.kr/","pricing_type":"dynamic_quote","services":[],"note":"온라인/매장 접수 지원. 공개 정적 금액은 미확인."},
 {"provider":"JINSCA 카드랩","grader":"PSA","official_dealer":True,"source":"https://jinsca.com/shop/grade01.php?ca=1&type=1","pricing_type":"dynamic_quote","services":[],"extras":[{"name":"뽀각","price_krw":1000},{"name":"스캔","price_krw":2000}],"note":"PSA 신청 화면에서 카드별 등급비/택배비를 계산. 공개 화면에서 기본 티어 가격은 동적으로 산정."},
]

def _strip_html(raw:str)->str:
    raw=re.sub(r'(?is)<script.*?</script>|<style.*?</style>',' ',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return re.sub(r'\s+',' ',unescape(raw)).strip()

def _fetch(url:str)->str:
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 TCG-Grader/1.0','Accept-Language':'ko,en;q=0.8'})
    with urlopen(req,timeout=12) as r:
        return r.read(1_500_000).decode('utf-8','ignore')

def _clone():
    return json.loads(json.dumps(BASELINE,ensure_ascii=False))

def _refresh_public_prices(rows):
    errors=[]; refreshed=[]
    by={(x['provider'],x['grader']):x for x in rows}
    # Hobby Korea: page currently exposes these labels and prices as text.
    try:
        text=_strip_html(_fetch('https://hobbykorea.com/GRADING'))
        row=by.get(('HOBBY KOREA','PSA'))
        patterns={'Regular':r'레귤러\s*([0-9,]+)원','Express':r'익스프레스\s*([0-9,]+)원','Super Express':r'슈퍼\s*익스프레스\s*([0-9,]+)원','Reholder':r'리홀더\s*([0-9,]+)원'}
        changed=0
        for svc in row.get('services',[]):
            m=re.search(patterns.get(svc['name'],'$^'),text,re.I)
            if m:
                svc['price_krw']=int(m.group(1).replace(',',''));changed+=1
        row['live_verified']=changed>0;row['live_verified_count']=changed
        refreshed.append('HOBBY KOREA')
    except Exception as e: errors.append('HOBBY KOREA:'+type(e).__name__)
    # TCAVOL BGS guide public prices.
    try:
        text=_strip_html(_fetch('https://tradingcardsvault.com/GradingConsignmentGuide'))
        row=by.get(('TCAVOL 트카볼','BGS'))
        patterns={'Base':r'베이스\s*([0-9,]+)\s*Cash','Standard':r'스탠다드\s*([0-9,]+)\s*Cash','Priority':r'프리오리티\s*([0-9,]+)\s*Cash'}
        changed=0
        for svc in row.get('services',[]):
            m=re.search(patterns.get(svc['name'],'$^'),text,re.I)
            if m:
                svc['price_krw']=int(m.group(1).replace(',',''));changed+=1
        row['live_verified']=changed>0;row['live_verified_count']=changed
        refreshed.append('TCAVOL 트카볼')
    except Exception as e: errors.append('TCAVOL:'+type(e).__name__)
    # Card Lab Busan proxy fee floors.
    try:
        text=_strip_html(_fetch('https://cardlabbusan.com/'))
        for grader,label in [('PSA','PSA'),('CGC','CGC'),('BRG','BRG')]:
            row=by.get(('CARD LAB BUSAN',grader));m=re.search(label+r'\s*등급대행[^0-9]{0,40}([0-9,]+)원',text,re.I)
            if m: row['proxy_fee_from_krw']=int(m.group(1).replace(',',''));row['live_verified']=True
        refreshed.append('CARD LAB BUSAN')
    except Exception as e: errors.append('CARD LAB BUSAN:'+type(e).__name__)
    return refreshed,errors

def _load_cache():
    try:
        with open(CACHE,encoding='utf-8') as f: return json.load(f)
    except Exception: return None

def get_proxy_costs(force=False):
    now=time.time(); cached=_load_cache()
    if not force and isinstance(cached,dict) and now-float(cached.get('_epoch',0))<REFRESH_SECONDS:
        return cached
    rows=_clone(); refreshed,errors=_refresh_public_prices(rows)
    data={'ok':True,'checked_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),'refresh_hours':6,'providers':rows,'refreshed':refreshed,'errors':errors,
          'notice':'대행사 공개가격만 표시합니다. 로그인/동적 견적·환율·업차지·국제운임·보험 실비는 임의 생성하지 않습니다. 접수 전 대행사 결제화면을 최종 확인하세요.','_epoch':now}
    try:
        tmp=CACHE+'.tmp'
        with open(tmp,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(tmp,CACHE)
    except OSError: pass
    return data

if __name__=='__main__':
    print(json.dumps(get_proxy_costs(force=True),ensure_ascii=False,indent=2))
