#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified append-only official release-history backfill for Pokémon / ONE PIECE / NARUTO.

The backfill is intentionally incremental so the tablet does not hammer official sites.
Each run revisits the current year and advances a small number of older years/pages.
Only official hosts are accepted; failures never delete previously verified history.
"""
from __future__ import annotations

import datetime as dt
import json, re, urllib.parse
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'release_history_progress.json'


def _load_state():
    try:
        d=json.loads(STATE.read_text(encoding='utf-8'))
        return d if isinstance(d,dict) else {}
    except Exception:
        return {}


def _save_state(d):
    tmp=Path(str(STATE)+'.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(STATE)


def _norm(s):return re.sub(r'\s+',' ',str(s or '')).strip()

def _today():return dt.date.today()


def pokemon_jp_years(fetch, html_to_text, years_per_run=2):
    """Backfill Japanese Pokémon expansion/high-class product archive from 1996 onward."""
    state=_load_state();cur=_today().year
    next_year=int(state.get('pokemon_jp_next_year') or cur)
    years=[cur]
    y=next_year
    while len(years)<years_per_run+1 and y>=1996:
        if y not in years:years.append(y)
        y-=1
    out=[];errors=[]
    pat=re.compile(
        r'(?:拡張パック|強化拡張パック|ハイクラスパック|コンセプトパック|再販パック)\s*[「『]?(.{2,80}?)[」』]?\s*'
        r'.{0,180}?(?:発売日|販売日)\s*(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日'
        r'(?:.{0,220}?(?:希望小売価格|価格)\s*([0-9,]+)円)?',re.I)
    for year in years:
        url=(f'https://www.pokemon-card.com/products/?productType=expansion&'
             f'dateLowerY={year}&dateLowerM=1&dateLowerD=1&dateUpperY={year}&dateUpperM=12&dateUpperD=31')
        try:text=html_to_text(fetch(url))
        except Exception as e:errors.append(f'Pokémon JP {year}: {type(e).__name__}');continue
        for name,yy,mm,dd,price in pat.findall(text):
            if int(yy) != year:
                continue
            row={'game':'Pokémon','region':'JP','name':_norm(name),'release_date':dt.date(int(yy),int(mm),int(dd)).isoformat(),
                 'price':f'¥{price}/팩' if price else '공식 가격 확인','status':'공식 과거출시 확인','source':url,'archive_year':year}
            out.append(row)
    if next_year>=1996:
        state['pokemon_jp_next_year']=max(1995,next_year-years_per_run)
    state['pokemon_jp_last_run']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds');_save_state(state)
    return out,errors


def onepiece_all_regions(collect_kr,collect_jp,collect_us):
    out=[];errors=[]
    for label,fn in [('ONE PIECE KR',collect_kr),('ONE PIECE JP',collect_jp),('ONE PIECE US',collect_us)]:
        try:out.extend(fn() or [])
        except Exception as e:errors.append(f'{label}: {type(e).__name__}')
    return out,errors


def naruto_official(collect_naruto):
    try:return list(collect_naruto() or []),[]
    except Exception as e:return [],[f'NARUTO: {type(e).__name__}']


def run(fetch,html_to_text,collect_onepiece_kr,collect_onepiece_jp,collect_onepiece_us,collect_naruto):
    items=[];errors=[]
    a,e=pokemon_jp_years(fetch,html_to_text);items+=a;errors+=e
    a,e=onepiece_all_regions(collect_onepiece_kr,collect_onepiece_jp,collect_onepiece_us);items+=a;errors+=e
    a,e=naruto_official(collect_naruto);items+=a;errors+=e
    return {'items':items,'errors':errors,'progress':_load_state(),
            'policy':'Pokémon/ONE PIECE/NARUTO 동일 append-only 누적정책 · 공식출처만 반영 · 실패 시 기존 이력 보존'}
