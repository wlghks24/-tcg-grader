#!/usr/bin/env python3
"""Refresh a small verified public-price cache without bypassing logins or private APIs."""
from __future__ import annotations
import os
import time
import datetime as dt, json, re, urllib.error, urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, diagnostic_exception, env_int, html_to_text, safe_read_text, safe_urlopen

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'market_prices.json'
APP=ROOT/'index.html'
HEADERS={
 'User-Agent':'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/126.0 Safari/537.36 TCG-Grader/2.0',
 'Accept':'text/html,application/xhtml+xml;q=0.9,*/*;q=0.7',
 'Accept-Language':'ko-KR,ko;q=0.9,en;q=0.7',
}
ALLOWED_MARKET={'pokard.io','kream.co.kr','www.kream.co.kr','collectory.cc','www.collectory.cc','www.packmagik.com','packmagik.com','www.tcgplayer.com','tcgplayer.com','psa-index.com','www.psa-index.com','narutomarket.com','www.narutomarket.com'}
NETWORK_ERRORS=(urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError, ValueError)

def fetch(url:str)->str:
    if not url.startswith(('https://pokard.io/','https://kream.co.kr/','https://www.packmagik.com/',
                           'https://www.tcgplayer.com/','https://psa-index.com/','https://narutomarket.com/')):
        raise ValueError('허용되지 않은 가격 출처')
    attempts=(url, url+'/' if 'kream.co.kr/products/' in url and not url.endswith('/') else url)
    last_error=None
    for index,target in enumerate(attempts):
        req=urllib.request.Request(target,headers=HEADERS)
        try:
            with safe_urlopen(req,timeout=env_int('TCG_HTTP_TIMEOUT',20,5,60),allowed_hosts=ALLOWED_MARKET) as r:
                return r.read(2_000_000).decode('utf-8','replace')
        except urllib.error.HTTPError as exc:
            last_error=exc
            if exc.code not in {500,502,503,504} or index+1>=len(attempts):raise
            time.sleep(0.35)
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
            last_error=exc
            if index+1>=len(attempts):raise
    if last_error is not None:raise last_error
    raise urllib.error.URLError('empty fetch attempt')

def kream_label_prices(text:str,label_pattern:str,low:int,high:int,limit:int=12)->list[int]:
    """Read public KREAM transaction rows without mistaking release/shipping prices."""
    values=[int(value.replace(',','')) for value in re.findall(label_pattern+r'\s*([0-9,]+)원',text,re.I)]
    return [value for value in values if low<=value<=high][:max(1,min(int(limit),30))]

def set_price(db,key,display,kind,market,transactions,source):
    db['entries'][key]={'display':display,'kind':kind,'market':market,'transactions':transactions,
      'source_date':dt.date.today().isoformat(),'source':source}

def blank_grade_prices():
    return {company:{str(grade):0 for grade in range(1,11)}
            for company in ('PSA','BGS','CGC','TAG','BRG')}

