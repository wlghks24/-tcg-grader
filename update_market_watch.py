#!/usr/bin/env python3
"""가격 미확정 상품까지 포함한 판매·재발매 추적목록을 안전하게 갱신한다."""
from __future__ import annotations
import datetime as dt, json, re
from pathlib import Path
from safe_runtime import atomic_write_json, safe_read_text, validate_public_https_url

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'market_watch.json'
RELEASES=ROOT/'releases.json'

SEEDS=[
 {'region':'KR','game':'ONE PIECE','asset':'BOX','name':'계승되는 의지','native':'[OPK-13] 부스터 팩 계승되는 의지','product_code':'OPK-13','release_date':'2026-06-26','sale_status':'거래중','release_type':'신규 발매','official_price':'₩48,000/BOX','source':'https://kream.co.kr/products/975577/'},
 {'region':'KR','game':'ONE PIECE','asset':'BOX','name':'히로인즈 에디션 8BOX','native':'[EBK-03] Heroines Edition 8BOX','product_code':'EBK-03','release_date':'2026-07-24','sale_status':'거래중','release_type':'신규 발매','official_price':'8BOX 구성','source':'https://kream.co.kr/products/1015880'},
 {'region':'KR','game':'ONE PIECE','asset':'BOX','name':'창해의 칠걸','native':'[OPK-14] 부스터 팩 창해의 칠걸','product_code':'OPK-14','release_date':'2026-08-21','sale_status':'판매중·거래확인 중','release_type':'신규 발매','official_price':'₩48,000/BOX','source':'https://kream.co.kr/products/1044391/'},
 {'region':'JP','game':'ONE PIECE','asset':'BOX','name':'계승되는 의지 일본판','native':'受け継がれる意志 [OP-13]','product_code':'OP-13','release_date':'2025-08-23','sale_status':'거래중','release_type':'재발매 관찰중','official_price':'¥5,280/BOX','source':'https://psa-index.com/op/box/f2368df8-afac-4442-b478-207121908a3c'},
 {'region':'US','game':'ONE PIECE','asset':'BOX','name':'계승되는 의지 미국판','native':'Carrying On His Will [OP-13]','product_code':'OP-13','release_date':'2025-11-07','sale_status':'거래중','release_type':'재발매 관찰중','official_price':'$4.99/팩 · 24팩','source':'https://www.tcgplayer.com/content/article/The-Best-Sealed-One-Piece-Buys-for-Mayhem-2026/b0c78d2b-ffdd-4497-b067-387273d8fade/'},
 {'region':'US','game':'ONE PIECE','asset':'BOX','name':'더 베스트 Vol.2','native':'Premium Booster -The Best- Vol.2 [PRB-02]','product_code':'PRB-02','release_date':'2025-10-03','sale_status':'거래중','release_type':'신규 발매','official_price':'공식 BOX 구성 확인','source':'https://www.tcgplayer.com/content/article/The-10-Cards-Everybody-Wants-from-Premium-Booster-The-Best-Vol-2-PRB-02/5ebe50da-37b7-4be3-a0a2-ab0520a3beb7/'},
]

def norm_region(value):
    value=(value or '').upper()
    return 'KR' if value in ('KR','KOREA') else 'JP' if value in ('JP','JAPAN') else 'US' if value in ('US','USA','EN','GLOBAL') else None

def package_type(row):
    text=json.dumps(row,ensure_ascii=False).lower()
    if re.search(r'\b(?:case|8box|10box|12box)\b|박스\s*묶음|케이스',text): return '박스 묶음·케이스'
    if re.search(r'\bbox\b|박스|elite trainer box',text): return '박스'
    if re.search(r'부스터\s*팩|booster|パック|/팩',text): return '부스터 상품 · 박스 구성 확인'
    return '상품 구성 확인'

def main():
    errors=[]
    current={}
    try:
        current=json.loads(safe_read_text(OUT))
        if not isinstance(current,dict) or not isinstance(current.get('items'),list):
            raise ValueError('기존 추적자료의 최상위 구조가 잘못되었습니다')
    except FileNotFoundError:
        current={'items':[]}
    except (OSError,ValueError,TypeError) as exc:
        current={'items':[]}
        errors.append(f'기존 추적자료 확인 실패: {type(exc).__name__}')
    items={}
    for row in current.get('items',[]):
        if not isinstance(row,dict) or row.get('region') not in {'KR','JP','US'} or row.get('asset') not in {'BOX','HIT'} or not isinstance(row.get('name'),str) or not row['name'].strip():
            errors.append('기존 추적자료의 잘못된 항목 1건 제외')
            continue
        clean=dict(row)
        clean['package_type']=clean.get('package_type') or package_type(clean)
        source=clean.get('source')
        if source:
            try:validate_public_https_url(source)
            except (TypeError,ValueError):
                errors.append(f"{clean['name']}: 안전하지 않은 기존 출처 제외")
                clean['source']=None
        items[f"{clean['region']}|{clean['name']}|{clean['asset']}"]=clean
    for row in SEEDS:
        key=f"{row['region']}|{row['name']}|{row['asset']}"
        items.setdefault(key,dict(row,package_type=package_type(row)))
    try:
        document=json.loads(safe_read_text(RELEASES))
        if not isinstance(document,dict) or not isinstance(document.get('items'),list):
            raise ValueError('출시목록 items 구조 오류')
        releases=document['items']
        for row in releases:
            if not isinstance(row,dict):
                errors.append('출시목록의 잘못된 항목 1건 제외')
                continue
            region=norm_region(row.get('region'))
            if not region: continue
            name=row.get('name') or row.get('title')
            if not isinstance(name,str) or not name.strip(): continue
            source=row.get('source')
            if source:
                try:validate_public_https_url(source)
                except (TypeError,ValueError):
                    errors.append(f'{name}: 안전하지 않은 출시 출처 제외')
                    continue
            code_match=re.search(r'\b(?:OPK|EBK|OP|EB|PRB)-?\d{1,2}\b',f"{name} {row.get('code','')}",re.I)
            code=code_match.group(0).upper() if code_match else ''
            key=f'{region}|{name}|BOX'
            items.setdefault(key,{'region':region,'game':row.get('game','확인 중'),'asset':'BOX','name':name,'native':row.get('native_name') or name,'product_code':code,'package_type':package_type(row),'release_date':row.get('release_date') or row.get('date') or '확인 중','sale_status':'판매·출시 확인 중','release_type':'재발매' if re.search(r'재발매|재입고|再販|reprint|restock',json.dumps(row,ensure_ascii=False),re.I) else '신규·상시 판매','official_price':row.get('official_price') or row.get('price') or '공식가격 확인 중','source':source})
    except (OSError,ValueError,TypeError) as exc: errors.append(f'출시목록 결합 실패: {type(exc).__name__}')
    payload={**current,'version':1,'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),'items':list(items.values()),'collection_status':'정상' if not errors else '기존 추적자료 유지','collection_errors':errors}
    atomic_write_json(OUT,payload)
    return payload

if __name__=='__main__': main()
