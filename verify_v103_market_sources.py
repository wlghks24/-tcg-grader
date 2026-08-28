#!/usr/bin/env python3
from __future__ import annotations
import json, tempfile
from pathlib import Path
import market_public_crosscheck as m


def main():
    checks=[]
    def ok(name,cond,detail=''):
        checks.append({'name':name,'ok':bool(cond),'detail':detail}); assert cond,name
    r=m.self_test();ok('parser_self_test',r['ok'],json.dumps(r,ensure_ascii=False))
    row={'key':'KR|테스트|HIT','game':'Pokémon','card_name':'피카츄','card_number':'001/100','name':'피카츄'}
    db={'entries':{'KR|테스트|HIT':dict(row)}}
    old_watch=m.WATCH;old_state=m.STATE
    with tempfile.TemporaryDirectory() as td:
        t=Path(td);m.WATCH=t/'watch.json';m.STATE=t/'state.json'
        m.WATCH.write_text('{"items":[]}',encoding='utf-8')
        def fake(url):
            if 'collectory' in url:return '피카츄 001/100 현재 시세 ₩120,000 🏅10'
            return 'Pokemon TCG 피카츄 001/100 125,000원 관심 10 · 거래 7'
        summary=m.crosscheck_market_db(db,fetcher=fake)
        cc=db['entries']['KR|테스트|HIT']['source_crosschecks']
        ok('both_sources_collected',{x['source'] for x in cc}=={'Collectory','KREAM'},str(cc))
        ok('no_primary_price_overwrite','display' not in db['entries']['KR|테스트|HIT'])
        ok('summary_counts',summary['matches']==2 and summary['requests_checked']==2,str(summary))
        m.WATCH=old_watch;m.STATE=old_state
    updater=Path(__file__).with_name('update_market_prices.py').read_text(encoding='utf-8')
    tcg=Path(__file__).with_name('tcg_updater.py').read_text(encoding='utf-8')
    ui=Path(__file__).with_name('index.html').read_text(encoding='utf-8')
    ok('market_updater_integration','crosscheck_market_db(db)' in updater)
    ok('top_level_sources','Collectory 공개 카드시세' in tcg and 'KREAM 공개 TCG 시세' in tcg)
    ok('ui_crosscheck_visible','🔎 교차확인:' in ui)
    ok('public_only_policy','비공개 API' in Path(__file__).with_name('market_public_crosscheck.py').read_text(encoding='utf-8'))
    report={'ok':all(x['ok'] for x in checks),'successful':sum(x['ok'] for x in checks),'failed':sum(not x['ok'] for x in checks),'checks':checks}
    Path(__file__).with_name('V103_MARKET_SOURCE_TEST_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':report['ok'],'successful':report['successful'],'failed':report['failed']},ensure_ascii=False))

if __name__=='__main__':main()