def keep_verified_seeds(db):
    """공개 상품 페이지에서 확인한 기준값을 보존한다. 수집 실패 때 빈 목록으로 지우지 않는다."""
    seeds={
      'KR|계승되는 의지|BOX':{'display':'₩89,000','kind':'KREAM 공개 현재가','market':'KREAM 한국판','transactions':'공개 페이지 거래 1,290건','source':'https://kream.co.kr/products/975577/','game':'ONE PIECE','product_name':'[OPK-13] 계승되는 의지','official_price':'₩48,000/BOX'},
      'KR|히로인즈 에디션 8BOX|BOX':{'display':'₩574,000','kind':'8BOX 묶음 공개 현재가','market':'KREAM 한국판','transactions':'공개 페이지 거래 12건 · 박스당 참고 약 ₩71,750','source':'https://kream.co.kr/products/1015880','game':'ONE PIECE','product_name':'[EBK-03] Heroines Edition 8BOX','official_price':'8BOX 구성'},
      'JP|계승되는 의지 일본판|BOX':{'display':'¥24,500','kind':'SNKRDUNK 공개 거래가격','market':'PSA Index · SNKRDUNK','transactions':'2026-08-13 공개 이력','source':'https://psa-index.com/op/box/f2368df8-afac-4442-b478-207121908a3c','game':'ONE PIECE','product_name':'受け継がれる意志 [OP-13]','official_price':'¥5,280/BOX'},
      'US|계승되는 의지 미국판|BOX':{'display':'$419.29','kind':'TCGplayer Market Price','market':'TCGplayer 미국판','transactions':'공개 시장가격','source':'https://www.tcgplayer.com/content/article/Everything-We-Know-About-One-Piece-TCG-s-Carrying-On-His-Will-OP-13/39711531-74c9-45e6-acab-c67de795bc03/','game':'ONE PIECE','product_name':"Carrying On His Will [OP-13]",'official_price':'$4.99/팩 · 24팩'},
      'US|더 베스트 Vol.2|BOX':{'display':'$394.85','kind':'TCGplayer Market Price','market':'TCGplayer 미국판','transactions':'공개 시장가격','source':'https://www.tcgplayer.com/content/article/The-10-Cards-Everybody-Wants-from-Premium-Booster-The-Best-Vol-2-PRB-02/5ebe50da-37b7-4be3-a0a2-ab0520a3beb7/','game':'ONE PIECE','product_name':'Premium Booster -The Best- Vol.2 [PRB-02]','official_price':'공식 BOX 구성 확인'},
      'JP|계승되는 의지 일본판 에이스 만화패러렐|HIT':{'display':'₩11,190,000~₩13,000,000','kind':'PSA10 공개 체결가 범위','market':'KREAM 한국 거래','transactions':'공개 체결자료','source':'https://kream.co.kr/products/911415','game':'ONE PIECE','card_name':'포트거스 D. 에이스 만화 패러렐','product_name':'계승되는 의지 일본판'},
      'JP|계승되는 의지 일본판 삼형제 SR|HIT':{'display':'₩20,000','kind':'미감정 A 공개 체결가','market':'KREAM 한국 거래','transactions':'공개 체결자료','source':'https://kream.co.kr/products/991036','game':'ONE PIECE','card_name':'에이스·사보·루피 SR','product_name':'계승되는 의지 일본판'},
      'JP|계승되는 의지 일본판 카무사리|HIT':{'display':'₩43,000','kind':'미감정 A 공개 체결가','market':'KREAM 한국 거래','transactions':'공개 체결자료','source':'https://kream.co.kr/products/911481','game':'ONE PIECE','card_name':'카무사리 R-P','product_name':'계승되는 의지 일본판'}
      ,'US|NARUTO CP-001 Gen Con 2026|HIT':{'display':'$700~$1,000','kind':'공개 판매목록 최저가~참조가 · 체결 확정가 아님','market':'NARUTOMARKET · eBay 공개 판매목록','transactions':'2026-08-25 공개 판매목록 52건 · PSA 10 등록품 0건','source':'https://narutomarket.com/en/market/chakra-card-cp-001-gen-con-2026','game':'NARUTO','card_name':'Chakra Card CP-001 · Gen Con 2026 Ver.','card_number':'CP-001','product_name':'NARUTO CARD GAME Gen Con 2026 Promo','image_url':'https://narutomarket.com/uploads/8a9ce860-f747-4f68-9082-85b22c39c7e5-237767__carta.webp?v=1786351506'},
      'KR|릴리에 SM1M 065/060|HIT':{'display':'미등급 ₩300,000 · BRG 9 ₩450,000 · BRG 10 ₩2,000,000','kind':'BRG 공식 페이지 공개 거래 예시','market':'BRG · 2025년 5월 거래플랫폼 P사 자료','transactions':'업체 공개 예시 · 카드·시점 한정','source':'https://break.co.kr/','game':'Pokémon','card_name':'릴리에 Full Art 065/060','card_number':'SM1M 065/060','product_name':'컬렉션 문 한국판'}
    }
    today=dt.date.today().isoformat()
    for key,value in seeds.items():
        current=db['entries'].setdefault(key,{})
        for field,field_value in value.items(): current.setdefault(field,field_value)
        current.setdefault('source_date',today)
    db.setdefault('graded_prices',{})
    profiles={
      'US|NARUTO CP-001 Gen Con 2026|HIT':{
        'raw_usd_low':700,'raw_usd_reference':1000,'raw_krw':1_179_000,
        'grade_prices_krw':blank_grade_prices(),
        'note':'미감정 공개 판매목록만 확인 · 5개 업체 등급별 거래자료 없음 · 확인되지 않은 등급 가격은 직접 입력'
      },
      'JP|계승되는 의지 일본판 에이스 만화패러렐|HIT':{
        'raw_krw':0,'grade_prices_krw':blank_grade_prices(),
        'note':'PSA 10 공개 체결가 범위 중앙값 · 다른 업체·등급은 자료 확인 후 직접 입력'
      },
      'KR|릴리에 SM1M 065/060|HIT':{
        'raw_krw':300_000,'grade_prices_krw':blank_grade_prices(),
        'note':'BRG 공식 페이지의 2025년 5월 특정 카드 거래 예시 · 다른 업체·등급에 일반화 금지'
      }
    }
    profiles['JP|계승되는 의지 일본판 에이스 만화패러렐|HIT']['grade_prices_krw']['PSA']['10']=12_095_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['9']=450_000
    profiles['KR|릴리에 SM1M 065/060|HIT']['grade_prices_krw']['BRG']['10']=2_000_000
    for key,value in profiles.items():
        current=db['graded_prices'].setdefault(key,{})
        for field,field_value in value.items():
            if field in ('grade_prices_krw','note'):
                current[field]=field_value
            else:
                current.setdefault(field,field_value)
        for obsolete in ('psa8_krw','psa9_krw','psa10_krw','aph10_krw'):
            current.pop(obsolete,None)
    defaults=db.setdefault('grading_cost_defaults',{})
    defaults.update({
      'currency':'KRW','grading_fee_krw':0,'round_trip_shipping_krw':30_000,
      'selling_fee_percent':6.5,'editable':True,
      'company_fees_krw':{'PSA':0,'BGS':0,'CGC':0,'TAG':0,'BRG':19_800},
      'company_fee_basis':{'BRG':'공식 Regular 장당 가격 · 2026-08-25 확인','PSA':'직접 입력','BGS':'직접 입력','CGC':'직접 입력','TAG':'직접 입력'},
      'notice':'BRG 외 업체는 서비스·보험가액·대행 여부에 따라 달라지므로 현재 실제 비용을 직접 입력'
    })

