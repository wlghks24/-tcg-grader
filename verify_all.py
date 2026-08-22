#!/usr/bin/env python3
"""배포 전 전체 구성요소를 검사하고 결과를 누적 저장한다."""
from __future__ import annotations
import datetime as dt, json, py_compile, re, subprocess, tempfile, threading, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/'verification_history.json'
PY_FILES=('tcg_updater.py','auto_update_all.py','auto_repair_engine.py','update_releases.py','update_market_prices.py','update_market_watch.py','update_promo_events.py','update_purchase_sources.py','update_exchange_rates.py','migrate_old_data.py')
JSON_FILES=('releases.json','market_prices.json','market_watch.json','promo_events.json','purchase_sources.json','exchange_rates.json','auto_update_report.json','auto_update_issues.json','auto_repair_memory.json','learning_store.json')

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
    def purchase_check():
        sources=parsed['purchase_sources.json']['sources']
        assert {'KR','JP','US'} <= {x['region'] for x in sources}
        assert {'Pokemon','ONE PIECE','NARUTO'} <= {g for x in sources for g in x['games']}
        assert {'official','marketplace','used','blog'} <= {x['type'] for x in sources}
        assert any(x.get('channel')=='offline' for x in sources)
        assert {'KR','JP','US'} <= {x['region'] for x in sources if x.get('channel')=='offline'}
        assert all(x.get('url') or '{query}' in x.get('url_template','') for x in sources)
        assert any(x['name']=='Pokémon Center US' and x['type']=='official' for x in sources)
        offline=sum(x.get('channel')=='offline' for x in sources)
        return f'{len(sources)}개 · 온라인 {len(sources)-offline}개 / 오프라인 {offline}개 · 3개 국가'
    check('국가별 구매처 검색',purchase_check,rows)
    def promo_check():
        items=parsed['promo_events.json']['items']
        assert len(items)>=5
        assert {'promo','collaboration'} <= {x.get('category','promo') for x in items}
        assert all(x.get('source','').startswith('https://') and x.get('condition') and x.get('reward') for x in items)
        return f'{len(items)}개 · 프로모/콜라보·특별행사 · 공식 출처·기간·조건 확인'
    check('프로모·콜라보 행사',promo_check,rows)
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    def html_check():
        ids=re.findall(r'\bid="([^"]+)"',html);assert len(ids)==len(set(ids))
        assert 'market_watch.json' in html and 'BOX·박스' in html and '가격 확인 중' in html
        assert 'id="siteUpdateAll"' in html and 'id="siteUpdateStatus"' in html
        assert 'siteUpdateAll").addEventListener("click",refreshReleaseInfo)' in html
        required=('v30mode','rawMode','slabMode','v30slab','slabAnalyze','precisionHub','v30validation','saveValidation','recalcCalibration','qualityStatus','v31testdashboard')
        assert all(f'id="{item}"' in html for item in required)
        assert html.index('TCG 등급 사전검사기 v31') < html.index('id="gradeStart"')
        assert html.index('id="gradeStart"') < html.index('id="v30mode"') < html.index('id="precisionHub"') < html.index('id="v30validation"')
        assert 'const grades=window.tcgLastGrades||{}' in html
        assert all(f'id="{item}"' in html for item in ('purchasePanel','purchaseGame','purchaseQuery','purchaseRegionGrid','guideLeft','guideRight','guideTop','guideBottom','guideCalculate','guideResult'))
        assert 'applyGuideCenteringCap' in html and 'purchase_sources.json' in html
        assert 'data-purchase-channel="online"' in html and 'data-purchase-channel="offline"' in html
        assert 'id="promoType"' in html and '콜라보·특별행사' in html
        assert 'id="tabletServerGuide"' in html and 'START_TCG_UPDATER_ANDROID.sh' in html
        assert 'setInterval(syncBackgroundData,60000)' in html
        assert 'safeExternalUrl' in html and 'escapeDisplayText' in html
        assert 'useCanonicalLocalServer' in html and 'http://127.0.0.1:8765' in html
        assert 'updateViaCache:"none"' in html
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
        sw=(ROOT/'sw.js').read_text(encoding='utf-8');assert 'market_watch.json' in sw and 'purchase_sources.json' in sw
        subprocess.run(['node','--check','sw.js'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=20)
        return '판매·재발매 자료 캐시 포함'
    check('서비스워커',sw_check,rows)
    def launchers():
        required=('TCG_AUTO_UPDATE.bat','정보자동업데이트.bat','START_TCG_UPDATER_ANDROID.sh','자동실행_설치.bat','ANDROID_AUTO_START_INSTALL.sh','PC_SERVER_AUTO_START_INSTALL.bat','TCG_SERVER_AUTO_RUN.cmd','자동실행_해제.bat','기존버전_학습자료_가져오기.bat','학습자료_백업.bat','migrate_old_data.py')
        assert all((ROOT/f).exists() for f in required)
        for script in ('START_TCG_UPDATER_ANDROID.sh','ANDROID_AUTO_START_INSTALL.sh','ANDROID_AUTO_START_REMOVE.sh'):
            subprocess.run(['bash','-n',script],cwd=ROOT,check=True,capture_output=True,text=True,timeout=10)
        return f'{len(required)}개 · 안드로이드 셸 문법 정상'
    check('PC·태블릿 실행파일',launchers,rows)
    def tablet_auto_security():
        import auto_update_all, update_purchase_sources, update_promo_events
        assert len(auto_update_all.JOBS)==6
        expected_modules=('update_releases','update_market_watch','update_market_prices','update_promo_events','update_purchase_sources','update_exchange_rates')
        assert tuple(job[1] for job in auto_update_all.JOBS)==expected_modules
        for unsafe in ('http://example.com','https://127.0.0.1/private','https://localhost/private','https://user@example.com/path'):
            try: update_purchase_sources.checked_url(unsafe)
            except ValueError: pass
            else: raise AssertionError(f'위험 주소 허용: {unsafe}')
        update_purchase_sources.checked_url('https://onepiece-cardgame.kr/events/')
        try: update_promo_events.approved_url('https://example.com/event')
        except ValueError: pass
        else: raise AssertionError('비공식 행사 출처 허용')
        launcher=(ROOT/'START_TCG_UPDATER_ANDROID.sh').read_text(encoding='utf-8')
        boot=(ROOT/'ANDROID_AUTO_START_INSTALL.sh').read_text(encoding='utf-8')
        assert 'python tcg_updater.py' in launcher and 'python auto_update_all.py' not in launcher
        assert "PORT=8765" in (ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert 'while true; do' in boot and 'sleep 10' in boot
        for pc_script in ('TCG_AUTO_UPDATE.bat','정보자동업데이트.bat'):
            content=(ROOT/pc_script).read_text(encoding='utf-8')
            assert 'auto_update_all.py' in content and '6 STEPS' in content
        return '6종 자동수집 · 공식 HTTPS 검증 · 서버 우선 시작 · 1분 화면 동기화'
    check('태블릿 자동수집·링크 보안',tablet_auto_security,rows)
    def startup_safety():
        installer=(ROOT/'PC_SERVER_AUTO_START_INSTALL.bat').read_text(encoding='utf-8')
        runner=(ROOT/'TCG_SERVER_AUTO_RUN.cmd').read_text(encoding='utf-8')
        remover=(ROOT/'자동실행_해제.bat').read_text(encoding='utf-8')
        assert 'if not exist "tcg_updater.py"' in installer
        assert 'if not exist "index.html"' in installer
        assert 'TCG_SERVER_AUTO_RUN.cmd' in installer
        assert ':RUN' in runner and 'goto RUN' in runner and 'Restarting in 10 seconds' in runner
        assert 'timeout /t 30' in runner and 'tcg_updater.py' in runner
        assert 'TCG_SERVER_AUTO_START.cmd' in remover and 'TCG_AUTO_UPDATE_START.cmd' in remover
        return '필수파일·Python 확인 · 오류 시 10초 후 자동복구'
    check('Windows 자동실행 안전장치',startup_safety,rows)
    def migration_safety():
        import migrate_old_data
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);old=base/'old';new=base/'new';old.mkdir();new.mkdir()
            (old/'tcg_updater.py').write_text('# old',encoding='utf-8');(new/'tcg_updater.py').write_text('# new',encoding='utf-8')
            def put(folder,name,data):(folder/name).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            put(old,'learning_store.json',{'v30_validation':[{'time':'old','company':'PSA','actual':9,'pred':10}]})
            put(new,'learning_store.json',{'v30_validation':[{'time':'new','company':'PSA','actual':10,'pred':10}]})
            put(old,'verification_history.json',{'version':1,'runs':[{'checked_at':'2026-01-01','checks':[]}]})
            put(new,'verification_history.json',{'version':1,'runs':[{'checked_at':'2026-08-22','checks':[]}]})
            put(old,'auto_repair_memory.json',{'version':1,'total_runs':5,'patterns':{},'files':{}});put(new,'auto_repair_memory.json',{'version':1,'total_runs':2,'patterns':{},'files':{}})
            put(old,'tcg_live_data.json',{'auto_update':{'last_run':'2026-08-21T12:00:00+09:00'}});put(new,'tcg_live_data.json',{'auto_update':{'last_run':'2026-08-22T12:00:00+09:00'},'keep':'new'})
            backup=migrate_old_data.migrate(old,new)
            learning=json.loads((new/'learning_store.json').read_text(encoding='utf-8'));history=json.loads((new/'verification_history.json').read_text(encoding='utf-8'))
            assert len(learning['v30_validation'])==2 and len(history['runs'])==2
            assert json.loads((new/'auto_repair_memory.json').read_text(encoding='utf-8'))['total_runs']==5
            assert json.loads((new/'tcg_live_data.json').read_text(encoding='utf-8'))['keep']=='new'
            assert (backup/'verification_history.json').exists()
        return '기존·신규 기록 병합 · 최신자료 선택 · 병합 전 백업'
    check('기존버전 자료 안전 이전',migration_safety,rows)
    def lan_selection():
        import tcg_updater
        assert tcg_updater.choose_lan_ip(['10.5.0.2','192.168.1.2'])=='192.168.1.2'
        assert tcg_updater.choose_lan_ip(['10.0.0.8'])=='10.0.0.8'
        assert tcg_updater.choose_lan_ip(['127.0.0.1'])=='127.0.0.1'
        return 'VPN 10.5.0.2보다 Wi-Fi 192.168.1.2 우선'
    check('휴대폰·태블릿 LAN 주소 선택',lan_selection,rows)
    def server_api():
        import tcg_updater
        original_learning=tcg_updater.LEARNING_STORE
        learning_tmp=tempfile.NamedTemporaryFile(suffix='.json',delete=False);learning_tmp.close();Path(learning_tmp.name).unlink(missing_ok=True)
        tcg_updater.LEARNING_STORE=learning_tmp.name
        server=tcg_updater.ThreadingHTTPServer(('127.0.0.1',0),tcg_updater.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            def get(path):
                with urllib.request.urlopen(base+path,timeout=5) as response:
                    return response.status,response.read().decode('utf-8')
            status,health=get('/api/health');health_body=json.loads(health)
            assert status==200 and health_body['ok'] and health_body['service']=='TCG v31 Updater'
            assert health_body['port']==8765 and health_body['api_version']==1 and health_body['platform']
            trusted=urllib.request.Request(base+'/api/health',headers={'Origin':'https://wlghks24.github.io'})
            with urllib.request.urlopen(trusted,timeout=5) as response:
                assert response.headers.get('Access-Control-Allow-Origin')=='https://wlghks24.github.io'
            untrusted=urllib.request.Request(base+'/api/health',headers={'Origin':'https://example.com'})
            with urllib.request.urlopen(untrusted,timeout=5) as response:
                assert response.headers.get('Access-Control-Allow-Origin') is None
            preflight=urllib.request.Request(base+'/api/health',headers={'Origin':'https://wlghks24.github.io','Access-Control-Request-Private-Network':'true'},method='OPTIONS')
            with urllib.request.urlopen(preflight,timeout=5) as response:
                assert response.status==204 and response.headers.get('Access-Control-Allow-Private-Network')=='true'
            status,watch=get('/api/market-watch');assert status==200 and len(json.loads(watch)['items'])>=3
            key=urllib.parse.quote('KR|계승되는 의지|BOX')
            status,price=get('/api/market-price?key='+key);body=json.loads(price)
            assert status==200 and body['found'] and body['price']['display']=='₩89,000'
            payload=json.dumps({'v30_validation':[{'time':'test','company':'PSA','actual':9,'pred':10}], 'v11_validation':[]}).encode('utf-8')
            request=urllib.request.Request(base+'/api/learning-store',data=payload,headers={'Content-Type':'application/json'},method='POST')
            with urllib.request.urlopen(request,timeout=5) as response: saved=json.loads(response.read().decode('utf-8'))
            assert saved['ok'] and saved['saved']==1
            status,learning=get('/api/learning-store');assert status==200 and len(json.loads(learning)['v30_validation'])==1
            status,page=get('/index.html');assert status==200 and 'BOX·박스' in page
            status,purchase=get('/purchase_sources.json');assert status==200 and len(json.loads(purchase)['sources'])>=20
            status,events=get('/promo_events.json');assert status==200 and len(json.loads(events)['items'])>=5
            status,auto_status=get('/api/auto-status');assert status==200 and isinstance(json.loads(auto_status),dict)
            status,report=get('/api/update-report');assert status==200 and isinstance(json.loads(report),dict)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3);tcg_updater.LEARNING_STORE=original_learning
            Path(learning_tmp.name).unlink(missing_ok=True);Path(learning_tmp.name+'.bak').unlink(missing_ok=True)
        return 'health·자동수집 상태·업데이트 보고·행사·구매처·학습 저장·화면 응답 정상'
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
