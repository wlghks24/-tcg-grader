#!/usr/bin/env python3
"""Refresh a small verified public-price cache without bypassing logins or private APIs."""
from __future__ import annotations
import datetime as dt, html, json, re, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'market_prices.json'
APP=ROOT/'index.html'
HEADERS={'User-Agent':'TCG-Grader-Public-Price-Checker/1.0'}

def fetch(url:str)->str:
    if not url.startswith(('https://pokard.io/','https://kream.co.kr/','https://www.packmagik.com/',
                           'https://www.tcgplayer.com/','https://psa-index.com/')):
        raise ValueError('허용되지 않은 가격 출처')
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=20) as r:
        return r.read(2_000_000).decode('utf-8','replace')

def textify(raw:str)->str:
    raw=re.sub(r'(?is)<script.*?</script>|<style.*?</style>',' ',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return re.sub(r'\s+',' ',html.unescape(raw)).strip()

def set_price(db,key,display,kind,market,transactions,source):
    db['entries'][key]={'display':display,'kind':kind,'market':market,'transactions':transactions,
      'source_date':dt.date.today().isoformat(),'source':source}

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
    }
    today=dt.date.today().isoformat()
    for key,value in seeds.items():
        current=db['entries'].setdefault(key,{})
        for field,field_value in value.items(): current.setdefault(field,field_value)
        current.setdefault('source_date',today)

def atomic_save(db):
    tmp=DATA.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(db,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    tmp.replace(DATA)

def coverage(db):
    raw=APP.read_text(encoding='utf-8');block=raw.split('const COUNTRY_BOX_DATA=',1)[1].split('const LEARNING_PRICE_DATA=',1)[0]
    products=re.findall(r'\{country:"(KR|JP|US)",game:"[^"]+",name:"([^"]+)"',block)
    required={f'{region}|{name}|{asset}' for region,name in products for asset in ('BOX','HIT')}
    verified=required & set(db.get('entries',{}));missing=sorted(required-verified)
    return {'total':len(required),'verified':len(verified),'pending':len(missing),'missing_keys':missing}

def main():
    db=json.loads(DATA.read_text(encoding='utf-8')); db.setdefault('entries',{}); errors=[]
    keep_verified_seeds(db)
    # 느린 외부 사이트가 응답하지 않아도 확인 완료 기준자료는 즉시 보존한다.
    atomic_save(db)
    try:
        url='https://pokard.io/'
        text=textify(fetch(url))
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
    except Exception as e: errors.append('POKARD BOX: '+type(e).__name__)
    try:
        url='https://kream.co.kr/products/959332'; text=textify(fetch(url))
        vals=[int(x.replace(',','')) for x in re.findall(r'Ungraded A\s*([0-9,]+)원',text)[:3]]
        if vals:
            vals.sort(); median=vals[len(vals)//2]
            set_price(db,'KR|테라스탈 페스타 ex|HIT',f'₩{median:,}',f'최근 미감정 거래 {len(vals)}건 중앙값','KREAM 한국판','공개 페이지 거래자료',url)
        else: errors.append('KREAM HIT: 거래가격 패턴 0건')
    except Exception as e: errors.append('KREAM HIT: '+type(e).__name__)
    try:
        url='https://kream.co.kr/products/stock/16256508'; text=textify(fetch(url))
        values=[int(x.replace(',','')) for x in re.findall(r'(?:구매가|즉시 구매가)\s*([0-9,]+)원',text)]
        plausible=[x for x in values if 50_000 <= x <= 500_000]
        if plausible:
            set_price(db,'KR|로맨스 던|BOX',f'₩{plausible[0]:,}','KREAM 공개 상품 구매가','KREAM 한국판','공개 구매가 · 판매완료 체결가 아님',url)
        else: errors.append('KREAM 로맨스 던 BOX: 구매가격 패턴 0건')
    except Exception as e: errors.append('KREAM 로맨스 던 BOX: '+type(e).__name__)
    try:
        url='https://kream.co.kr/products/627575';text=textify(fetch(url))
        trades=[int(x.replace(',','')) for x in re.findall(r'ONE SIZE\s*([0-9,]+)원',text)[:12]]
        plausible=[x for x in trades if 20_000<=x<=150_000]
        if plausible:
            low,high=min(plausible),max(plausible);display=f'₩{low:,}' if low==high else f'₩{low:,}~₩{high:,}'
            set_price(db,'KR|블랙볼트|BOX',display,'최근 공개 체결가 범위','KREAM 한국판',f'최근 공개 체결 {len(plausible)}건',url)
        else: errors.append('KREAM 블랙볼트 BOX: 체결가격 패턴 0건')
    except Exception as e: errors.append('KREAM 블랙볼트 BOX: '+type(e).__name__)
    try:
        url='https://www.packmagik.com/cards/op-op14-op14-009-p1';text=textify(fetch(url))
        m=re.search(r'(?:Market|시장가)\s*\$([0-9]+(?:\.[0-9]+)?)',text,re.I)
        if m:set_price(db,'KR|창해의 칠걸|HIT','$'+m.group(1),'OP14-009 패러렐 국제판 참고시세','Pack Magik 국제시장','한국판 실거래 아님 · 국제판 시장가 참고',url)
        else: errors.append('Pack Magik OP14-009: 가격 패턴 0건')
    except Exception as e: errors.append('Pack Magik OP14-009: '+type(e).__name__)
    try:
        url='https://pokard.io/jpcard/SV8a-217/'; text=textify(fetch(url))
        m=re.search(r'(?:Ungrade|미감정)\s*¥([0-9,]+)',text,re.I)
        if m:set_price(db,'JP|테라스탈 페스타 ex 일본판|HIT','¥'+m.group(1),'미감정 참고가격','POKARD · SNKRDUNK','공개 표시가격',url)
        else: errors.append('POKARD HIT: 가격 패턴 0건')
    except Exception as e: errors.append('POKARD HIT: '+type(e).__name__)
    db['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    db['collection_status']='정상' if not errors else '일부 가격 출처 확인 실패'
    db['collection_errors']=errors
    db['catalog_price_coverage']=coverage(db)
    atomic_save(db)
    return db

if __name__=='__main__': main()