def atomic_save(db):
    atomic_write_json(DATA,db,suffix='.json.tmp')

def _sanitize_entries(db):
    entries=db.get('entries')
    if not isinstance(entries,dict):
        bad={'__entries__':entries}
        db['entries']={}
        quarantine=db.setdefault('invalid_entries_quarantine',{})
        quarantine.update(bad)
        return 1
    quarantine=db.setdefault('invalid_entries_quarantine',{})
    repaired=0
    for key,value in list(entries.items()):
        valid_key=isinstance(key,str) and key.count('|')==2
        valid_value=isinstance(value,dict) and bool(value.get('display'))
        if valid_key and valid_value:
            continue
        quarantine[str(key)]={'value':value,'reason':'invalid market entry quarantined'}
        entries.pop(key,None)
        repaired+=1
    # Keep quarantine bounded: it is diagnostic memory, not a second market DB.
    if len(quarantine)>100:
        for key in list(quarantine)[:-100]:
            quarantine.pop(key,None)
    return repaired


def coverage(db):
    raw=safe_read_text(APP)
    start='const COUNTRY_BOX_DATA='; end='const LEARNING_PRICE_DATA='
    if start not in raw or end not in raw:
        return {'total':0,'verified':0,'pending':0,'missing_keys':[],
                'warning':'catalog_marker_missing · 가격자료는 유지하고 UI 카탈로그 커버리지 계산만 보류'}
    try:
        block=raw.split(start,1)[1].split(end,1)[0]
        products=re.findall(r'\{country:"(KR|JP|US)",game:"[^"]+",name:"([^"]+)"',block)
    except (IndexError,TypeError,ValueError):
        return {'total':0,'verified':0,'pending':0,'missing_keys':[],
                'warning':'catalog_parse_failed · 가격자료는 유지하고 UI 카탈로그 커버리지 계산만 보류'}
    required={f'{region}|{name}|{asset}' for region,name in products for asset in ('BOX','HIT')}
    verified=required & set(db.get('entries',{}));missing=sorted(required-verified)
    return {'total':len(required),'verified':len(verified),'pending':len(missing),'missing_keys':missing}

