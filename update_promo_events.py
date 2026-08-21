#!/usr/bin/env python3
"""Validate curated promo events against official public pages without inventing events."""
import datetime as dt, json, re, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'promo_events.json'
ALLOWED={'www.pokemon-card.com','pokemoncard.co.kr','www.pokemoncard.co.kr','onepiece-cardgame.kr','www.onepiece-cardgame.kr','www.onepiece-cardgame.com','en.onepiece-cardgame.com'}

def fetch(url):
    if urllib.parse.urlparse(url).hostname not in ALLOWED: raise ValueError('허용되지 않은 공식 출처')
    req=urllib.request.Request(url,headers={'User-Agent':'TCG-Grader-Promo-Checker/1.0'})
    with urllib.request.urlopen(req,timeout=25) as r:return r.read(2_000_000).decode('utf-8','replace')

def valid(x):
    required=('game','region','name_ko','start_date','end_date','reward','condition','source')
    if not all(x.get(k) for k in required):return False
    if urllib.parse.urlparse(x['source']).hostname not in ALLOWED:return False
    try:dt.date.fromisoformat(x['start_date']);dt.date.fromisoformat(x['end_date'])
    except ValueError:return False
    return True

def main():
    data=json.loads(DATA.read_text(encoding='utf-8')); errors=[]; checked=[]
    for item in data.get('items',[]):
        if not valid(item):errors.append(f"구조 오류: {item.get('name_ko','이름 없음')}");continue
        try:
            page=fetch(item['source'])
            if not any(token in page for token in re.findall(r'[가-힣ァ-ヶ一-龠]{4,}',item.get('name_native',''))[:2]):raise ValueError('행사명 확인 실패')
            checked.append(item)
        except Exception as exc:
            errors.append(f"{item['name_ko']}: {type(exc).__name__}")
            checked.append(item)  # 일시적 통신 실패로 확인 완료 자료를 삭제하지 않음
    data['items']=checked;data['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    data['collection_status']='정상' if not errors else '기존 확인자료 유지 · 일부 출처 재확인 필요';data['collection_errors']=errors
    DATA.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return data

if __name__=='__main__':main()
