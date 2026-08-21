#!/usr/bin/env python3
"""배포 전 전체 구성요소를 검사하고 결과를 누적 저장한다."""
from __future__ import annotations
import datetime as dt, json, py_compile, re, subprocess, tempfile, threading, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/'verification_history.json'
PY_FILES=('tcg_updater.py','auto_update_all.py','auto_repair_engine.py','update_releases.py','update_market_prices.py','update_market_watch.py','update_promo_events.py','update_exchange_rates.py')
JSON_FILES=('releases.json','market_prices.json','market_watch.json','promo_events.json','exchange_rates.json','auto_update_report.json','auto_update_issues.json','auto_repair_memory.json')

def check(name,fn,rows):
    try: detail=fn() or '정상';rows.append({'name':name,'ok':True,'detail':str(detail)})
    except Exception as exc: rows.append({'name':name,'ok':False,'detail':f'{type(exc).__name__}: {exc}'})

def main():
    rows=[]
    check('Python 문법',lambda:[py_compile.compile(str(ROOT/f),doraise=True) for f in PY_FILES] and f'{len(PY_FILES)}개',rows)
    parsed={}
    def json_check():
        for f in JSON_FILES: parsed[f]=json.loads((ROOT/f).read_text(encoding='utf-8'))
        return f'{len(JSON_FILES)}개'
    check('JSON 구조',json_check,rows)
    def market_check():
        prices=parsed['market_prices.json']['entries'];watch=parsed['market_watch.json']['items']
        assert prices['KR|계승되는 의지|BOX']['display']!='가격 확인 중'
        assert prices['KR|계승되는 의지|BOX']['official_price']=='₩48,000/BOX'
        assert {'KR','JP','US'} <= {x['region'] for x in watch}
        assert all(x.get('package_type') for x in watch)
        assert any(x.get('product_code')=='OPK-13' for x in watch)
        assert any('재발매' in x.get('release_type','') for x in watch)
        return f'가격 {len(prices)}개 · 판매/재발매 추적 {len(watch)}개'
    check('국가별 BOX·박스·카드 자료',market_check,rows)
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    def html_check():
        ids=re.findall(r'\bid="([^"]+)"',html);assert len(ids)==len(set(ids))
        assert 'market_watch.json' in html and 'BOX·박스' in html and '가격 확인 중' in html
        assert 'id="siteUpdateAll"' in html and 'id="siteUpdateStatus"' in html
        assert 'siteUpdateAll").addEventListener("click",refreshReleaseInfo)' in html
        return f'고유 ID {len(ids)}개'
    check('화면 구성',html_check,rows)
    def js_check():
        scripts='\n'.join(re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>',html,re.I))
        with tempfile.NamedTemporaryFile('w',suffix='.js',encoding='utf-8',delete=False) as f:f.write(scripts);path=f.name
        try: subprocess.run(['node','--check',path],check=True,capture_output=True,text=True,timeout=20)
        finally: Path(path).unlink(missing_ok=True)
        return '인라인 JavaScript 문법 정상'
    check('JavaScript 문법',js_check,rows)
    def sw_check():
        sw=(ROOT/'sw.js').read_text(encoding='utf-8');assert 'market_watch.json' in sw
        subprocess.run(['node','--check','sw.js'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=20)
        return '판매·재발매 자료 캐시 포함'
    check('서비스워커',sw_check,rows)
    def launchers():
        required=('TCG_AUTO_UPDATE.bat','정보자동업데이트.bat','START_TCG_UPDATER_ANDROID.sh','자동실행_설치.bat','ANDROID_AUTO_START_INSTALL.sh')
        assert all((ROOT/f).exists() for f in required);return f'{len(required)}개'
    check('PC·태블릿 실행파일',launchers,rows)
    def server_api():
        import tcg_updater
        server=tcg_updater.ThreadingHTTPServer(('127.0.0.1',0),tcg_updater.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            def get(path):
                with urllib.request.urlopen(base+path,timeout=5) as response:
                    return response.status,response.read().decode('utf-8')
            status,health=get('/api/health');assert status==200 and json.loads(health)['ok']
            status,watch=get('/api/market-watch');assert status==200 and len(json.loads(watch)['items'])>=3
            key=urllib.parse.quote('KR|계승되는 의지|BOX')
            status,price=get('/api/market-price?key='+key);body=json.loads(price)
            assert status==200 and body['found'] and body['price']['display']=='₩89,000'
            status,page=get('/index.html');assert status==200 and 'BOX·박스' in page
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)
        return 'health·추적목록·OPK-13 가격·화면 응답 정상'
    check('PC·태블릿 서버 실제 응답',server_api,rows)
    now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    try: history=json.loads(HISTORY.read_text(encoding='utf-8'))
    except Exception: history={'version':1,'runs':[]}
    run={'checked_at':now,'ok':all(x['ok'] for x in rows),'pass_count':sum(x['ok'] for x in rows),'failure_count':sum(not x['ok'] for x in rows),'checks':rows}
    history['updated_at']=now;history['runs']=(history.get('runs',[])+[run])[-100:]
    temp=HISTORY.with_suffix('.json.tmp');temp.write_text(json.dumps(history,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(HISTORY)
    print('전체 프로그램 검사 결과')
    for row in rows: print(f"- {'통과' if row['ok'] else '실패'}: {row['name']} · {row['detail']}")
    print(f"누적 검사 {len(history['runs'])}회 · 이번 결과 {'정상' if run['ok'] else '수정 필요'}")
    return 0 if run['ok'] else 1

if __name__=='__main__': raise SystemExit(main())