def main():
    db=json.loads(safe_read_text(DATA)); errors=[]; initial_repairs=_sanitize_entries(db)
    keep_verified_seeds(db)
    # 느린 외부 사이트가 응답하지 않아도 확인 완료 기준자료는 즉시 보존한다.
    atomic_save(db)
    try:
        url='https://narutomarket.com/en/market/chakra-card-cp-001-gen-con-2026';text=html_to_text(fetch(url))
        reference=re.search(r'Reference listing price\s*\$([0-9,.]+)',text,re.I)
        cheapest=re.search(r'Cheapest listing\s*\$([0-9,.]+)',text,re.I)
        listings=re.search(r'Listings\s*([0-9,]+)',text,re.I)
        if reference and cheapest:
            low=float(cheapest.group(1).replace(',',''));high=float(reference.group(1).replace(',',''))
            display=f'${low:,.0f}~${high:,.0f}'
            set_price(db,'US|NARUTO CP-001 Gen Con 2026|HIT',display,'공개 판매목록 최저가~참조가 · 체결 확정가 아님','NARUTOMARKET · eBay 공개 판매목록',f'공개 판매목록 {listings.group(1) if listings else "확인"}건 · PSA 10 등록품 별도 확인',url)
            db['entries']['US|NARUTO CP-001 Gen Con 2026|HIT'].update({'game':'NARUTO','card_name':'Chakra Card CP-001 · Gen Con 2026 Ver.','card_number':'CP-001','product_name':'NARUTO CARD GAME Gen Con 2026 Promo','image_url':'https://narutomarket.com/uploads/8a9ce860-f747-4f68-9082-85b22c39c7e5-237767__carta.webp?v=1786351506'})
        else: errors.append('NARUTO CP-001: 가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('NARUTO CP-001: '+diagnostic_exception(e))
    try:
        url='https://pokard.io/'
        text=html_to_text(fetch(url))
        boxes={'인페르노X':('JP|인페르노 X|BOX','인페르노 X'),'닌자스피너':('JP|닌자스피너|BOX','닌자스피너'),
          '메가 드림 ex':('JP|메가 드림 ex|BOX','메가 드림 ex'),'메가브레이브':('JP|메가 브레이브|BOX','메가 브레이브'),
          '메가심포니아':('JP|메가 심포니아|BOX','메가 심포니아'),'스타버스':('JP|스타버스|BOX','스타버스'),
          'VMAX 클라이맥스':('JP|VMAX 클라이맥스|BOX','VMAX 클라이맥스'),'니힐제로':('JP|니힐제로|BOX','니힐제로'),
          '포켓몬 카드 151':('JP|포켓몬 카드 151|BOX','포켓몬 카드 151'),'블랙볼트':('JP|블랙볼트 일본판|BOX','블랙볼트'),
          '화이트플레어':('JP|화이트플레어 일본판|BOX','화이트플레어'),'25주년 기념 컬렉션':('JP|25주년 기념 컬렉션|BOX','25주년 기념 컬렉션'),
          '브이스타 유니버스':('JP|브이스타 유니버스|BOX','브이스타 유니버스'),'배틀리전':('JP|배틀리전|BOX','배틀리전'),
          '포켓몬 GO':('JP|포켓몬 GO|BOX','포켓몬 GO'),'창공스트림':('JP|창공스트림|BOX','창공스트림')}
        found_boxes=0
        for token,(key,label) in boxes.items():
            m=re.search(re.escape(token)+r'\s*₩([0-9,]+)',text,re.I)
            if m:
                set_price(db,key,'₩'+m.group(1),'BOX 리셀가','POKARD','공개 표시가격',url);found_boxes+=1
        if not found_boxes: errors.append('POKARD BOX: 가격 패턴 0건')
        popular_cards={
          '피카츄 RR 포켓심쿵 컬렉션 RR':('KR|포켓심쿵 컬렉션|HIT','Pokémon','피카츄 RR','PSA10 공개 체결가'),
          '메가 리자몽 X ex':('JP|메가 리자몽 X ex|HIT','Pokémon','메가 리자몽 X ex','미감정 공개 시세'),
          '뮤 P 극장판 뮤츠의 역습 프로모 카드':('KR|뮤츠의 역습 프로모|HIT','Pokémon','뮤 프로모','PSA10 공개 체결가'),
          '리자몽ex SR':('KR|흑염의 지배자|HIT','Pokémon','리자몽 ex SR','PSA10 공개 체결가')}
        for token,(key,game,card_name,kind) in popular_cards.items():
            m=re.search(re.escape(token)+r'.{0,80}?([₩¥$][0-9,]+)',text,re.I)
            if m:
                set_price(db,key,m.group(1),kind,'POKARD',f'{token} 공개 표시가격',url)
                db['entries'][key].update({'game':game,'card_name':card_name,'product_name':token})
    except NETWORK_ERRORS as e: errors.append('POKARD BOX: '+diagnostic_exception(e))
    try:
        url='https://kream.co.kr/products/959332'; text=html_to_text(fetch(url))
        vals=kream_label_prices(text,r'Ungraded A',30_000,2_000_000,3)
        if vals:
            vals.sort(); median=vals[len(vals)//2]
            set_price(db,'KR|테라스탈 페스타 ex|HIT',f'₩{median:,}',f'최근 미감정 거래 {len(vals)}건 중앙값','KREAM 한국판','공개 페이지 거래자료',url)
        else: errors.append('KREAM HIT: 거래가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('KREAM HIT: '+diagnostic_exception(e))
    try:
        url='https://kream.co.kr/products/290634'; text=html_to_text(fetch(url))
        plausible=kream_label_prices(text,r'ONE SIZE',50_000,500_000,12)
        if plausible:
            set_price(db,'KR|로맨스 던|BOX',f'₩{plausible[0]:,}','KREAM 공개 상품 구매가','KREAM 한국판','공개 구매가 · 판매완료 체결가 아님',url)
        else: errors.append('KREAM 로맨스 던 BOX: 구매가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('KREAM 로맨스 던 BOX: '+diagnostic_exception(e))
    try:
        url='https://kream.co.kr/products/627575';text=html_to_text(fetch(url))
        plausible=kream_label_prices(text,r'ONE SIZE',20_000,150_000,12)
        if plausible:
            low,high=min(plausible),max(plausible);display=f'₩{low:,}' if low==high else f'₩{low:,}~₩{high:,}'
            set_price(db,'KR|블랙볼트|BOX',display,'최근 공개 체결가 범위','KREAM 한국판',f'최근 공개 체결 {len(plausible)}건',url)
        else: errors.append('KREAM 블랙볼트 BOX: 체결가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('KREAM 블랙볼트 BOX: '+diagnostic_exception(e))
    try:
        url='https://www.packmagik.com/cards/op-op14-op14-009-p1';text=html_to_text(fetch(url))
        m=re.search(r'(?:Market|시장가)\s*\$([0-9]+(?:\.[0-9]+)?)',text,re.I)
        if m:set_price(db,'KR|창해의 칠걸|HIT','$'+m.group(1),'OP14-009 패러렐 국제판 참고시세','Pack Magik 국제시장','한국판 실거래 아님 · 국제판 시장가 참고',url)
        else: errors.append('Pack Magik OP14-009: 가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('Pack Magik OP14-009: '+diagnostic_exception(e))
    try:
        url='https://pokard.io/jpcard/SV8a-217/'; text=html_to_text(fetch(url))
        m=re.search(r'(?:Ungrade|미감정)\s*¥([0-9,]+)',text,re.I)
        if m:set_price(db,'JP|테라스탈 페스타 ex 일본판|HIT','¥'+m.group(1),'미감정 참고가격','POKARD · SNKRDUNK','공개 표시가격',url)
        else: errors.append('POKARD HIT: 가격 패턴 0건')
    except NETWORK_ERRORS as e: errors.append('POKARD HIT: '+diagnostic_exception(e))
    try:
        from box_hit_market_discovery import merge_market_catalog
        merge_market_catalog(db)
    except Exception as e:
        errors.append('BOX/HIT 다중마켓 자동발견: '+diagnostic_exception(e))
    try:
        from market_public_crosscheck import crosscheck_market_db
        crosscheck_market_db(db)
    except (OSError, ValueError, TypeError, urllib.error.URLError, TimeoutError) as e:
        errors.append('Collectory/KREAM 교차확인: '+diagnostic_exception(e))
    late_repairs=_sanitize_entries(db)
    repaired_entries=initial_repairs+late_repairs
    if repaired_entries:
        db['market_entry_repair']={'repaired_count':repaired_entries,'action':'malformed rows quarantined; verified rows preserved'}
    transient_market_errors=[]
    hard_market_errors=[]
    for item in errors:
        text=str(item)
        kream_transient=(
            re.search(r'^KREAM ',text,re.I) is not None and (
                re.search(r'HTTPError: status (?:403|429|5(?:00|02|03|04))\b',text,re.I) is not None
                or re.search(r'(?:URLError|TimeoutError|timed out|temporary failure|connection reset|name resolution|DNS)',text,re.I) is not None
            )
        )
        if kream_transient:
            transient_market_errors.append(text)
        else:
            hard_market_errors.append(text)
    db['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    db['collection_status']='정상' if not hard_market_errors else '일부 가격 출처 확인 실패'
    db['collection_errors']=hard_market_errors
    db['collection_warnings']=transient_market_errors
    db['collection_note']='KREAM 원출처 403/429/5xx/네트워크 지연 시 직전 검증자료 유지 · 다음 업데이트에서 재확인' if transient_market_errors else ''
    db['catalog_price_coverage']=coverage(db)
    atomic_save(db)
    return db

if __name__=='__main__': main()
