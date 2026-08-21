#!/usr/bin/env python3
"""Refresh a small verified public-price cache without bypassing logins or private APIs."""
from __future__ import annotations
import datetime as dt, html, json, re, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'market_prices.json'
HEADERS={'User-Agent':'TCG-Grader-Public-Price-Checker/1.0'}

def fetch(url:str)->str:
    if not url.startswith(('https://pokard.io/','https://kream.co.kr/')):
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

def main():
    db=json.loads(DATA.read_text(encoding='utf-8')); db.setdefault('entries',{}); errors=[]
    try:
        url='https://pokard.io/'
        text=textify(fetch(url))
        boxes={'인페르노X':('JP|인페르노 X|BOX','인페르노 X'),'닌자스피너':('JP|닌자스피너|BOX','닌자스피너'),
          '메가 드림 ex':('JP|메가 드림 ex|BOX','메가 드림 ex'),'메가브레이브':('JP|메가 브레이브|BOX','메가 브레이브'),
          '메가심포니아':('JP|메가 심포니아|BOX','메가 심포니아')}
        found_boxes=0
        for token,(key,label) in boxes.items():
            m=re.search(re.escape(token)+r'\s*₩([0-9,]+)',text,re.I)
            if m:
                set_price(db,key,'₩'+m.group(1),'BOX 리셀가','POKARD','공개 표시가격',url);found_boxes+=1
        if not found_boxes: errors.append('POKARD BOX: 가격 패턴 0건')
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
        url='https://pokard.io/jpcard/SV8a-217/'; text=textify(fetch(url))
        m=re.search(r'(?:Ungrade|미감정)\s*¥([0-9,]+)',text,re.I)
        if m:set_price(db,'JP|테라스탈 페스타 ex 일본판|HIT','¥'+m.group(1),'미감정 참고가격','POKARD · SNKRDUNK','공개 표시가격',url)
        else: errors.append('POKARD HIT: 가격 패턴 0건')
    except Exception as e: errors.append('POKARD HIT: '+type(e).__name__)
    db['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    db['collection_status']='정상' if not errors else '일부 가격 출처 확인 실패'
    db['collection_errors']=errors
    tmp=DATA.with_suffix('.json.tmp');tmp.write_text(json.dumps(db,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');tmp.replace(DATA)
    return db

if __name__=='__main__': main()
