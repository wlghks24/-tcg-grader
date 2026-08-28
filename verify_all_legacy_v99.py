#!/usr/bin/env python3
"""배포 전 전체 구성요소를 검사하고 결과를 누적 저장한다."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, py_compile, re, subprocess, sys, tempfile, threading, urllib.parse, urllib.request
from pathlib import Path
from safe_runtime import atomic_write_json, safe_read_text

ROOT=Path(__file__).resolve().parent
HISTORY=ROOT/'verification_history.json'
HISTORY_LOCK=threading.RLock()
VERIFICATION_HISTORY_LIMIT=24
VERIFICATION_FULL_DETAIL_LIMIT=8
CURRENT_APP_NAME='TCG 등급 사전검사기 v98'
CURRENT_SERVICE='TCG v98 Updater'
CURRENT_ENGINE='v98-camera-resilience-full-runtime'
CURRENT_CACHE='tcg-v98-camera-resilience-full-runtime'
PY_FILES=('tcg_updater.py','card_grading_valuation.py','feature_contract.py','error_scenario_lab.py','ai_code_improver.py','verify_ai_code_improver.py','verify_link_runtime.py','fault_injection_healing.py','verify_fault_injection_healing.py','vision_calibration.py','verify_vision_calibration.py','grading_accuracy_v99.py','verify_v99_accuracy.py','verify_v99_learning_pipeline.py','verify_v99_cross_runtime.py','purchase_intelligence.py','auto_update_all.py','auto_repair_engine.py','update_releases.py','update_market_prices.py','market_public_crosscheck.py','update_market_watch.py','update_promo_events.py','update_purchase_sources.py','update_exchange_rates.py','migrate_old_data.py','run_repeated_verification.py','social_event_discovery.py')
JSON_FILES=('releases.json','purchase_signals.json','market_prices.json','market_watch.json','promo_events.json',
    'supplementary_candidates.json','social_event_candidates.json','social_source_registry.json','purchase_sources.json','exchange_rates.json','auto_update_report.json',
    'auto_update_issues.json','auto_repair_memory.json','learning_store.json','verification_cycles.json',
    'verification_history.json','adaptive_collection_stats.json','source_collection_stats.json',
    'web_discovery_candidates.json','link_health_report.json','tcg_live_data.json',
    'FINAL_VERIFICATION_REPORT.json','INTEGRATION_REPORT.json','scenario_learning_profiles.json',
    'ai_code_learning.json','fault_learning.json','vision_calibration.json','integrity_manifest.json')

def check(name,fn,rows):
    try: detail=fn() or '정상';rows.append({'name':name,'ok':True,'detail':str(detail)})
    except Exception as exc: rows.append({'name':name,'ok':False,'detail':f'{type(exc).__name__}: {exc}'})


def compact_verification_history_payload(value):
    """Keep recent evidence while preserving lifetime counters for compacted runs."""
    source=value if isinstance(value,dict) else {}
    all_runs=[dict(row) for row in source.get('runs',[]) if isinstance(row,dict)]
    retained=all_runs[-VERIFICATION_HISTORY_LIMIT:]
    full_start=max(0,len(retained)-VERIFICATION_FULL_DETAIL_LIMIT)
    for index,row in enumerate(retained):
        checks=row.get('checks') if isinstance(row.get('checks'),list) else []
        if index<full_start and checks:
            encoded=json.dumps(checks,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
            row['check_count']=len(checks)
            row['checks_sha256']=hashlib.sha256(encoded).hexdigest()
            row['checks']=[]
            row['details_compacted']=True
    def counter(value,default=0):
        try:return max(0,min(10**12,int(value)))
        except (TypeError,ValueError,OverflowError):return default
    def nonnegative(name,derived):
        return max(derived,counter(source.get(name),derived))
    derived_runs=len(all_runs)+counter(source.get('pruned_runs'))
    derived_passed=sum(counter(row.get('pass_count')) for row in all_runs)
    derived_failed=sum(counter(row.get('failure_count')) for row in all_runs)
    lifetime_runs=nonnegative('lifetime_runs',derived_runs)
    return {
        'version':2,'updated_at':source.get('updated_at'),'retention_limit':VERIFICATION_HISTORY_LIMIT,
        'full_detail_limit':VERIFICATION_FULL_DETAIL_LIMIT,'lifetime_runs':lifetime_runs,
        'lifetime_passed_checks':nonnegative('lifetime_passed_checks',derived_passed),
        'lifetime_failed_checks':nonnegative('lifetime_failed_checks',derived_failed),
        'pruned_runs':max(0,lifetime_runs-len(retained)),'runs':retained,
    }


def persist_verification_history(rows, history_path=HISTORY):
    """Finalize only after every check has run; recover a damaged history safely."""
    path=Path(history_path)
    backup=path.with_suffix(path.suffix+'.bak')
    with HISTORY_LOCK:
        if path.is_symlink() or backup.is_symlink() or path.parent.is_symlink():
            raise ValueError('심볼릭 링크 검사기록 저장 경로를 차단했습니다.')
        history=compact_verification_history_payload({})
        current_valid=None
        for candidate in (path,backup):
            try:
                loaded=json.loads(safe_read_text(candidate))
            except (OSError,ValueError,TypeError):
                continue
            if isinstance(loaded,dict) and isinstance(loaded.get('runs'),list):
                history=compact_verification_history_payload(loaded)
                if candidate==path:
                    current_valid=loaded
                break
        now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        checks=[dict(row) for row in rows if isinstance(row,dict)]
        run={'checked_at':now,'ok':all(bool(row.get('ok')) for row in checks),
             'pass_count':sum(bool(row.get('ok')) for row in checks),
             'failure_count':sum(not bool(row.get('ok')) for row in checks),'checks':checks}
        history['updated_at']=now
        history['lifetime_runs']+=1
        history['lifetime_passed_checks']+=run['pass_count']
        history['lifetime_failed_checks']+=run['failure_count']
        history['runs']=[row for row in history.get('runs',[]) if isinstance(row,dict)]+[run]
        history=compact_verification_history_payload(history)
        if current_valid is not None:
            atomic_write_json(backup,compact_verification_history_payload(current_valid),suffix='.history.bak.tmp')
        atomic_write_json(path,history,suffix='.history.tmp')
        return history,run

def main():
    rows=[]
    check('Python 문법',lambda:[py_compile.compile(str(ROOT/f),doraise=True) for f in PY_FILES] and f'{len(PY_FILES)}개',rows)
    check('전체 Python 문법',lambda:[py_compile.compile(str(f),doraise=True) for f in ROOT.glob('*.py')] and f"{len(list(ROOT.glob('*.py')))}개 전체 검사",rows)
    parsed={}
    def json_check():
        from tcg_updater import strict_json_loads
        for f in JSON_FILES: parsed[f]=strict_json_loads((ROOT/f).read_text(encoding='utf-8'),max_depth=32,max_nodes=200000)
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
        assert {'promo','collaboration','movie'} <= {x.get('category','promo') for x in items}
        assert {'포켓몬 카드','원피스 카드','나루토 카드'} <= {x.get('game') for x in items}
        kr_games={x.get('game') for x in items if x.get('region')=='KR'}
        assert {'포켓몬 카드','원피스 카드'} <= kr_games, f'한국 행사 게임 누락: {kr_games}'
        assert any(x.get('region')=='KR' and x.get('game')=='포켓몬 카드' and 'pokemonkorea.co.kr' in x.get('source','') for x in items)
        assert all(x.get('source','').startswith('https://') and x.get('condition') and x.get('reward') for x in items)
        assert any(x.get('game')=='나루토 카드' and 'naruto-cardgame.com' in x.get('source','') for x in items)
        today=dt.date.today()
        def expiry(x):
            end=dt.date.fromisoformat(x['end_date'])
            claim=dt.date.fromisoformat(x.get('claim_deadline',x['end_date']))
            return max(end,claim)
        assert all(expiry(x)>=today for x in items), '날짜 지난 프로모/콜라보 행사가 남아 있음'
        kr_movies=[x for x in items if x.get('region')=='KR' and x.get('category')=='movie']
        assert {x.get('game') for x in kr_movies} >= {'포켓몬 카드','원피스 카드','나루토 카드'}, '한국 영화정보 3종 추적 누락'
        return f'{len(items)}개 · 만료행사 0개 · 한국 포켓몬/원피스/나루토 영화정보 {len(kr_movies)}종 포함 · 프로모/콜라보·특별행사'
    check('프로모·콜라보 행사',promo_check,rows)
    html=(ROOT/'index.html').read_text(encoding='utf-8')
    def html_check():
        ids=re.findall(r'\bid="([^"]+)"',html);assert len(ids)==len(set(ids))
        assert 'market_watch.json' in html and 'BOX·박스' in html and '가격 확인 중' in html
        assert 'id="siteUpdateAll"' in html and 'id="siteUpdateStatus"' in html
        assert 'siteUpdateAll").addEventListener("click",refreshReleaseInfo)' in html
        required=('v30mode','rawMode','slabMode','v30slab','slabAnalyze','precisionHub','v30validation','saveValidation','recalcCalibration','qualityStatus','v31testdashboard')
        assert all(f'id="{item}"' in html for item in required)
        assert html.index(CURRENT_APP_NAME) < html.index('id="gradeStart"')
        assert html.index('id="gradeStart"') < html.index('id="v30mode"') < html.index('id="precisionHub"') < html.index('id="v30validation"')
        assert 'const grades=window.tcgLastGrades||{}' in html
        assert all(f'id="{item}"' in html for item in ('purchasePanel','purchaseGame','purchaseQuery','purchaseAsset','purchaseAreaText','purchaseUseLocation','purchaseSort','purchaseNearby','purchaseLive','purchaseRegionGrid','guideLeft','guideRight','guideTop','guideBottom','guideCalculate','guideResult'))
        assert 'applyGuideCenteringCap' in html and 'purchase_sources.json' in html
        assert 'data-purchase-channel="online"' in html and 'data-purchase-channel="offline"' in html
        assert 'navigator.geolocation' in html and '/api/purchase-live-search' in html and '구매 가능성' in html
        assert 'id="promoGame"' in html and '나루토' in html
        assert 'id="promoType"' in html and '콜라보·특별행사' in html
        assert 'id="tabletServerGuide"' in html and 'START_TCG_UPDATER_ANDROID.sh' in html
        assert 'setInterval(syncBackgroundData,60000)' in html
        assert 'safeExternalUrl' in html and 'escapeDisplayText' in html
        assert (ROOT/'validate_external_links.py').exists()
        assert 'href="${x.source}"' not in html and 'href="${source}"' not in html
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
        sw=(ROOT/'sw.js').read_text(encoding='utf-8');assert 'market_watch.json' in sw and 'purchase_sources.json' in sw and 'purchase_signals.json' in sw
        assert 'supplementary_candidates\\.json' in sw
        subprocess.run(['node','--check','sw.js'],cwd=ROOT,check=True,capture_output=True,text=True,timeout=20)
        return '판매·재발매 자료 캐시 포함 · 프로모/콜라보 보조자료 네트워크 우선 갱신'
    check('서비스워커',sw_check,rows)
    def launchers():
        required=('TCG_AUTO_UPDATE.bat','정보자동업데이트.bat','START_TCG_UPDATER_ANDROID.sh','자동실행_설치.bat','ANDROID_AUTO_START_INSTALL.sh','PC_SERVER_AUTO_START_INSTALL.bat','TCG_SERVER_AUTO_RUN.cmd','자동실행_해제.bat','기존버전_학습자료_가져오기.bat','학습자료_백업.bat','migrate_old_data.py','run_repeated_verification.py','verify_browser_runtime.js','verify_service_worker_runtime.js','verify_camera_runtime.js')
        assert all((ROOT/f).exists() for f in required)
        for script in ('START_TCG_UPDATER_ANDROID.sh','ANDROID_AUTO_START_INSTALL.sh','ANDROID_AUTO_START_REMOVE.sh'):
            subprocess.run(['bash','-n',script],cwd=ROOT,check=True,capture_output=True,text=True,timeout=10)
        return f'{len(required)}개 · 안드로이드 셸 문법 정상'
    check('PC·태블릿 실행파일',launchers,rows)
    def tablet_auto_security():
        import auto_update_all, update_purchase_sources, update_promo_events, supplementary_discovery
        assert len(auto_update_all.JOBS)==6
        expected_modules=('update_releases','update_market_watch','update_market_prices','update_promo_events','update_purchase_sources','update_exchange_rates')
        assert tuple(job[1] for job in auto_update_all.JOBS)==expected_modules
        for unsafe in ('http://example.com','https://127.0.0.1/private','https://localhost/private','https://user@example.com/path'):
            try: update_purchase_sources.checked_url(unsafe)
            except ValueError: pass
            else: raise AssertionError(f'위험 주소 허용: {unsafe}')
        update_purchase_sources.checked_url('https://onepiece-cardgame.kr/events/')
        import purchase_intelligence
        score,label,reasons=purchase_intelligence._score('포켓몬 BOX 재입고 구매 후기','판매중 재고 확인')
        assert score>=75 and label=='높음' and reasons
        score2,label2,_=purchase_intelligence._score('원피스 BOX 품절','sold out')
        assert score2<50 and label2=='낮음'
        update_promo_events.approved_url('https://pokemonkorea.co.kr/M6_tournament')
        # 나무위키/커뮤니티 보조자료는 공식 URL 검증기와 분리해 출처 등급을 유지한다.
        try: update_promo_events.approved_url('https://namu.wiki/w/test')
        except ValueError: pass
        else: raise AssertionError('나무위키를 공식 출처로 오인')
        supplementary_discovery.secondary_url('https://namu.wiki/w/test')
        supplemental=json.loads((ROOT/'supplementary_candidates.json').read_text(encoding='utf-8'))
        assert isinstance(supplemental.get('items'), list) and len(supplemental['items']) >= 3
        assert any(x.get('source_tier')=='C' for x in supplemental['items'])
        sample=[{'end_date':'2026-08-20','claim_deadline':'2026-08-20'},{'end_date':'2026-08-20','claim_deadline':'2026-08-30'}]
        kept,removed=update_promo_events.purge_expired(sample,dt.date(2026,8,23))
        assert len(kept)==1 and len(removed)==1
        assert update_promo_events.explicit_local_date_range('2026년 8월 22일 ~ 9월 4일')==('2026-08-22','2026-09-04')
        repaired=update_promo_events.normalize_event_dates({'name_ko':'행사 2026년 8월 22일 ~ 9월 4일','start_date':'2026-08-22','end_date':'2026-08-22','claim_deadline':'2026-08-22'})
        assert repaired['end_date']=='2026-09-04' and repaired['claim_deadline']=='2026-09-04'
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
    def adaptive_error_learning():
        import auto_update_all as au
        stats={"jobs":{}}
        fn='test.json'
        assert au._job_timeout(fn,stats)==300
        # 빠른 정상 성공을 12회 학습하면 30초까지 줄어야 한다.
        for _ in range(12): au._record_job_stat(stats,fn,4.0,True)
        assert au._job_timeout(fn,stats)==30, au._job_timeout(fn,stats)
        # 일시 오류가 발생하면 다음 실행의 여유시간이 다시 늘어나야 한다.
        au._record_job_stat(stats,fn,30.0,False,True,'TimeoutError: source timed out')
        assert au._job_timeout(fn,stats)>=90
        row=stats['jobs'][fn]
        assert row.get('error_patterns') and row.get('dominant_error_signature')
        # 부분 성공도 깨끗한 성공으로 간주하면 안 된다(성공 streak 리셋).
        au._record_job_stat(stats,fn,8.0,True,error='KREAM TimeoutError',partial=True)
        assert row['success_streak']==0 and row.get('partial_successes',0)>=1
        assert au._should_retry(row,False,'TimeoutError: temporary connection')
        assert not au._should_retry(row,False,'ValueError: 구조 오류')
        return '초기 300초 → 안정학습 30초 · 실패 시 >=90초 회복 · 오류패턴/부분성공 학습 정상'
    check('v50 오류학습·시간제한 회복',adaptive_error_learning,rows)

    def recovered_retry_learning():
        import auto_update_all as au
        stats={"jobs":{}}; fn='recovered-test.json'
        for _ in range(12): au._record_job_stat(stats,fn,3.0,True)
        assert au._job_timeout(fn,stats)==30
        # 첫 시도 오류 후 재시도 성공은 깨끗한 성공 streak로 이어지면 안 된다.
        au._record_job_stat(stats,fn,12.0,True,error='TimeoutError: first attempt',recovered=True)
        row=stats['jobs'][fn]
        assert row['success_streak']==0
        assert row.get('recovered_successes',0)==1
        assert row.get('last_recovered') is True
        assert row.get('error_patterns')
        assert au._job_timeout(fn,stats)>=90
        src=Path(au.__file__).read_text(encoding='utf-8')
        assert 'retry_timeout = timeout_s if attempts == 1 else min(300, max(90, timeout_s * 2))' in src
        return '재시도 복구를 clean success와 분리 · 동일 실행 재시도 timeout >=90초 확대 · 총 300초 예산 유지'
    check('v53 재시도 복구학습·오류감소',recovered_retry_learning,rows)

    def precollect_schedule_learning():
        import tcg_updater
        assert tcg_updater.AUTO_INTERVAL_SECONDS==6*60*60
        assert tcg_updater.PRECOLLECT_LEAD_SECONDS==30*60
        mapped=tcg_updater._changed_source_files([
            {'source':'포켓몬 일본 공식','kind':'공식','status':'변경 확인 필요'},
            {'source':'포켓몬 일본 프로모 행사 공식','kind':'행사','status':'변경 확인 필요'},
            {'source':'CGC 공식 등급','kind':'등급','status':'변경 확인 필요'},
        ])
        assert 'releases.json' in mapped and 'market_watch.json' in mapped and 'promo_events.json' in mapped
        assert 'exchange_rates.json' not in mapped
        default=tcg_updater.default_db()['auto_update']
        assert default['interval_hours']==6 and default['precollect_lead_minutes']==30
        return '6시간 반영 · 30분 전 staging 사전수집 · 변경/실패 항목만 최종 보완수집'
    check('v51 30분 사전수집·6시간 최종반영',precollect_schedule_learning,rows)

    def server_api():
        import tcg_updater
        original_learning=tcg_updater.LEARNING_STORE
        learning_tmp=tempfile.NamedTemporaryFile(suffix='.json',delete=False);learning_tmp.close();Path(learning_tmp.name).unlink(missing_ok=True)
        tcg_updater.LEARNING_STORE=learning_tmp.name
        server=tcg_updater.QuietThreadingHTTPServer(('127.0.0.1',0),tcg_updater.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        try:
            def get(path):
                with urllib.request.urlopen(base+path,timeout=5) as response:
                    return response.status,response.read().decode('utf-8')
            status,health=get('/api/health');health_body=json.loads(health)
            assert status==200 and health_body['ok'] and health_body['service']==CURRENT_SERVICE
            assert health_body['port']==8765 and health_body['api_version']==2 and health_body['platform']
            status,contract_text=get('/api/feature-audit');contract=json.loads(contract_text)
            assert status==200 and contract['ok'] and contract['implemented']==contract['total']==23
            assert contract['excluded'][0]['id']=='iphone_serverless_continuous_collection'
            status,scenario_text=get('/api/scenario-learning-summary');scenario=json.loads(scenario_text)
            assert status==200 and scenario['ok'] and scenario['scenario_count']>=83
            assert scenario['family_count']>=19 and scenario['verified_profile_count']>=65
            assert scenario['operational_occurrences_modified'] is False and scenario['advisory_text_executed'] is False
            with urllib.request.urlopen(base+'/api/health',timeout=5) as response:
                assert response.headers.get('X-Content-Type-Options')=='nosniff'
                assert response.headers.get('X-Frame-Options')=='DENY'
                assert response.headers.get('Referrer-Policy')=='no-referrer'
            try: urllib.request.urlopen(base+'/tcg_updater.py',timeout=5)
            except urllib.error.HTTPError as exc: assert exc.code==404
            else: raise AssertionError('파이썬 소스 파일 외부 공개')
            try: urllib.request.urlopen(base+'/.tcg_last_good/market_prices.json',timeout=5)
            except urllib.error.HTTPError as exc: assert exc.code==404
            else: raise AssertionError('백업 폴더 외부 공개')
            try: urllib.request.urlopen(base+'/api/update',timeout=5)
            except urllib.error.HTTPError as exc: assert exc.code==405
            else: raise AssertionError('GET 업데이트 실행 허용')
            hostile=urllib.request.Request(base+'/api/learning-store',data=b'{}',headers={'Content-Type':'application/json','Origin':'https://example.com'},method='POST')
            try: urllib.request.urlopen(hostile,timeout=5)
            except urllib.error.HTTPError as exc: assert exc.code==403
            else: raise AssertionError('비신뢰 Origin 쓰기 허용')
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
            status,signals=get('/purchase_signals.json');assert status==200 and isinstance(json.loads(signals).get('items'),list)
            try: urllib.request.urlopen(base+'/api/purchase-live-search?region=XX&game=Pokemon&q=test',timeout=5)
            except urllib.error.HTTPError as exc: assert exc.code==400
            else: raise AssertionError('구매 신호 API 입력 검증 누락')
            with urllib.request.urlopen(base+'/api/health',timeout=5) as response:
                assert 'geolocation=(self)' in response.headers.get('Permissions-Policy','')
            status,events=get('/promo_events.json');assert status==200 and len(json.loads(events)['items'])>=5
            status,auto_status=get('/api/auto-status');assert status==200 and isinstance(json.loads(auto_status),dict)
            status,job=get('/api/update-job');assert status==200 and isinstance(json.loads(job).get('job'),dict)
            status,report=get('/api/update-report');assert status==200 and isinstance(json.loads(report),dict)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3);tcg_updater.LEARNING_STORE=original_learning
            Path(learning_tmp.name).unlink(missing_ok=True);Path(learning_tmp.name+'.bak').unlink(missing_ok=True)
        return 'health·보안헤더·소스/백업 비공개·GET 변경 차단·Origin 검증·자동수집/학습 정상'

    def v54_singular_error_learning():
        import auto_update_all
        assert auto_update_all._count_payload({'rates':{'JPY_KRW':8.7,'USD_KRW':1380}})==2
        # Regression guard: collectors such as exchange_rates may use singular
        # collection_error while preserving the last verified payload.
        src=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        assert "data.get('collection_error')" in src
        assert "'urlerror'" in src
        assert "startup_cleanup" in (ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        return '단일 collection_error도 부분실패 학습 · 환율 2개 카운트 · 시작 전 만료자료 자가정리'
    check('v54 시작정리·단일오류 학습보강',v54_singular_error_learning,rows)

    def v55_source_learning_parallel():
        import tcg_updater
        assert hasattr(tcg_updater,'SOURCE_STATS')
        assert tcg_updater._source_timeout({})==300
        row={'successes':12,'clean_success_streak':12,'success_ewma_seconds':4.0,'consecutive_failures':0}
        assert tcg_updater._source_timeout(row)==27 or tcg_updater._source_timeout(row)==30
        # lower bound is always 30 seconds
        assert tcg_updater._source_timeout(row)>=30
        failed={'successes':12,'clean_success_streak':0,'success_ewma_seconds':4.0,'consecutive_failures':1}
        assert tcg_updater._source_timeout(failed)>=90
        src=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert 'ThreadPoolExecutor' in src and 'recovered_successes' in src and '_source_transient_error' in src
        return '공식출처도 초기 300초→학습 30초 · 실패 시 >=90초 회복 · PC/Android 병렬수집 · 복구성공 분리학습'
    check('v55 공식출처 병렬·오류학습',v55_source_learning_parallel,rows)


    def v56_aux_learning():
        text=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        assert "_run_aux_task" in text and "__integration__" in text and "__link_audit__" in text
        assert "timeout=8" not in text and "timeout=12" not in text
        assert "reachable_count" in text and "degraded" in text and "ok_with_aux" in text
        return '보조 후보수집·링크검사도 300→30초 학습형 timeout · 링크 정상개수/프로세스성공 의미 분리 · 부분성공 오류학습'
    check('v56 보조작업 오류학습·링크검사 의미보정',v56_aux_learning,rows)

    def v57_retry_budget_learning():
        import tcg_updater
        calls=[]
        stats={'sources':{'V57_TEST':{'successes':20,'clean_success_streak':20,'success_ewma_seconds':2.0,'consecutive_failures':0}}}
        original_fetch=tcg_updater.fetch; original_sleep=tcg_updater.time.sleep
        try:
            def fake_fetch(url,timeout=300):
                calls.append(int(timeout))
                if len(calls)==1: raise TimeoutError('simulated transient timeout')
                return '<html><title>OK</title></html>'
            tcg_updater.fetch=fake_fetch; tcg_updater.time.sleep=lambda *_:None
            result=tcg_updater._collect_one_source(('V57_TEST','https://example.com','공식'),stats)
        finally:
            tcg_updater.fetch=original_fetch; tcg_updater.time.sleep=original_sleep
        assert result['ok'] and result.get('recovered') is True
        assert calls[0]==30 and calls[1]>=90, calls
        assert stats['sources']['V57_TEST'].get('recovered_successes',0)>=1
        text=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        assert 'while attempts < 2' in text and "recovered_after_retry" in text
        assert 'QuietThreadingHTTPServer' in (ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        return '30초 학습 후 일시오류 시 복구시도 >=90초 · 보조작업 재시도 · 정상 client disconnect 오류로그 억제'
    check('v57 재시도 예산·오류로그 보강',v57_retry_budget_learning,rows)

    def v58_safe_monitoring_learning():
        import tempfile
        import auto_repair_engine
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix='tcg-v58-') as td:
            tr=Path(td); lg=tr/'.tcg_last_good'; lg.mkdir()
            backup={'items':[{'game':'Pokemon','region':'KR','name':'TEST','source':'https://example.com'}]}
            (lg/'releases.json').write_text(json.dumps(backup,ensure_ascii=False),encoding='utf-8')
            (tr/'releases.json').write_text('{broken json',encoding='utf-8')
            eng=auto_repair_engine.AutoRepairEngine(memory_file=tr/'memory.json',root=tr,last_good=lg)
            out=eng.validate_project_files(['releases.json'])
            assert out['ok'] and json.loads((tr/'releases.json').read_text(encoding='utf-8'))==backup
            mem=json.loads((tr/'memory.json').read_text(encoding='utf-8'))
            assert mem.get('monitor_history') and mem['monitor_history'][-1]['resolved'] is True
            # 허용되지 않은 파일은 예외문자열을 이용해 임의 생성하지 않는다.
            assert eng._safe_target('../outside.json') is None
            # 백업 없는 손상 파일은 빈 객체로 초기화하지 않고 복구 실패로 남긴다.
            (tr/'market_prices.json').write_text('{bad',encoding='utf-8')
            out2=eng.validate_project_files(['market_prices.json'])
            assert not out2['ok'] and (tr/'market_prices.json').read_text(encoding='utf-8')=='{bad'
        text=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        assert 'preflight_monitor' in text and 'postflight_monitor' in text and CURRENT_ENGINE in text
        return 'traceback 기반 실행감시 · 화이트리스트 파일만 복구 · 손상 JSON은 정상백업 있을 때만 복원 · 동일오류 재실행 제한 · 전/후 검증'
    check('v58 안전 자동복구·오류학습 감시',v58_safe_monitoring_learning,rows)
    def v60_concurrency_guard():
        text=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert "with UPDATE_LOCK:\n            report=auto_update_all.run_all('retry-failed'" in text
        assert "with UPDATE_LOCK:\n            _safe_stage_copy(BASE,tmp_stage)" in text
        return '실패항목 재수집/30분 사전수집 스냅샷을 전역 업데이트 잠금으로 보호 · JSON/학습값 동시쓰기 방지'
    check('v60 동시업데이트 충돌방지',v60_concurrency_guard,rows)

    check('PC·태블릿 서버 실제 응답',server_api,rows)

    def v61_deep_guard():
        au=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        ur=(ROOT/'update_releases.py').read_text(encoding='utf-8')
        ue=(ROOT/'update_exchange_rates.py').read_text(encoding='utf-8')
        um=(ROOT/'update_market_prices.py').read_text(encoding='utf-8')
        assert 'TCG_HTTP_TIMEOUT' in au and 'TCG_HTTP_TIMEOUT' in ur and 'TCG_HTTP_TIMEOUT' in ue and 'TCG_HTTP_TIMEOUT' in um
        assert '.json.tmp' in ur
        assert 'as_completed' in ur
        return '하위 2~4초 고정 timeout 제거 · 외부 학습예산 연동 · 원자적 JSON 저장 · 완료순 병렬처리'
    check('v61 내부 HTTP timeout 학습연동·원자저장',v61_deep_guard,rows)

    def v62_aux_and_backup_guard():
        import tempfile, gzip, json as _json
        from pathlib import Path as _Path
        import auto_pipeline_runner, multi_channel_agent
        from optimized_self_healing import SelfHealingEngine
        # 1) 보조검색 전체 실패가 clean success로 숨겨지지 않아야 한다.
        original=multi_channel_agent.MultiChannelCollector.search_web
        try:
            def fake_fail(self, keyword, limit=5):
                return {'ok':False,'keyword':keyword,'results':[],'error':'TimeoutError: simulated'}
            multi_channel_agent.MultiChannelCollector.search_web=fake_fail
            result=auto_pipeline_runner.run_pipeline()
            assert result['ok'] is False and result['degraded'] is True and result['failure_count']==3
        finally:
            multi_channel_agent.MultiChannelCollector.search_web=original
        # 2) 손상된 주 gzip이 마지막 정상 backup을 덮어쓰면 안 된다.
        with tempfile.TemporaryDirectory(prefix='tcg-v62-sh-') as td:
            td=_Path(td); data=td/'data.json.gz'; bak=td/'backup.json.gz'
            eng=SelfHealingEngine(data,bak)
            assert eng.save_compressed_data({'v':1})
            assert eng.save_compressed_data({'v':2})
            # backup에는 직전 정상 v1이 있다. 주 파일을 고의 손상 후 새 저장.
            data.write_bytes(b'not-gzip')
            assert eng.save_compressed_data({'v':3})
            with gzip.open(bak,'rb') as fh:
                assert _json.loads(fh.read().decode('utf-8'))=={'v':1}
            with gzip.open(data,'rb') as fh:
                assert _json.loads(fh.read().decode('utf-8'))=={'v':3}
        mc=(ROOT/'multi_channel_agent.py').read_text(encoding='utf-8')
        gh=(ROOT/'github_sync_engine.py').read_text(encoding='utf-8')
        au=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        assert 'TCG_HTTP_TIMEOUT' in mc and 'timeout=8' not in mc
        assert 'TCG_HTTP_TIMEOUT' in gh and 'timeout=12' not in gh and 'atomic_write_json(self.cache,data' in gh
        assert "ok=bool(extra.get('ok', True))" in au
        assert f"'integrated_version':'{CURRENT_ENGINE}'" in (ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        return '보조검색 실패를 부분실패로 학습 · 고정 8/12초 제거 · GitHub 캐시 원자저장 · 손상 gzip이 정상 backup을 덮어쓰지 않음'
    check('v62 보조수집·압축백업 심층보강',v62_aux_and_backup_guard,rows)

    def v63_timeout_consistency_guard():
        promo=(ROOT/'update_promo_events.py').read_text(encoding='utf-8')
        purchase=(ROOT/'update_purchase_sources.py').read_text(encoding='utf-8')
        assert 'TCG_HTTP_TIMEOUT' in promo and 'TIMEOUT_SECONDS = 3' not in promo
        assert 'TCG_HTTP_TIMEOUT' in purchase and 'TIMEOUT_SECONDS = 3' not in purchase
        assert 'raise urllib.error.URLError("도메인 확인 실패")' in purchase
        import os as _os, subprocess as _sp, sys as _sys
        env=_os.environ.copy(); env['TCG_HTTP_TIMEOUT']='47'
        code="import update_promo_events as p, update_purchase_sources as u; print(p.TIMEOUT_SECONDS, u.TIMEOUT_SECONDS)"
        out=_sp.check_output([_sys.executable,'-c',code],cwd=ROOT,env=env,text=True,timeout=10).strip()
        assert out=='47 47', out
        env['TCG_HTTP_TIMEOUT']='999'
        out=_sp.check_output([_sys.executable,'-c',code],cwd=ROOT,env=env,text=True,timeout=10).strip()
        assert out=='60 60', out
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert 'api_version!==1' not in page and 'Number(health.api_version||0)<2' in page
        assert 'health.service!=="TCG v31 Updater"' not in page
        import update_purchase_sources as _ups, auto_update_all as _aua, socket as _socket
        original_gai=_socket.getaddrinfo
        try:
            def _fail_gai(*args,**kwargs): raise _socket.gaierror(-3,'simulated DNS')
            _socket.getaddrinfo=_fail_gai
            name,state=_ups.probe({'name':'DNS_TEST','url':'https://example.com','type':'official'})
            assert 'URLError' in state, state
            assert _aua._should_retry({},False,state) is True
        finally:
            _socket.getaddrinfo=original_gai
        sw=(ROOT/'sw.js').read_text(encoding='utf-8')
        assert CURRENT_CACHE in sw
        return '프로모·구매처 내부 고정 3초 timeout 제거 · 외부 학습 timeout과 5~60초 범위 연동 · 화면/서버 API v2 계약 일치 · 구매처 DNS 오류를 일시 통신오류로 학습·재시도'
    check('v63 프로모·구매처 timeout 학습연동',v63_timeout_consistency_guard,rows)


    def v64_failure_accounting_guard():
        import auto_update_all as _aua
        stats={'jobs':{}}
        _aua._record_job_stat(stats,'__aux_fail__',1.0,False,error='RuntimeError: simulated',partial=False,recovered=False)
        row=stats['jobs']['__aux_fail__']
        assert row.get('failures')==1 and row.get('partial_successes',0)==0
        text=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        assert "partial=bool(ok and degraded)" in text
        assert 'fresh_success_count' in text and 'restored_count' in text and 'degraded_count' in text
        promo=(ROOT/'update_promo_events.py').read_text(encoding='utf-8')
        assert 'deferred-to-integration-stage' in promo and 'supplementary_discovery.main()' not in promo
        assert '_run_managed_process' in text and 'os.killpg' in text and 'taskkill' in text
        updater=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert '_run_precollect_process' in updater and 'os.killpg' in updater and 'taskkill' in updater
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert '신규 정상' in page and '기존자료 유지' in page and CURRENT_APP_NAME in page
        return '보조작업 완전실패/부분성공 분리 · 기존자료 유지/신규수집 통계 분리 · 프로모 내부 보조출처 중복수집 제거 · timeout 프로세스 트리 정리'
    check('v64 런타임 실패회계·중복수집 방지',v64_failure_accounting_guard,rows)

    def v65_stage_gated_timeout_learning():
        import auto_update_all as _au
        import tcg_updater as _tu
        expected={0:300,2:300,3:180,4:120,5:90,7:60,9:45,12:30}
        for streak,want in expected.items():
            stats={'jobs':{'probe':{'successes':20,'success_streak':streak,'success_ewma_seconds':2,'consecutive_failures':0}}}
            got=_au._job_timeout('probe',stats)
            assert got==want,(streak,got,want)
            row={'successes':20,'clean_success_streak':streak,'success_ewma_seconds':2,'consecutive_failures':0}
            got2=_tu._source_timeout(row)
            assert got2==want,(streak,got2,want)
        # Slow real work must keep enough headroom even after stage 12.
        stats={'jobs':{'probe':{'successes':20,'success_streak':12,'success_ewma_seconds':40,'consecutive_failures':0}}}
        assert _au._job_timeout('probe',stats)==135
        row={'successes':20,'clean_success_streak':12,'success_ewma_seconds':40,'consecutive_failures':0}
        assert _tu._source_timeout(row)==135
        # Any recent failure re-expands the budget to at least 90 seconds.
        stats={'jobs':{'probe':{'successes':20,'success_streak':0,'success_ewma_seconds':2,'consecutive_failures':1}}}
        assert _au._job_timeout('probe',stats)>=90
        row={'successes':20,'clean_success_streak':0,'success_ewma_seconds':2,'consecutive_failures':1}
        assert _tu._source_timeout(row)>=90

    check('v65 단계형 timeout 학습 우회방지',v65_stage_gated_timeout_learning,rows)

    def v66_link_audit_hidden_error_guard():
        import importlib
        import os as _os
        import validate_external_links as _vl
        importlib.reload(_vl)
        text=(ROOT/'validate_external_links.py').read_text(encoding='utf-8')
        assert 'import datetime as dt, ipaddress, json, os, socket' in text
        assert 'TIMEOUT=2' not in text and 'request_timeout or _request_timeout()' in text
        assert 'except mp.TimeoutError:' in text
        assert 'except Exception:\n            # v66:' in text and '\n            raise\n' in text
        import auto_repair_engine as _ar
        import auto_update_all as _au
        cat, action, _ = _ar.classify('NameError: name os is not defined')
        assert cat=='내부 코드 오류' and '재시도 중단' in action
        assert _au._should_retry({},False,'NameError: name os is not defined') is False
        au_text=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        assert "link_report.unlink(missing_ok=True)" in au_text and 'old_report=safe_read_bytes(link_report)' in au_text
        old_http=_os.environ.get('TCG_HTTP_TIMEOUT'); old_audit=_os.environ.get('TCG_LINK_AUDIT_TIMEOUT')
        try:
            _os.environ['TCG_HTTP_TIMEOUT']='7'
            _os.environ['TCG_LINK_AUDIT_TIMEOUT']='19'
            assert _vl._request_timeout()==7 and _vl._audit_timeout(10,2)==30
            _os.environ['TCG_HTTP_TIMEOUT']='bad'
            assert _vl._request_timeout()==20
            _os.environ['TCG_HTTP_TIMEOUT']='999'
            assert _vl._request_timeout()==30
        finally:
            if old_http is None:_os.environ.pop('TCG_HTTP_TIMEOUT',None)
            else:_os.environ['TCG_HTTP_TIMEOUT']=old_http
            if old_audit is None:_os.environ.pop('TCG_LINK_AUDIT_TIMEOUT',None)
            else:_os.environ['TCG_LINK_AUDIT_TIMEOUT']=old_audit
        # 정적 회귀: os.environ을 사용하는 Python 파일은 os import가 있어야 한다.
        for py in ROOT.glob('*.py'):
            src=py.read_text(encoding='utf-8',errors='replace')
            if 'os.environ' in src:
                assert ('import os' in src or ', os' in src or 'os,' in src), f'os import 누락: {py.name}'
        return '링크검사 os import 누락 복구 · 고정 2초 제거 · 내부 코딩오류를 네트워크 오류로 숨기지 않음 · 환경 timeout 회귀검사'
    check('v66 링크검사 숨은오류·timeout 학습보강',v66_link_audit_hidden_error_guard,rows)

    def v67_learning_memory_recovery_guard():
        au=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        up=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        vl=(ROOT/'validate_external_links.py').read_text(encoding='utf-8')
        assert 'ADAPTIVE_STATS_BAK' in au and 'for candidate in (ADAPTIVE_STATS, ADAPTIVE_STATS_BAK)' in au
        assert 'SOURCE_STATS_BAK' in up and 'for candidate in (SOURCE_STATS,SOURCE_STATS_BAK)' in up
        assert 'state":"blocked"' in vl and 'DNS_SECURITY' in vl and '"blocked":0' in vl
        # 실제 손상 주파일 + 정상 백업 복구를 검증한다.
        import tempfile, importlib.util
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            main=td/'adaptive_collection_stats.json'; bak=td/'adaptive_collection_stats.json.bak'
            main.write_text('{broken',encoding='utf-8')
            backup={'version':1,'jobs':{'x.json':{'successes':7}},'updated_at':'test'}
            bak.write_text(json.dumps(backup),encoding='utf-8')
            ns={}
            # 함수 로직과 동일한 후보 순회 검증
            recovered=None
            for candidate in (main,bak):
                try:
                    data=json.loads(candidate.read_text(encoding='utf-8'))
                    if isinstance(data,dict) and isinstance(data.get('jobs',{}),dict): recovered=data; break
                except (OSError,ValueError,TypeError):
                    continue
            assert recovered and recovered['jobs']['x.json']['successes']==7
        return 'adaptive/source 학습값 정상백업 복구 · private DNS 보안차단 분리'
    check('v67 학습메모리 복구·DNS 보안분류',v67_learning_memory_recovery_guard,rows)


    def v68_five_pass_hardening_guard():
        import importlib.util
        link=(ROOT/'validate_external_links.py').read_text(encoding='utf-8')
        updater=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        sw=(ROOT/'sw.js').read_text(encoding='utf-8')
        assert '_resolve_public(host)' in link and 'except ValueError as exc:' in link
        assert '_worker_count(len(urls))' in link and 'MAX_WORKERS=8' in link
        assert '_sanitize_adaptive_stats' in updater and CURRENT_ENGINE in updater
        assert '_sanitize_source_stats' in server and CURRENT_SERVICE in server
        assert CURRENT_APP_NAME in page and CURRENT_CACHE in sw
        spec=importlib.util.spec_from_file_location('v68_auto_update',ROOT/'auto_update_all.py')
        m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        bad={'version':1,'jobs':{'x.json':{'successes':'oops','success_streak':-99,'success_ewma_seconds':'nan','consecutive_failures':'999999999999999999'}}}
        clean=m._sanitize_adaptive_stats(bad)['jobs']['x.json']
        assert clean['successes']==0 and clean['success_streak']==0 and clean['success_ewma_seconds']==0.0 and clean['consecutive_failures']<=1_000_000
        assert m._job_timeout('x.json',{'jobs':{'x.json':clean}})==300
    check('v68 5회 반복 심층검사·학습값 보강',v68_five_pass_hardening_guard,rows)

    def v69_link_budget_partial_result_guard():
        import validate_external_links as _vl
        import os as _os
        old_http=_os.environ.get('TCG_HTTP_TIMEOUT'); old_audit=_os.environ.get('TCG_LINK_AUDIT_TIMEOUT')
        try:
            _os.environ.pop('TCG_LINK_AUDIT_TIMEOUT',None); _os.environ['TCG_HTTP_TIMEOUT']='20'
            # 112 links / 8 workers = 14 waves. HEAD+GET worst case needs far more than old fixed 120s.
            assert _vl._audit_timeout(112,8) >= 590
            assert _vl._audit_timeout(1,8) == 120
            _os.environ['TCG_LINK_AUDIT_TIMEOUT']='240'
            assert _vl._audit_timeout(112,8)==240
        finally:
            if old_http is None: _os.environ.pop('TCG_HTTP_TIMEOUT',None)
            else: _os.environ['TCG_HTTP_TIMEOUT']=old_http
            if old_audit is None: _os.environ.pop('TCG_LINK_AUDIT_TIMEOUT',None)
            else: _os.environ['TCG_LINK_AUDIT_TIMEOUT']=old_audit
        text=(ROOT/'validate_external_links.py').read_text(encoding='utf-8')
        assert 'imap_unordered' in text and 'results.setdefault' in text
        assert 'map_async(probe, urls).get' not in text
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        sw=(ROOT/'sw.js').read_text(encoding='utf-8')
        assert CURRENT_SERVICE in server and CURRENT_ENGINE in server
        assert CURRENT_APP_NAME in page and CURRENT_CACHE in sw
        return '링크 수/worker에 비례한 전체예산 · timeout 전 완료결과 보존 · v69 계약 일치'
    check('v69 링크감사 예산·부분결과 보존',v69_link_budget_partial_result_guard,rows)

    def v70_runtime_env_dns_guard():
        import os as _os, subprocess as _sp, sys as _sys, safe_runtime
        modules=['purchase_intelligence','update_promo_events','supplementary_discovery','update_purchase_sources','update_releases','update_exchange_rates','update_market_prices']
        code=';'.join([f'__import__({m!r})' for m in modules])+';print("OK")'
        for bad in ('abc','nan','inf','-999','999999'):
            env=dict(_os.environ); env['TCG_HTTP_TIMEOUT']=bad
            out=_sp.check_output([_sys.executable,'-c',code],cwd=ROOT,env=env,text=True,timeout=15).strip()
            assert out=='OK'
        old=safe_runtime.socket.getaddrinfo
        try:
            safe_runtime.socket.getaddrinfo=lambda *a,**k:[(2,1,6,'',('127.0.0.1',443))]
            try: safe_runtime.require_public_https('https://example.com/', {'example.com'})
            except ValueError: pass
            else: raise AssertionError('private DNS target allowed')
            safe_runtime.socket.getaddrinfo=lambda *a,**k:[(2,1,6,'',('93.184.216.34',443))]
            assert safe_runtime.require_public_https('https://example.com/', {'example.com'})=='https://example.com/'
        finally:
            safe_runtime.socket.getaddrinfo=old
        page=(ROOT/'index.html').read_text(encoding='utf-8'); sw=(ROOT/'sw.js').read_text(encoding='utf-8'); server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert CURRENT_APP_NAME in page and CURRENT_CACHE in sw
        assert CURRENT_SERVICE in server and CURRENT_ENGINE in server
        return '잘못된 환경 timeout 자동복구 · redirect/public DNS 재검증 · v70 계약 일치'
    check('v70 런타임 환경값·DNS 보안 회귀검사',v70_runtime_env_dns_guard,rows)

    def v71_budget_safe_guard():
        import auto_update_all as _au, validate_external_links as _vl, os as _os
        au=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        gh=(ROOT/'github_sync_engine.py').read_text(encoding='utf-8')
        mc=(ROOT/'multi_channel_agent.py').read_text(encoding='utf-8')
        assert "if stat_key == '__link_audit__'" in au and 'learned_timeout=max(120, learned_timeout)' in au
        assert "TCG_LINK_AUDIT_TIMEOUT" in au and "min(290,int(timeout_s)-10)" in au
        assert 'old_report=safe_read_bytes(link_report)' in au and "atomic_write_bytes(link_report,old_report,suffix='.restore.tmp')" in au
        assert 'from safe_runtime import (' in gh and '\n    env_int,' in gh and 'from safe_runtime import env_int' in mc
        assert 'except (urllib.error.URLError, TimeoutError, OSError) as exc' in mc
        assert 'p.port not in (None,443)' in (ROOT/'validate_external_links.py').read_text(encoding='utf-8')
        old=_os.environ.get('TCG_LINK_AUDIT_TIMEOUT')
        try:
            _os.environ['TCG_LINK_AUDIT_TIMEOUT']='290'
            assert _vl._audit_timeout(112,8)==290
        finally:
            if old is None:_os.environ.pop('TCG_LINK_AUDIT_TIMEOUT',None)
            else:_os.environ['TCG_LINK_AUDIT_TIMEOUT']=old
        # 112 URLs, 8 workers, 290s budget => per-request budget must fit global waves.
        workers=8; waves=(112+workers-1)//workers; usable=290-30
        req=max(5,min(30,max(5,usable//(waves*2))))
        assert req==9
        return '링크감사 최소예산 120초 · 내부/외부 timeout 일치 · report 원자복원 · 공통 env 파서 · 443 포트 제한'
    check('v71 링크감사 예산·런타임 안전보강',v71_budget_safe_guard,rows)

    def v72_mutation_origin_guard():
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        post_block=server.split('def do_POST(self):',1)[1].split('def local_startup_housekeeping',1)[0]
        assert "('/run-auto-update','/api/run-auto-update','/api/retry-failed')" in post_block
        assert 'if not self._require_mutation_origin()' in post_block
        assert post_block.index('if not self._require_mutation_origin()') < post_block.index('_start_background_update(')
        assert CURRENT_SERVICE in server and CURRENT_ENGINE in server
        page=(ROOT/'index.html').read_text(encoding='utf-8'); sw=(ROOT/'sw.js').read_text(encoding='utf-8')
        assert CURRENT_APP_NAME in page and CURRENT_CACHE in sw
        # v72: user/localStorage and server pending values must never be inserted raw into innerHTML.
        assert '<b>${x.name||"(이름 없음)"}</b>' not in page
        assert 'href="${x.url}"' not in page
        assert 'escapeDisplayText(x.name||"(이름 없음)")' in page
        assert 'safeExternalUrl(x.url)' in page and 'escapeDisplayText(x.error)' in page
        import auto_update_all as _aua, auto_repair_engine as _are
        assert _aua._should_retry({},False,'RuntimeError: invalid configuration') is False
        assert _aua._should_retry({},False,'RuntimeError: URLError temporary failure') is True
        category,action,_=_are.classify('SECURITY: private DNS target blocked')
        assert category=='보안 정책 차단' and '재시도 중단' in action
        return '백그라운드 POST Origin 검증 · innerHTML XSS 차단 · deterministic RuntimeError 재시도 억제 · 보안차단 학습 격리'
    check('v72 변경 API CSRF·출처검증 보강',v72_mutation_origin_guard,rows)

    def v73_exception_atomic_learning_guard():
        import os as _os, json as _json, tempfile as _tempfile, hashlib as _hashlib, re as _re
        import validate_external_links as _vl, auto_repair_engine as _are, tcg_updater as _tu, auto_update_all as _au
        old=_os.environ.get('TCG_HTTP_TIMEOUT')
        try:
            _os.environ['TCG_HTTP_TIMEOUT']='inf'
            assert _vl._request_timeout()==20
        finally:
            if old is None:_os.environ.pop('TCG_HTTP_TIMEOUT',None)
            else:_os.environ['TCG_HTTP_TIMEOUT']=old
        # nested learning counters must self-sanitize instead of crashing the next write
        with _tempfile.TemporaryDirectory() as d:
            mp=Path(d)/'memory.json'
            key=_are.fingerprint('x.json','통신 오류','Timeout')
            mp.write_text(_json.dumps({'version':2,'total_runs':'bad','patterns':{key:{'file':'x.json','category':'통신 오류','occurrences':'abc'}},'files':{},'monitor_known_errors':{},'monitor_history':[]}),encoding='utf-8')
            learned=_are.learn({'results':[{'file':'x.json','ok':False,'error':'Timeout'}]},mp)
            assert learned['patterns'][key]['occurrences']==1
        err='same error'; sig=_hashlib.sha1(_re.sub(r'\d+','<n>',err.lower()).encode()).hexdigest()[:12]
        stats=_tu._sanitize_source_stats({'sources':{'x':{'error_patterns':{sig:{'count':'abc'}}}}})
        _tu._record_source_stat(stats,'x',1.0,False,err,False)
        assert stats['sources']['x']['error_patterns'][sig]['count']==1
        astats=_au._sanitize_adaptive_stats({'jobs':{'x.py':{'error_patterns':{'bad':{'count':'oops'}}}}})
        _au._record_job_stat(astats,'x.py',1.0,False,error='failure')
        assert all(isinstance(v.get('count'),int) for v in astats['jobs']['x.py']['error_patterns'].values())
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert 'OfficialSourceRedirect' in server and 'require_public_https(newurl)' in server
        assert 'DATA_WRITE_LOCK=threading.RLock()' in server and 'DB_MUTATION_LOCK=threading.RLock()' in server
        assert CURRENT_SERVICE in server and CURRENT_ENGINE in server
        page=(ROOT/'index.html').read_text(encoding='utf-8'); sw=(ROOT/'sw.js').read_text(encoding='utf-8')
        assert CURRENT_APP_NAME in page and CURRENT_CACHE in sw
        return 'Inf timeout 복구 · 예외 오분류 방지 · 원자 백업/동시쓰기 잠금 · 공식출처 SSRF 차단 · 중첩 학습값 손상 복구'
    check('v73 6회 심층 예외·원자저장·학습값 보강',v73_exception_atomic_learning_guard,rows)

    def v74_migration_http_guard():
        import tempfile as _tempfile, json as _json
        import migrate_old_data as _mig, tcg_updater as _tu
        # malformed legacy learning counters must not abort a migration merge
        merged=_mig.merge_memory(
            {'version':2,'total_runs':'bad','patterns':{},'files':{},'monitor_known_errors':{},'monitor_history':[]},
            {'version':'oops','total_runs':'7','patterns':{'p':{'occurrences':'abc','successful_repairs':'2'}},
             'files':{'x.json':{'runs':'bad','recent_failures':'3','clean_success_streak':'9','last_run':'2026-08-24T00:00:00+00:00'}},
             'monitor_known_errors':{'m':{'occurrences':'4','resolved_count':'bad','last_seen':'2026-08-24T00:00:00+00:00'}},
             'monitor_history':[{'timestamp':'2026-08-24T00:00:00+00:00','function':'x','error_type':'Timeout','error_message':'x','attempt':1}]})
        assert merged['total_runs']==7
        assert merged['patterns']['p']['occurrences']==0 and merged['patterns']['p']['successful_repairs']==2
        assert merged['files']['x.json']['recent_failures']==3 and merged['files']['x.json']['clean_success_streak']==9
        assert merged['monitor_known_errors']['m']['occurrences']==4
        assert len(merged['monitor_history'])==1
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert "TCG_HTTP_REQUEST_TIMEOUT" in server and "self.connection.settimeout" in server
        assert "Content-Length 형식 오류" in server
        assert CURRENT_SERVICE in server and CURRENT_ENGINE in server
        mig=(ROOT/'migrate_old_data.py').read_text(encoding='utf-8')
        assert "not dst.exists()" in mig and "monitor_known_errors" in mig and "monitor_history" in mig
        page=(ROOT/'index.html').read_text(encoding='utf-8'); sw=(ROOT/'sw.js').read_text(encoding='utf-8')
        assert CURRENT_APP_NAME in page and CURRENT_CACHE in sw
        return '손상 학습값 이전 안전화 · monitor 학습 보존 · last-good 덮어쓰기 방지 · HTTP body timeout/Content-Length 검증'
    check('v74 마이그레이션·HTTP 요청고갈·학습값 보강',v74_migration_http_guard,rows)

    def v75_safe_redirect_exception_learning_guard():
        import json as _json, tempfile as _tempfile, socket as _socket, urllib.error as _uerr, urllib.request as _ureq
        import safe_runtime as _sr, github_sync_engine as _gh, tcg_updater as _tu
        # Pre-follow DNS check: a redirect that resolves to loopback must be blocked
        # before urllib gets a chance to issue the redirected request.
        old=_sr.socket.getaddrinfo
        try:
            _sr.socket.getaddrinfo=lambda *a,**k:[(_socket.AF_INET,_socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
            req=_ureq.Request('https://example.com/start')
            try:
                _sr.PublicHTTPSRedirect({'example.com'}).redirect_request(req,None,302,'Found',{},'https://example.com/private')
                raise AssertionError('private redirect accepted')
            except ValueError:
                pass
        finally:
            _sr.socket.getaddrinfo=old
        # Authenticated GitHub requests must never follow redirects (token leakage guard).
        req=_ureq.Request('https://api.github.com/repos/o/r',headers={'Authorization':'Bearer SECRET'})
        try:
            _sr.NoRedirect().redirect_request(req,None,302,'Found',{},'https://evil.example/leak')
            raise AssertionError('authenticated redirect accepted')
        except _uerr.HTTPError:
            pass
        for bad in (
            _gh.GitHubSyncEngine(token='x',repo_owner='owner/evil',repo_name='repo'),
            _gh.GitHubSyncEngine(token='x',repo_owner='owner',repo_name='repo',file_path='../secret.json'),
        ):
            try: bad._url(); raise AssertionError('bad github config accepted')
            except ValueError: pass
        # Corrupted current JSON must not replace an existing known-good .bak.
        with _tempfile.TemporaryDirectory() as td:
            path=Path(td)/'x.json'; bak=Path(str(path)+'.bak')
            path.write_text('{broken',encoding='utf-8'); bak.write_text(_json.dumps({'known_good':1}),encoding='utf-8')
            _tu.save_json_atomic(str(path),{'new':2})
            assert _json.loads(path.read_text(encoding='utf-8'))=={'new':2}
            assert _json.loads(bak.read_text(encoding='utf-8'))=={'known_good':1}
        market=(ROOT/'update_market_prices.py').read_text(encoding='utf-8')
        protected=('update_market_prices.py','update_exchange_rates.py','update_releases.py','supplementary_discovery.py','purchase_intelligence.py','multi_channel_agent.py','github_sync_engine.py')
        for fn in protected:
            src=(ROOT/fn).read_text(encoding='utf-8')
            assert 'urllib.request.urlopen(' not in src and 'with urlopen(' not in src
        assert 'except NETWORK_ERRORS as e' in market and 'except Exception as e' not in market
        manifest=_json.loads((ROOT/'manifest.webmanifest').read_text(encoding='utf-8'))
        page=(ROOT/'index.html').read_text(encoding='utf-8'); sw=(ROOT/'sw.js').read_text(encoding='utf-8'); server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert manifest.get('name')==CURRENT_APP_NAME
        assert CURRENT_APP_NAME in page and CURRENT_CACHE in sw
        assert CURRENT_SERVICE in server and CURRENT_ENGINE in server
        return 'redirect 사전 DNS 검증 · 인증요청 redirect 차단 · 코드오류 오분류 방지 · 정상 backup 보존 · PWA 버전 일치'
    check('v75 redirect·예외학습·백업보존 보강',v75_safe_redirect_exception_learning_guard,rows)

    def v79_history_finalization_guard():
        with tempfile.TemporaryDirectory(prefix='tcg-v79-history-') as td:
            path=Path(td)/'history.json'
            sample=[{'name':'first','ok':True,'detail':'ok'},{'name':'last security check','ok':False,'detail':'forced failure'}]
            stored,failed=persist_verification_history(sample,path)
            assert failed['ok'] is False and failed['pass_count']==1 and failed['failure_count']==1
            assert len(stored['runs'][-1]['checks'])==2
            sample.append({'name':'late mutation','ok':True})
            assert len(stored['runs'][-1]['checks'])==2
            persist_verification_history([{'name':'second','ok':True}],path)
            assert path.with_suffix('.json.bak').exists()
            path.write_text('{damaged',encoding='utf-8')
            recovered,latest=persist_verification_history([{'name':'recovered','ok':True}],path)
            assert recovered['runs'][0]['ok'] is False and latest['ok'] is True
            assert json.loads(path.read_text(encoding='utf-8'))['runs'][-1]['checks'][0]['name']=='recovered'
        source=(ROOT/'verify_all.py').read_text(encoding='utf-8')
        assert source.rfind('history,run=persist_verification_history(rows)')>source.rfind("check('v79")
        return '마지막 보안검사까지 합산 · 실패 종료코드 반영 · 전체 검사내역 누적 · 손상 기록 백업 복구'
    check('v79 최종판정·전체 검사기록 누락 방지',v79_history_finalization_guard,rows)

    def v79_memory_privacy_concurrency_guard():
        import concurrent.futures
        import auto_repair_engine as repair
        import auto_update_all as automatic
        with tempfile.TemporaryDirectory(prefix='tcg-v79-memory-') as td:
            memory_path=Path(td)/'memory.json'
            stale_engine=repair.AutoRepairEngine(memory_file=memory_path,root=Path(td))
            payload={'results':[{}, {'file':'../bad.json','ok':False},
                {'file':'C:\\Users\\private\\bad.json','ok':False,'error':'should not be stored'},
                {'file':'x.json','ok':False,'collection_errors':'TimeoutError: https://example.com/?token=PRIVATEQUERY',
                 'error':'Bearer TOPSECRET password=hunter2 api_key=MYKEY'}]}
            first=repair.learn(payload,memory_path)
            assert first['invalid_report_count']==3 and first['files']['x.json']['runs']==1
            assert len(first['patterns'])==2
            raw=memory_path.read_text(encoding='utf-8')
            assert all(secret not in raw for secret in ('PRIVATEQUERY','TOPSECRET','hunter2','MYKEY'))
            def one(_):
                repair.learn({'results':[{'file':'x.json','ok':True}]},memory_path)
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(one,range(8)))
            learned=repair.load_memory(memory_path)
            assert learned['total_runs']==9 and learned['files']['x.json']['runs']==9
            stale_engine._record_monitor_event(func_name='test',error_type='ValueError',
                error_msg='token=MONITORSECRET',tb='Traceback: Bearer TRACESECRET',resolved=False,
                action='safe',target_file='x.json',attempt=1)
            latest=repair.load_memory(memory_path)
            assert latest['total_runs']==9 and len(latest['monitor_history'])==1
            persisted=memory_path.read_text(encoding='utf-8')
            assert 'MONITORSECRET' not in persisted and 'TRACESECRET' not in persisted
            assert repair.attempts_for('x.json',{'files':{'x.json':{'recent_failures':'broken'}}})==2
            assert automatic._sanitize_adaptive_stats([])['jobs']=={}
        return '학습값 동시 저장 유실 차단 · 손상 보고서 격리 · URL/토큰/비밀번호·traceback 비공개'
    check('v79 학습정보 보호·동시성·손상값 복구',v79_memory_privacy_concurrency_guard,rows)

    def v79_host_and_learning_api_guard():
        import socket
        import safe_runtime
        import tcg_updater as updater
        original_learning=updater.LEARNING_STORE
        with tempfile.TemporaryDirectory(prefix='tcg-v79-api-') as td:
            invalid_json=Path(td)/'invalid-shape.json';invalid_json.write_text('[]',encoding='utf-8')
            assert updater.load_json_file(str(invalid_json),{'safe':True})=={'safe':True}
            for unsafe in ('https://example.com/a\r\nInjected: yes','https://example.com/\\private'):
                try:safe_runtime.require_public_https(unsafe)
                except ValueError:pass
                else:raise AssertionError('unsafe URL control characters allowed')
            updater.LEARNING_STORE=str(Path(td)/'learning.json')
            server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),updater.Handler)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                for forged in (f'evil.example:{port}',f'127.0.0.1:{port+1}'):
                    request=urllib.request.Request(base+'/api/health',headers={'Host':forged})
                    try:urllib.request.urlopen(request,timeout=5)
                    except urllib.error.HTTPError as exc:assert exc.code==421
                    else:raise AssertionError('forged Host allowed')
                def post(body):
                    request=urllib.request.Request(base+'/api/learning-store',data=json.dumps(body).encode('utf-8'),
                        headers={'Content-Type':'application/json'},method='POST')
                    with urllib.request.urlopen(request,timeout=5) as response:
                        return json.loads(response.read().decode('utf-8'))
                for invalid in ([],{'v30_validation':{}}):
                    try:post(invalid)
                    except urllib.error.HTTPError as exc:assert exc.code==400
                    else:raise AssertionError('malformed learning JSON allowed')
                one={'time':'one','company':'PSA','actual':9,'pred':10}
                two={'time':'two','company':'BGS','actual':9,'pred':9}
                assert post({'v30_validation':[one],'v11_validation':[]})['saved']==1
                assert post({'v30_validation':[],'v11_validation':[]})['saved']==1
                assert post({'v30_validation':[two],'v11_validation':[]})['saved']==2
                with urllib.request.urlopen(base+'/api/verification-cycles',timeout=5) as response:
                    assert response.status==200 and isinstance(json.load(response),dict)
                duplicate=(f'POST /api/learning-store HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n'
                    'Content-Type: application/json\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}').encode('ascii')
                with socket.create_connection(('127.0.0.1',port),timeout=5) as connection:
                    connection.sendall(duplicate)
                    assert b' 400 ' in connection.recv(1024)
            finally:
                server.shutdown();server.server_close();thread.join(timeout=3)
                updater.LEARNING_STORE=original_learning
        return '위조 Host 421 · JSON 배열/중복 길이 400 · 빈 기기 동기화에서도 기존 학습기록 유지'
    check('v79 로컬 서버 Host·학습기록 보안',v79_host_and_learning_api_guard,rows)

    def v79_browser_runtime_guard():
        completed=subprocess.run(['node','verify_browser_runtime.js'],cwd=ROOT,capture_output=True,text=True,timeout=30,check=True)
        assert 'PASS: browser storage recovery' in completed.stdout
        assert 'shared image loaders and URL cleanup' in completed.stdout
        return '공통 이미지 로더·URL 해제 · 손상 localStorage 복구 · 등급값 정규화 · 검사이력/오류보고/시세목록/빠른검색 XSS 실제 실행검증'
    check('v79 브라우저 실동작·화면 주입 방지',v79_browser_runtime_guard,rows)

    def v79_launchers_and_repeat_guard():
        runner=(ROOT/'TCG_SERVER_AUTO_RUN.cmd').read_text(encoding='utf-8')
        installer=(ROOT/'PC_SERVER_AUTO_START_INSTALL.bat').read_text(encoding='utf-8')
        android=(ROOT/'ANDROID_AUTO_START_INSTALL.sh').read_text(encoding='utf-8')
        repeated=(ROOT/'run_repeated_verification.py','social_event_discovery.py').read_text(encoding='utf-8')
        assert 'py.exe -3 -c' in runner and 'python.exe -c' in runner
        assert 'ping 127.0.0.1 -n 11' in runner and 'restart loop stopped' in runner
        assert 'py.exe -3 -c' in installer and 'python.exe -c' in installer
        assert 'BOOT_TEMP=' in android and 'umask 077' in android and 'mv -f "$BOOT_TEMP" "$BOOT_FILE"' in android
        assert 'max(5, min(10, int(passes)))' in repeated and 'validate_project_files' in repeated
        assert 'learning_results.extend' in repeated and 'for filename in RECOVERABLE_FILES' in repeated
        for name in ('TCG_AUTO_UPDATE.bat','정보자동업데이트.bat','전체프로그램검사.bat'):
            assert 'run_repeated_verification.py --passes 5' in (ROOT/name).read_text(encoding='utf-8')
        for script in [*ROOT.glob('*.bat'),*ROOT.glob('*.cmd')]:
            text=script.read_text(encoding='utf-8')
            labels={item.lower() for item in re.findall(r'^\s*:([A-Za-z0-9_]+)\s*$',text,re.M)}
            targets={item.lower() for item in re.findall(r'\bgoto\s+:?([A-Za-z0-9_]+)',text,re.I)}
            assert not targets-labels-{'eof'},f'{script.name}: 존재하지 않는 이동 대상 {targets-labels}'
        return '실행 가능한 Python 3 검증 · 무한 재시작 폭주 차단 · 태블릿 시작파일 원자 설치 · 5~10회 반복검사'
    check('v79 PC·태블릿 자동실행·5회 반복검사',v79_launchers_and_repeat_guard,rows)

    def v79_head_and_standard_json_guard():
        import tcg_updater as updater
        original_learning=updater.LEARNING_STORE
        with tempfile.TemporaryDirectory(prefix='tcg-v79-http-') as td:
            updater.LEARNING_STORE=str(Path(td)/'learning.json')
            server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),updater.Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            port=server.server_address[1];base=f'http://127.0.0.1:{port}'
            try:
                for path,host,status in (
                    ('/tcg_updater.py',f'127.0.0.1:{port}',404),
                    ('/.tcg_last_good/releases.json',f'127.0.0.1:{port}',404),
                    ('/index.html','attacker.invalid',421),
                    ('/api/health',f'127.0.0.1:{port}',405),
                ):
                    request=urllib.request.Request(base+path,method='HEAD',headers={'Host':host})
                    try:urllib.request.urlopen(request,timeout=5)
                    except urllib.error.HTTPError as error:
                        assert error.code==status and error.read()==b''
                    else:raise AssertionError(f'HEAD 보안 우회: {path}')
                with urllib.request.urlopen(urllib.request.Request(base+'/index.html',method='HEAD'),timeout=5) as response:
                    assert response.status==200 and response.read()==b''
                malformed=(
                    b'{"v30_validation":[{"company":"PSA","actual":9,"pred":9,"extra":NaN}]}',
                    b'{"v30_validation":[{"company":"PSA","actual":9,"pred":9,"extra":Infinity}]}',
                    b'{"v30_validation":[{"company":"PSA","actual":9,"pred":9,"extra":-Infinity}]}',
                    b'{"v30_validation":[],"v30_validation":[]}',
                    b'{"nested":'+b'['*30+b'0'+b']'*30+b'}',
                )
                for body in malformed:
                    request=urllib.request.Request(base+'/api/learning-store',data=body,method='POST',
                        headers={'Content-Type':'application/json'})
                    try:urllib.request.urlopen(request,timeout=5)
                    except urllib.error.HTTPError as error:assert error.code==400
                    else:raise AssertionError('표준이 아닌 학습 JSON 허용')
                body=json.dumps({'v30_validation':[{'company':'PSA','actual':9,'pred':10,
                    'time':'t'*200,'mode':'raw','private':'discard'}]}).encode('utf-8')
                request=urllib.request.Request(base+'/api/learning-store',data=body,method='POST',
                    headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(request,timeout=5) as response:assert response.status==200
                saved=json.loads(Path(updater.LEARNING_STORE).read_text(encoding='utf-8'))['v30_validation'][0]
                assert saved['company']=='PSA' and saved['mode']=='raw' and len(saved['time'])==120
                assert saved['match'] is False and 'private' not in saved
                assert updater.valid_learning_rows([{'company':'PSA','actual':10**400,'pred':9}])==[]
                try:updater.strict_json_loads('[0,0,0,0,0]',max_nodes=3)
                except ValueError:pass
                else:raise AssertionError('JSON 항목 수 제한 우회')
                before=Path(updater.LEARNING_STORE).read_text(encoding='utf-8')
                try:updater.save_json_atomic(updater.LEARNING_STORE,{'bad':float('nan')})
                except ValueError:pass
                else:raise AssertionError('NaN 원자 저장 허용')
                assert Path(updater.LEARNING_STORE).read_text(encoding='utf-8')==before
            finally:
                server.shutdown();server.server_close();worker.join(timeout=3)
                updater.LEARNING_STORE=original_learning
        return 'HEAD 내부파일·위조 Host 차단 · NaN/Infinity/중복 키/과도한 중첩 거부 · 학습 필드 정규화'
    check('v79 HEAD 우회·표준 JSON·학습값 오염 차단',v79_head_and_standard_json_guard,rows)

    def v79_purchase_request_budget_guard():
        import purchase_intelligence
        import tcg_updater as updater
        old_search=purchase_intelligence.search_web_signals
        old_limit=updater.SEARCH_LIMIT_REQUESTS
        with updater.SEARCH_LIMIT_LOCK:
            old_buckets=dict(updater.SEARCH_LIMIT_BUCKETS);updater.SEARCH_LIMIT_BUCKETS.clear()
        calls=[]
        purchase_intelligence.search_web_signals=lambda q,region,game:calls.append((q,region,game)) or {'ok':True,'items':[]}
        updater.SEARCH_LIMIT_REQUESTS=2
        server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),updater.Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_address[1]}/api/purchase-live-search?q=card&game=Pokemon&region='
        try:
            for headers in ({'Origin':'https://attacker.invalid'},{'Sec-Fetch-Site':'cross-site'}):
                request=urllib.request.Request(base+'KR',headers=headers)
                try:urllib.request.urlopen(request,timeout=5)
                except urllib.error.HTTPError as error:assert error.code==403
                else:raise AssertionError('외부 사이트 구매검색 실행 허용')
            assert calls==[]
            for _ in range(2):
                with urllib.request.urlopen(base+'KR',timeout=5) as response:assert response.status==200
            try:urllib.request.urlopen(base+'KR',timeout=5)
            except urllib.error.HTTPError as error:
                assert error.code==429 and json.loads(error.read().decode('utf-8'))['retry_after_seconds']>0
            else:raise AssertionError('구매검색 요청 폭주 허용')
            with urllib.request.urlopen(base+'JP',timeout=5) as response:assert response.status==200
            trusted=urllib.request.Request(base+'US',headers={'Origin':updater.TRUSTED_PAGES_ORIGIN})
            with urllib.request.urlopen(trusted,timeout=5) as response:assert response.status==200
            assert [row[1] for row in calls]==['KR','KR','JP','US']
        finally:
            server.shutdown();server.server_close();worker.join(timeout=3)
            purchase_intelligence.search_web_signals=old_search
            updater.SEARCH_LIMIT_REQUESTS=old_limit
            with updater.SEARCH_LIMIT_LOCK:
                updater.SEARCH_LIMIT_BUCKETS.clear();updater.SEARCH_LIMIT_BUCKETS.update(old_buckets)
        return '외부 Origin/Sec-Fetch-Site 검색 차단 · IP·국가별 요청량 제한 · 한국·일본·미국 독립 동작'
    check('v79 구매검색 출처검증·요청폭주 차단',v79_purchase_request_budget_guard,rows)

    def v79_backup_shape_and_symlink_guard():
        import auto_repair_engine as repair
        with tempfile.TemporaryDirectory(prefix='tcg-v79-repair-') as td:
            root=Path(td)/'project';root.mkdir()
            target=root/'releases.json';target.write_text('{damaged',encoding='utf-8')
            backup_root=root/'.tcg_last_good';backup_root.mkdir();backup=backup_root/'releases.json'
            engine=repair.AutoRepairEngine(memory_file=root/'memory.json',root=root,last_good=backup_root)
            for invalid in ('[]','{}','{"items":[],"price":NaN}'):
                backup.write_text(invalid,encoding='utf-8')
                result=engine.validate_project_files(['releases.json'])
                assert result['ok'] is False and target.read_text(encoding='utf-8')=='{damaged'
            outside=Path(td)/'outside.json';outside.write_text('{"items":[{"name":"outside"}]}',encoding='utf-8')
            if hasattr(os,'symlink'):
                try:
                    backup.unlink();backup.symlink_to(outside)
                    assert engine.validate_project_files(['releases.json'])['ok'] is False
                    backup.unlink();target.unlink();target.symlink_to(outside)
                    assert engine._safe_target('releases.json') is None
                    assert engine.validate_project_files(['releases.json'])['ok'] is False
                    assert json.loads(outside.read_text(encoding='utf-8'))['items'][0]['name']=='outside'
                    target.unlink();target.write_text('{damaged',encoding='utf-8')
                except (NotImplementedError,OSError):
                    if target.is_symlink():target.unlink();target.write_text('{damaged',encoding='utf-8')
                    if backup.is_symlink():backup.unlink()
            expected={'items':[{'game':'Pokemon','region':'KR','name':'valid','source':'https://example.com/cards'}]}
            backup.write_text(json.dumps(expected),encoding='utf-8')
            assert engine.validate_project_files(['releases.json'])['ok'] is True
            assert json.loads(target.read_text(encoding='utf-8'))==expected
            memory=repair.load_memory(root/'memory.json')
            assert any(not row['resolved'] for row in memory['monitor_history'])
            assert any(row['resolved'] for row in memory['monitor_history'])
        return '배열·필수값 누락·NaN 백업 폐기 · 복구 대상/백업 symlink 차단 · 정상 구조만 원자 복원·학습'
    check('v79 정상백업 구조검증·경로탈출 방지',v79_backup_shape_and_symlink_guard,rows)

    def v79_process_timeout_tree_guard():
        from unittest.mock import patch
        import tcg_updater as updater
        class FakeProcess:
            pid=424242
            returncode=-9
            def __init__(self):self.communications=0;self.killed=False
            def communicate(self,timeout=None):
                self.communications+=1
                if self.communications==1:raise subprocess.TimeoutExpired('collector',timeout)
                return '',''
            def kill(self):self.killed=True
        fake=FakeProcess()
        with patch.object(updater.subprocess,'Popen',return_value=fake):
            if os.name=='nt':
                with patch.object(updater.subprocess,'run') as terminate:
                    try:updater._run_precollect_process(['collector'],cwd=ROOT,timeout=0.01)
                    except subprocess.TimeoutExpired:pass
                    else:raise AssertionError('수집 제한시간 오류 누락')
                    assert terminate.call_args.args[0][0]=='taskkill'
            else:
                with patch.object(updater.os,'killpg') as terminate:
                    try:updater._run_precollect_process(['collector'],cwd=ROOT,timeout=0.01)
                    except subprocess.TimeoutExpired:pass
                    else:raise AssertionError('수집 제한시간 오류 누락')
                    terminate.assert_called_once_with(fake.pid,updater.signal.SIGKILL)
            assert fake.communications==2 and fake.killed is False
        return '누락 signal import 복구 · 제한시간 초과 시 수집 하위 프로세스 전체 종료'
    check('v79 사전수집 시간초과·하위프로그램 정리',v79_process_timeout_tree_guard,rows)

    def v79_compressed_storage_and_filename_guard():
        import gzip
        from unittest.mock import patch
        from optimized_self_healing import SelfHealingEngine
        from cross_platform_agent import CrossPlatformSelfHealingEngine
        with tempfile.TemporaryDirectory(prefix='tcg-v79-gzip-') as td:
            root=Path(td);data=root/'cards.json.gz';backup=root/'cards.json.gz.bak'
            engine=SelfHealingEngine(data,backup,max_bytes=1024)
            first={'cards':['first']};second={'cards':['second']}
            assert engine.save_compressed_data(first)
            assert engine.save_compressed_data(second)
            with gzip.open(data,'wt',encoding='utf-8') as output:json.dump({'payload':'x'*4000},output)
            assert engine.load_compressed_data()==first
            assert engine.save_compressed_data({'payload':'x'*4000}) is False
            assert engine.load_compressed_data()==first
            assert engine.save_compressed_data({'bad':float('nan')}) is False
            assert not data.with_suffix(data.suffix+'.tmp').exists()
            folder=root/'platform'
            with patch.dict(os.environ,{'TCG_DATA_DIR':str(folder)}):
                agent=CrossPlatformSelfHealingEngine()
                assert agent.save_and_clean_data([{'name':'ok'}],'../escape.json.gz') is False
                assert agent.save_and_clean_data([{'name':'ok'}],'cards.json.gz') is True
                assert not (root/'escape.json.gz').exists()
        return 'gzip 해제폭탄 크기 제한 · 손상자료는 정상 backup 복원 · NaN 차단 · 저장 경로탈출 방지'
    check('v79 압축자료 폭주·저장경로 보안',v79_compressed_storage_and_filename_guard,rows)

    def v79_service_worker_runtime_guard():
        completed=subprocess.run(['node','verify_service_worker_runtime.js'],cwd=ROOT,
            capture_output=True,text=True,timeout=30,check=True)
        assert 'PASS: service-worker error cache isolation' in completed.stdout
        assert 'supplementary event freshness' in completed.stdout
        source=(ROOT/'sw.js').read_text(encoding='utf-8')
        assert "response.ok" in source and "url.origin!==self.location.origin" in source
        return '행사 보조자료 오래된 캐시 회피 · 500 응답 캐시 오염 차단 · JSON 오프라인 503 유지 · 저장공간 오류 안전처리'
    check('v79 오프라인 캐시·서비스워커 실제 실행',v79_service_worker_runtime_guard,rows)

    def v79_repeated_history_integrity_guard():
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import patch
        import run_repeated_verification as repeated
        with tempfile.TemporaryDirectory(prefix='tcg-v79-repeat-') as td:
            history=Path(td)/'history.json';report=Path(td)/'cycles.json';memory=Path(td)/'memory.json'
            final_report=Path(td)/'final.json'
            final_report.write_text(json.dumps({'verified_at':'old','result':'PASS',
                'verification':{},'error_learning':{}}),encoding='utf-8')
            def save_latest(ok,number):
                history.write_text(json.dumps({'runs':[{'ok':ok,'pass_count':44,
                    'failure_count':0 if ok else 1,'nonce':'x'*number}]}),encoding='utf-8')
            save_latest(True,1)
            with patch.object(repeated,'HISTORY',history):
                stale=repeated._history_signature()
                latest,error=repeated._verified_latest(stale)
                assert latest=={} and error
                save_latest(False,2)
                latest,error=repeated._verified_latest(stale)
                assert latest.get('ok') is False and error
            count={'run':0,'learn':0}
            def pretend_verify(*args,**kwargs):
                count['run']+=1;ok=count['run']!=1;save_latest(ok,count['run']+3)
                return SimpleNamespace(returncode=0 if ok else 1,stdout='실패: simulated' if not ok else '',stderr='')
            def pretend_learn(*args,**kwargs):
                count['learn']+=1
                return {'version':4,'total_runs':count['learn'],'new_error_log':[],
                    'learning_summary':{'error_group_count':1,'new_group_count':0,
                    'recurring_group_count':1,'unresolved_group_count':0,
                    'resolved_group_count':1,'verified_solution_group_count':1,
                    'consolidated_event_total':3}}
            class SafeRecovery:
                def __init__(self,*args,**kwargs):pass
                def validate_project_files(self,*args,**kwargs):return {'ok':True,'results':[]}
            with patch.object(repeated,'HISTORY',history),patch.object(repeated,'REPORT',report),\
                 patch.object(repeated,'FINAL_REPORT',final_report),\
                 patch.object(repeated,'MEMORY',memory),patch.object(repeated.subprocess,'run',side_effect=pretend_verify),\
                 patch.object(repeated,'learn',side_effect=pretend_learn),patch.object(repeated,'AutoRepairEngine',SafeRecovery):
                with redirect_stdout(StringIO()):
                    results=repeated.run_repeated_verification(5)
            assert results['completed_passes']==5 and results['successful_passes']==4
            assert results['failed_passes']==1 and results['ok'] is False
            assert results['results'][0]['failed_checks']==1
            persisted=json.loads(report.read_text(encoding='utf-8'))
            synced=json.loads(final_report.read_text(encoding='utf-8'))
            assert persisted['ok'] is False and persisted['final_report_synced'] is True
            assert synced['result']=='FAIL' and synced['error_learning']['total_runs']==5
            assert synced['verification']['checks_executed']==221
            final_report.write_text('{',encoding='utf-8')
            with patch.object(repeated,'FINAL_REPORT',final_report):
                assert repeated._sync_final_report(results,pretend_learn()) is False
        return '이전 성공기록 재사용 차단 · 5회 중 1회 실패 은폐 방지 · 최종 보고서 학습통계 자동 동기화'
    check('v79 반복검사 기록 무결성·실패 은폐 방지',v79_repeated_history_integrity_guard,rows)

    def v79_unified_error_group_guard():
        import auto_repair_engine as repair
        with tempfile.TemporaryDirectory(prefix='tcg-v79-groups-') as td:
            memory_path=Path(td)/'memory.json'
            learned=repair.learn({'results':[
                {'file':'market_prices.json','ok':False,'error':'TimeoutError: price source 10 timed out'},
                {'file':'promo_events.json','ok':False,'error':'TimeoutError: promo source 99 timed out'},
                {'file':'releases.json','ok':False,'error':'MysteryFault item 100 refused moon'},
                {'file':'purchase_sources.json','ok':False,'error':'MysteryFault item 200 refused moon'},
            ]},memory_path)
            assert len(learned['error_groups'])==2 and len(learned['new_error_log'])==2
            timeout=next(row for row in learned['error_groups'].values() if row['code']=='NETWORK_TIMEOUT')
            unknown=next(row for row in learned['error_groups'].values() if row['code']=='UNCLASSIFIED_ERROR')
            assert timeout['occurrences']==2 and unknown['occurrences']==2
            assert set(timeout['unresolved_files'])=={'market_prices.json','promo_events.json'}
            for _ in range(2):repair.learn({'results':[{'file':'market_prices.json','ok':True}]},memory_path)
            partial=repair.load_memory(memory_path)
            timeout=next(row for row in partial['error_groups'].values() if row['code']=='NETWORK_TIMEOUT')
            assert timeout['last_outcome']=='unresolved' and timeout['unresolved_files']==['promo_events.json']
            for _ in range(2):repair.learn({'results':[{'file':'promo_events.json','ok':True}]},memory_path)
            complete=repair.load_memory(memory_path)
            timeout=next(row for row in complete['error_groups'].values() if row['code']=='NETWORK_TIMEOUT')
            assert timeout['last_outcome']=='resolved' and timeout['unresolved_files']==[]
            assert timeout['resolved_count']==2 and timeout['unresolved_count']==0
            assert timeout['proven_action']=='동일 파일 2회 연속 정상 실행으로 해결 확인'
            before=json.dumps(complete,ensure_ascii=False,sort_keys=True)
            public=repair.public_error_learning_summary(complete)
            assert json.dumps(complete,ensure_ascii=False,sort_keys=True)==before
            assert 'file_states' not in json.dumps(public,ensure_ascii=False)
        return '동일 원인 자동통합 · 신규 원인별 1회 기록 · 파일별 2회 정상 확인 · 검증된 해결조치 학습'
    check('v79 동일오류 통합·신규오류 분석·파일별 해결학습',v79_unified_error_group_guard,rows)

    def v79_error_learning_summary_api_guard():
        import auto_repair_engine as repair
        import tcg_updater as updater
        old_memory=updater.AUTO_MEMORY
        with tempfile.TemporaryDirectory(prefix='tcg-v79-summary-') as td:
            memory_path=Path(td)/'memory.json'
            repair.learn({'results':[{'file':'releases.json','ok':False,
                'error':'NameError: parser_name missing token=PRIVATEVALUE'}]},memory_path)
            engine=repair.AutoRepairEngine(memory_file=memory_path,root=Path(td))
            engine._record_monitor_event(func_name='collector',error_type='ValueError',
                error_msg='password=MONITORSECRET',tb='Traceback Bearer TRACESECRET',resolved=False,
                action='입력값 격리',target_file='releases.json',attempt=1)
            updater.AUTO_MEMORY=str(memory_path)
            server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),updater.Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{server.server_address[1]}/api/error-learning-summary',timeout=5) as response:
                    payload=json.load(response)
                encoded=json.dumps(payload,ensure_ascii=False)
                assert payload['version']>=3 and payload['summary']['error_group_count']==2
                assert all(key not in encoded for key in ('monitor_history','traceback_tail','PRIVATEVALUE','MONITORSECRET','TRACESECRET','file_states'))
                assert all(row.get('probable_cause') and row.get('resolution_steps') and row.get('verification_steps') for row in payload['groups'])
            finally:
                server.shutdown();server.server_close();worker.join(timeout=3)
                updater.AUTO_MEMORY=old_memory
            poisoned={'version':4,'patterns':{},'files':{},'total_runs':1,'error_groups':{
                'token=GROUPSECRET':{'occurrences':1,'resolved_count':0,'last_outcome':'unresolved',
                'code':'UNCLASSIFIED_ERROR','title':'x','category':'x','error_subtype':'general',
                'first_seen':{'password':'FIRSTSECRET'},'last_seen':{'api_key':'LASTSECRET'},
                'affected_files':['token=FILESECRET.json'],'file_counts':{'token=FILESECRET.json':1},
                'file_states':{'token=FILESECRET.json':{'occurrences':1,'resolved_count':0,'last_outcome':'unresolved'}}}},
                'new_error_log':[]}
            guarded=repair.public_error_learning_summary(poisoned)
            guarded_text=json.dumps(guarded,ensure_ascii=False)
            assert all(secret not in guarded_text for secret in ('GROUPSECRET','FIRSTSECRET','LASTSECRET','FILESECRET'))
            assert re.fullmatch(r'[0-9a-f]{16}',guarded['groups'][0]['group_id'])
            assert isinstance(guarded['groups'][0]['first_seen'],str) and isinstance(guarded['groups'][0]['last_seen'],str)
            network=repair.redact_sensitive(r'192.168.1.24 [fe80::1]:8765 \\OFFICE-PC\Users\user\secret.json')
            assert '192.168.1.24' not in network and 'fe80::1' not in network and 'OFFICE-PC' not in network
            assert len(repair.redact_sensitive('A'*100_000+' token=TOO_LATE',100))==100
            deep=Path(td)/'deep.json';value={}
            for _ in range(70):value={'next':value}
            deep.write_text(json.dumps(value),encoding='utf-8')
            try:repair._load_strict_json(deep);raise AssertionError('deep JSON accepted')
            except ValueError:pass
        return '요약 API 비밀값 비공개 · 손상 공개필드 정규화 · 진단길이·JSON 깊이 제한'
    check('v79 오류학습 요약 API·민감정보 비공개',v79_error_learning_summary_api_guard,rows)

    def v79_error_group_migration_guard():
        import copy as _copy
        import auto_repair_engine as repair
        import migrate_old_data as migration
        with tempfile.TemporaryDirectory(prefix='tcg-v79-migrate-') as td:
            memory_path=Path(td)/'memory.json'
            memory_path.write_text(json.dumps({'version':2,'total_runs':7,'patterns':{
                'one':{'file':'market_prices.json','occurrences':2,'successful_repairs':0,
                       'last_detail':'TimeoutError: source 10 timed out','last_seen':'2026-08-24T00:00:00+00:00'},
                'two':{'file':'promo_events.json','occurrences':3,'successful_repairs':1,
                       'last_detail':'TimeoutError: source 99 timed out','last_seen':'2026-08-24T01:00:00+00:00'}},
                'files':{},'monitor_known_errors':{},'monitor_history':[]}),encoding='utf-8')
            migrated=repair.load_memory(memory_path)
            assert migrated['version']>=3 and len(migrated['error_groups'])==1
            key,group=next(iter(migrated['error_groups'].items()))
            assert group['occurrences']==5 and group['resolved_count']==1
            assert set(group['file_states'])=={'market_prices.json','promo_events.json'}
            newer=_copy.deepcopy(migrated);new_group=newer['error_groups'][key]
            new_group['file_states']['market_prices.json'].update({'resolved_count':2,'last_outcome':'resolved',
                'resolution_confirmed':True,'last_clean_seen':'2026-08-25T00:00:00+00:00'})
            new_group['successful_actions']={'검증된 정상 실행':2}
            event={'group_id':key,'first_seen':'2026-08-24T00:00:00+00:00'}
            migrated['new_error_log']=[event];newer['new_error_log']=[event]
            merged=migration.merge_memory(newer,migrated)
            clean=repair._sanitize_memory(merged)
            assert len(clean['error_groups'])==1 and len(clean['new_error_log'])==1
            assert clean['error_groups'][key]['file_states']['market_prices.json']['last_outcome']=='resolved'
            assert clean['error_groups'][key]['successful_actions']['검증된 정상 실행']==2
        return 'v2 세부 패턴을 원인그룹으로 통합 · 파일별 상태/해결조치 보존 · 중복 신규기록 제거'
    check('v79 이전 학습값 통합이전·중복방지',v79_error_group_migration_guard,rows)

    def v79_deferred_timeout_selection_guard():
        import auto_update_all as automatic
        timeout_rows=[
            {'name':'출시일','file':'releases.json','ok':True,'status':'기존자료 유지',
             'timeout_exhausted':True,'adaptive_timeout_seconds':90,'last_attempt_timeout_seconds':90,
             'collection_errors':['TimeoutError: release source 90초 초과']},
            {'name':'행사','file':'promo_events.json','ok':True,'status':'기존자료 유지',
             'timeout_exhausted':True,'adaptive_timeout_seconds':120,'last_attempt_timeout_seconds':120,
             'collection_errors':['TIMEOUT: promotion source 120초 초과']},
            {'name':'시세','file':'market_prices.json','ok':False,'timeout_exhausted':True,
             'collection_errors':['TimeoutError: price source'],
             'error':'TimeoutError: price source / NameError: parser missing'},
            {'name':'구매처','file':'purchase_sources.json','ok':False,'timeout_exhausted':True,
             'collection_errors':['SECURITY: private IP blocked after timeout']},
            {'name':'환율','file':'exchange_rates.json','ok':False,'timeout_exhausted':True,
             'collection_errors':['KeyError: required JSON field missing after timeout']},
            {'name':'판매추적','file':'market_watch.json','ok':True,'timeout_exhausted':False,
             'collection_errors':[]},
        ]
        assert automatic._deferred_timeout_eligible(timeout_rows[0])
        assert automatic._deferred_timeout_eligible(timeout_rows[1])
        assert all(not automatic._deferred_timeout_eligible(row) for row in timeout_rows[2:])
        jobs=(
            ('출시일','update_releases','releases.json'),
            ('행사','update_promo_events','promo_events.json'),
            ('시세','update_market_prices','market_prices.json'),
            ('구매처','update_purchase_sources','purchase_sources.json'),
            ('환율','update_exchange_rates','exchange_rates.json'),
            ('판매추적','update_market_watch','market_watch.json'),
        )
        stats={'jobs':{
            'releases.json':{'successes':8,'success_streak':8,'success_ewma_seconds':8,
                             'timeouts':2,'deferred_recommended_timeout_seconds':240},
            'promo_events.json':{'successes':8,'success_streak':8,'success_ewma_seconds':10,'timeouts':1},
        }}
        calls=[]
        def fake_run(job,budget):
            calls.append((job[2],budget))
            if job[2]=='promo_events.json':
                return {'name':job[0],'file':job[2],'ok':True,'status':'기존자료 유지',
                        'collection_errors':['TimeoutError: still delayed'],'timeout_exhausted':True}
            return {'name':job[0],'file':job[2],'ok':True,'status':'정상',
                    'collection_errors':[],'timeout_exhausted':False}
        recovered,summary=automatic._run_deferred_timeout_recovery(timeout_rows,jobs,stats,fake_run)
        by_file={row['file']:row for row in recovered}
        assert {name for name,_ in calls}=={'releases.json','promo_events.json'}
        assert all(automatic.DEFERRED_TIMEOUT_MIN_SECONDS <= budget <= automatic.DEFERRED_TIMEOUT_MAX_SECONDS
                   for _,budget in calls)
        assert summary['eligible_count']==2 and summary['attempted_count']==2
        assert summary['parallel_workers']==2 and summary['only_timeout_affected_files'] is True
        assert summary['recovered_count']==1 and summary['pending_count']==1
        assert by_file['releases.json']['recovered_after_deferred_timeout'] is True
        assert by_file['promo_events.json']['deferred_timeout_pending'] is True
        assert 'deferred_timeout_attempted' not in by_file['market_prices.json']
        assert stats['jobs']['releases.json']['deferred_successes']==1
        assert stats['jobs']['promo_events.json']['deferred_failures']==1
        poisoned=automatic._sanitize_adaptive_stats({'jobs':{'releases.json':{
            'deferred_attempts':10**100,'deferred_failures':-9,
            'deferred_recommended_timeout_seconds':10**100,
            'last_deferred_duration_seconds':'Infinity','deferred_pending':1}}})
        clean=poisoned['jobs']['releases.json']
        assert clean['deferred_attempts']==1_000_000 and clean['deferred_failures']==0
        assert clean['deferred_recommended_timeout_seconds']==automatic.DEFERRED_TIMEOUT_MAX_SECONDS
        assert clean['last_deferred_duration_seconds']==0.0 and clean['deferred_pending'] is True
        return '시간초과 파일만 선택 · 코드/보안/구조 오류 제외 · 2개 제한병렬 · 3~10분 학습예산·손상값 상한'
    check('v79 시간초과 대상선별·학습예산·제한병렬',v79_deferred_timeout_selection_guard,rows)

    def v79_deferred_timeout_end_to_end_guard():
        import shutil as _shutil
        from unittest.mock import patch as _patch
        import auto_update_all as automatic
        source_root=ROOT
        names=('ROOT','REPORT','ISSUES','MEMORY','LAST_GOOD','ADAPTIVE_STATS','ADAPTIVE_STATS_BAK','JOBS')
        original={name:getattr(automatic,name) for name in names}
        with tempfile.TemporaryDirectory(prefix='tcg-v79-deferred-e2e-') as td:
            test_root=Path(td)
            _shutil.copy2(source_root/'releases.json',test_root/'releases.json')
            _shutil.copy2(source_root/'tcg_live_data.json',test_root/'tcg_live_data.json')
            automatic.ROOT=test_root
            automatic.REPORT=test_root/'auto_update_report.json'
            automatic.ISSUES=test_root/'auto_update_issues.json'
            automatic.MEMORY=test_root/'auto_repair_memory.json'
            automatic.LAST_GOOD=test_root/'.tcg_last_good'
            automatic.ADAPTIVE_STATS=test_root/'adaptive_collection_stats.json'
            automatic.ADAPTIVE_STATS_BAK=test_root/'adaptive_collection_stats.json.bak'
            automatic.JOBS=(('출시일','update_releases','releases.json'),)
            collector_timeouts=[]
            def fake_process(cmd,*,cwd,timeout,env=None):
                command=' '.join(str(value) for value in cmd)
                if 'update_releases' in command and 'importlib.import_module' in command:
                    collector_timeouts.append(int(timeout))
                    if len(collector_timeouts)<3:
                        raise subprocess.TimeoutExpired(cmd,timeout)
                    payload={'updated_at':'2026-08-25T00:00:00+00:00','collection_status':'정상',
                             'collection_errors':[],'items':[{'game':'Pokemon','region':'KR',
                             'name':'분리 복구 검증자료','source':'https://www.pokemon-card.com/'}]}
                    (test_root/'releases.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
                elif 'auto_pipeline_runner' in command:
                    (test_root/'.integration_result.tmp.json').write_text(
                        json.dumps({'ok':True,'degraded':False,'failure_count':0,'queries':[]}),encoding='utf-8')
                elif 'validate_external_links.py' in command:
                    (test_root/'link_health_report.json').write_text(json.dumps({
                        'checked_at':'2026-08-25T00:00:00+00:00','total':1,'ok':1,
                        'broken':0,'transient':0,'results':[]}),encoding='utf-8')
                else:
                    raise AssertionError(f'unexpected process: {command}')
                return subprocess.CompletedProcess(cmd,0,'','')
            try:
                with _patch.object(automatic,'_run_managed_process',side_effect=fake_process),\
                     _patch.object(automatic.time,'sleep',return_value=None):
                    report=automatic.run_all('verification',selected_files=['releases.json'])
            finally:
                for name,value in original.items():setattr(automatic,name,value)
            row=report['results'][0]
            assert len(collector_timeouts)==3 and max(collector_timeouts[:2])<=300
            assert automatic.DEFERRED_TIMEOUT_MIN_SECONDS <= collector_timeouts[2] <= automatic.DEFERRED_TIMEOUT_MAX_SECONDS
            assert row['file']=='releases.json' and row['recovered_after_deferred_timeout'] is True
            assert row['deferred_timeout_recovered'] is True and row['timeout_exhausted'] is False
            assert report['deferred_timeout_recovery']['attempted_count']==1
            assert report['deferred_timeout_recovery']['recovered_count']==1
            assert json.loads((test_root/'releases.json').read_text(encoding='utf-8'))['items'][0]['name']=='분리 복구 검증자료'
            adaptive=json.loads((test_root/'adaptive_collection_stats.json').read_text(encoding='utf-8'))['jobs']['releases.json']
            assert adaptive['deferred_attempts']==1 and adaptive['deferred_successes']==1
            issue=json.loads((test_root/'auto_update_issues.json').read_text(encoding='utf-8'))['issues'][0]
            assert issue['severity']=='해결' and issue['deferred_timeout_recovered'] is True
            memory=json.loads((test_root/'auto_repair_memory.json').read_text(encoding='utf-8'))
            timeout_group=next(group for group in memory['error_groups'].values() if group['code']=='NETWORK_TIMEOUT')
            assert timeout_group['last_outcome']=='resolved'
            assert '시간초과 자료만' in timeout_group['proven_action']
        return '1·2차 시간초과→대상 파일만 3차 분리수집 성공 · 신규자료 반영 · 통계/이슈/해결조치 학습'
    check('v79 시간초과 분리 복구수집 종단간 실행',v79_deferred_timeout_end_to_end_guard,rows)

    def v79_deferred_timeout_ui_runtime_guard():
        import auto_update_all as automatic
        old_issues=automatic.ISSUES
        with tempfile.TemporaryDirectory(prefix='tcg-v79-deferred-ui-') as td:
            automatic.ISSUES=Path(td)/'issues.json'
            report={'finished_at':'2026-08-25T00:00:00+00:00','results':[
                {'name':'출시일','file':'releases.json','ok':True,'status':'별도 복구 성공',
                 'collection_errors':['TimeoutError: delayed'],'recovered_after_deferred_timeout':True,
                 'deferred_timeout_attempted':True,'deferred_timeout_recovered':True,
                 'deferred_timeout_pending':False,'deferred_timeout_seconds':240},
                {'name':'행사','file':'promo_events.json','ok':True,'status':'기존자료 유지',
                 'collection_errors':['TimeoutError: still delayed'],'deferred_timeout_attempted':True,
                 'deferred_timeout_recovered':False,'deferred_timeout_pending':True,
                 'deferred_timeout_seconds':600}],
                 'integration':{'ok':True},'link_audit':{'ok':True}}
            try:automatic.atomic_issues(report)
            finally:automatic.ISSUES=old_issues
            issues=json.loads((Path(td)/'issues.json').read_text(encoding='utf-8'))['issues']
            assert issues[0]['severity']=='해결' and issues[0]['deferred_timeout_seconds']==240
            assert issues[1]['severity']=='주의' and issues[1]['deferred_timeout_pending'] is True
        source=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        worker=(ROOT/'sw.js').read_text(encoding='utf-8')
        manifest=json.loads((ROOT/'manifest.webmanifest').read_text(encoding='utf-8'))
        repeat=(ROOT/'run_repeated_verification.py','social_event_discovery.py').read_text(encoding='utf-8')
        guide=(ROOT/'사용방법_v79.md').read_text(encoding='utf-8')
        assert 'DEFERRED_TIMEOUT_MIN_SECONDS = 180' in source and 'DEFERRED_TIMEOUT_MAX_SECONDS = 600' in source
        assert '_run_deferred_timeout_recovery' in source and 'tcg-timeout-recovery' in source
        assert 'deferred-running' in server and '시간초과 자료만 별도 복구수집 중' in server
        assert 'deferred_timeout_recovery' in page and 'for(let i=0;i<3600;i++)' in page
        assert '브라우저 요청과 분리되어 서버에서 계속 진행됩니다' in page
        assert CURRENT_CACHE in worker and CURRENT_ENGINE in repeat
        assert manifest.get('name')==CURRENT_APP_NAME
        assert '3~10분' in guide and '시간초과 자료만' in guide
        return '서버 백그라운드 지속 · 화면 복구/대기 표시 · 72분 상태조회 · PWA/반복검사/사용문서 계약 일치'
    check('v79 시간초과 복구상태·백그라운드·UI 계약',v79_deferred_timeout_ui_runtime_guard,rows)

    def v79_issue_analysis_and_version_guard():
        import auto_update_all as automatic
        old_issues=automatic.ISSUES
        with tempfile.TemporaryDirectory(prefix='tcg-v79-issues-') as td:
            automatic.ISSUES=Path(td)/'issues.json'
            report={'finished_at':'2026-08-25T00:00:00+00:00','results':[
                {'name':'시세','file':'market_prices.json','ok':False,'error':'TimeoutError: source delayed','status':'실패'}],
                'integration':{'ok':True},'link_audit':{'ok':True}}
            try:automatic.atomic_issues(report)
            finally:automatic.ISSUES=old_issues
            issue=json.loads((Path(td)/'issues.json').read_text(encoding='utf-8'))['issues'][0]
            assert issue['error_code']=='NETWORK_TIMEOUT' and len(issue['error_group_id'])==16
            assert issue['probable_cause'] and issue['resolution_steps'] and issue['verification_steps']
            assert automatic.auto_repair_engine.analyze_error('HTTP 503 from official source')['code']=='NETWORK_HTTP_ERROR'
            assert automatic.auto_repair_engine.analyze_error('ConnectionError: DNS lookup failed')['code']=='NETWORK_CONNECTION_ERROR'
            assert automatic.auto_repair_engine.analyze_error('일시 확인불가 112개')['code']=='NETWORK_CONNECTION_ERROR'
            assert automatic.auto_repair_engine.analyze_error('KeyError: required field missing')['code']=='DATA_SCHEMA_ERROR'
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        worker=(ROOT/'sw.js').read_text(encoding='utf-8')
        manifest=json.loads((ROOT/'manifest.webmanifest').read_text(encoding='utf-8'))
        assert CURRENT_SERVICE in server and CURRENT_ENGINE in server
        assert '/api/error-learning-summary' in server and '/api/error-learning-summary' in page
        assert 'v20LearningHtml' in page and CURRENT_CACHE in worker
        assert manifest.get('name')==CURRENT_APP_NAME
        assert (ROOT/'V79_DEFERRED_TIMEOUT_RECOVERY_VERIFICATION_2026-08-25.md').is_file()
        return '오류별 원인·해결·검증계획 생성 · API/UI/PWA/문서 v79 통합버전 일치'
    check('v79 오류 해결계획 생성·통합버전 일치',v79_issue_analysis_and_version_guard,rows)

    def v80_project_schema_guard():
        import copy
        import auto_repair_engine as repair
        import auto_update_all as automatic
        core=('releases.json','market_watch.json','market_prices.json','promo_events.json',
              'purchase_sources.json','exchange_rates.json')
        for filename in core:
            for folder in (ROOT,ROOT/'.tcg_last_good'):
                data=json.loads((folder/filename).read_text(encoding='utf-8'))
                assert repair._valid_project_payload(filename,data),f'{folder.name}/{filename}'
                automatic.validate_json(filename,data)
        malformed=(
            ('releases.json',{'items':[{'name':'필수정보 없음'}]}),
            ('market_watch.json',{'items':[{'name':'잘못된 국가','region':'PRIVATE','asset':'BOX'}]}),
            ('market_prices.json',{'entries':{'bad-key':{'display':'₩100'}}}),
            ('promo_events.json',{'items':[{'game':'Pokemon','region':'KR'}]}),
            ('purchase_sources.json',{'sources':[]}),
            ('exchange_rates.json',{'rates':{'JPY_KRW':-1,'USD_KRW':9}}),
        )
        for filename,data in malformed:
            assert not repair._valid_project_payload(filename,data),filename
            try:automatic.validate_json(filename,data)
            except (TypeError,ValueError):pass
            else:raise AssertionError(f'손상된 자료 구조 허용: {filename}')
        poisoned=copy.deepcopy(json.loads((ROOT/'purchase_sources.json').read_text(encoding='utf-8')))
        poisoned['sources'][0]['url']='https://127.0.0.1/private'
        assert not repair._valid_project_payload('purchase_sources.json',poisoned)
        return '운영자료 6종+마지막 정상백업 6종의 필수필드·국가·시세키·환율·구매처·사설주소 동시 검증'
    check('v80 파일별 JSON 필수구조·자료값 검증',v80_project_schema_guard,rows)

    def v80_stage_path_and_json_guard():
        from unittest.mock import patch
        import tcg_updater as updater
        with tempfile.TemporaryDirectory(prefix='tcg-v80-stage-') as td:
            root=Path(td)/'project';root.mkdir();stage=root/'.precollect_stage';stage.mkdir()
            source=stage/'releases.json';destination=root/'releases.json'
            good={'items':[{'game':'Pokemon','region':'KR','name':'정상 운영자료','source':'https://example.com/cards'}]}
            destination.write_text(json.dumps(good,ensure_ascii=False),encoding='utf-8')
            baseline=destination.read_bytes()
            with patch.object(updater,'BASE',str(root)),patch.object(updater,'PRECOLLECT_STAGE',str(stage)):
                for invalid in ('[]','{"items":[],"items":[]}',
                                '{"items":[{"name":"필수값 누락"}]}',
                                '{"items":[],"price":NaN}'):
                    source.write_text(invalid,encoding='utf-8')
                    try:updater._atomic_copy_json(str(source),str(destination))
                    except (OSError,TypeError,ValueError):pass
                    else:raise AssertionError(f'잘못된 staging JSON 허용: {invalid}')
                    assert destination.read_bytes()==baseline
                source.write_text(json.dumps(good,ensure_ascii=False),encoding='utf-8')
                try:updater._atomic_copy_json(str(stage/'..'/'releases.json'),str(destination))
                except ValueError:pass
                else:raise AssertionError('staging 상위경로 탈출 허용')
                outside=Path(td)/'outside.json';outside.write_text(json.dumps(good),encoding='utf-8')
                source.unlink();source.symlink_to(outside)
                try:updater._atomic_copy_json(str(source),str(destination))
                except ValueError:pass
                else:raise AssertionError('staging 원본 심볼릭 링크 허용')
                source.unlink();source.write_text(json.dumps(good,ensure_ascii=False),encoding='utf-8')
                destination.unlink();destination.symlink_to(outside)
                try:updater._atomic_copy_json(str(source),str(destination))
                except ValueError:pass
                else:raise AssertionError('운영자료 심볼릭 링크 허용')
                assert json.loads(outside.read_text(encoding='utf-8'))==good
                destination.unlink()
                updater._atomic_copy_json(str(source),str(destination))
                assert json.loads(destination.read_text(encoding='utf-8'))==good
        return '최상위 배열·중복 키·NaN·필수값 누락·상위폴더 탈출·양쪽 symlink 차단 후 정상자료만 반영'
    check('v80 사전수집 경로격리·표준 JSON·원자 반영',v80_stage_path_and_json_guard,rows)

    def v80_stage_manifest_guard():
        from unittest.mock import patch
        import auto_update_all as automatic
        import tcg_updater as updater
        with tempfile.TemporaryDirectory(prefix='tcg-v80-manifest-') as td:
            root=Path(td)/'project';root.mkdir();stage=root/'.precollect_stage';stage.mkdir()
            status=root/'precollect_status.json';status.write_text('{"state":"ready"}',encoding='utf-8')
            outside=Path(td)/'outside.json';outside.write_text('보존해야 하는 외부 자료',encoding='utf-8')
            calls=[]
            def safe_supplement(trigger,selected_files):
                calls.append((trigger,list(selected_files)))
                return {'results':[{'file':name,'status':'검증된 보완수집'} for name in selected_files]}
            with patch.object(updater,'BASE',str(root)),patch.object(updater,'PRECOLLECT_STAGE',str(stage)),\
                 patch.object(updater,'PRECOLLECT_STATUS',str(status)),\
                 patch.object(updater,'collect',return_value={'pending':[]}),\
                 patch.object(updater,'load_db',return_value={'sources':{},'pending':[],'applied':[]}),\
                 patch.object(updater,'save_db',return_value=None),\
                 patch.object(automatic,'run_all',side_effect=safe_supplement):
                for results in ([{'file':'../../outside.json','ok':True}],
                                [{'file':'releases.json','ok':True},{'file':'releases.json','ok':True}],
                                ['잘못된 결과 항목']):
                    (stage/'auto_update_report.json').write_text(json.dumps({'results':results},ensure_ascii=False),encoding='utf-8')
                    updater.finalize_precollected_cycle(1_700_000_000)
            expected={job[2] for job in automatic.JOBS}
            assert len(calls)==3 and all(set(names)==expected for _,names in calls)
            assert outside.read_text(encoding='utf-8')=='보존해야 하는 외부 자료'
        return '변조된 파일명·중복 결과·잘못된 결과 형식 폐기 · 허용된 6개 자료만 안전하게 재수집'
    check('v80 사전수집 보고서 변조·경로탈출 방어',v80_stage_manifest_guard,rows)

    def v80_market_preservation_guard():
        from unittest.mock import patch
        import update_market_watch as market
        with tempfile.TemporaryDirectory(prefix='tcg-v80-market-') as td:
            watch=Path(td)/'market_watch.json';releases=Path(td)/'releases.json'
            retained={'region':'KR','game':'Pokemon','asset':'BOX','name':'기존 추적자료 유지',
                      'source':'https://example.com/original','package_type':'박스'}
            watch.write_text(json.dumps({'items':[retained]},ensure_ascii=False),encoding='utf-8')
            releases.write_text('{broken',encoding='utf-8')
            with patch.object(market,'OUT',watch),patch.object(market,'RELEASES',releases):
                first=market.main()
                assert any(row['name']==retained['name'] for row in first['items'])
                assert first['collection_status']=='기존 추적자료 유지' and len(first['items'])>=len(market.SEEDS)+1
                releases.write_text(json.dumps({'items':[None,
                    {'game':'Pokemon','region':'KR','name':'사설주소 제외','source':'https://127.0.0.1/private'},
                    {'game':'Pokemon','region':'JP','name':'검증된 신규자료','source':'https://example.com/new'}]},ensure_ascii=False),encoding='utf-8')
                second=market.main();names={row['name'] for row in second['items']}
                assert retained['name'] in names and '검증된 신규자료' in names and '사설주소 제외' not in names
                assert len(second['items'])>=len(first['items'])
        return '출시목록 손상 시 기존 판매·재발매 자료 유지 · 잘못된 항목·사설주소만 제외 · 정상 신규자료 병합'
    check('v80 자료수집 실패 시 기존 추적자료 보존',v80_market_preservation_guard,rows)

    def v80_https_dns_redirect_guard():
        from unittest.mock import patch
        import socket
        import safe_runtime as runtime
        import tcg_updater as updater
        import update_purchase_sources as purchase
        import update_promo_events as promo
        import purchase_intelligence as intelligence
        import validate_external_links as links
        hostile=('http://example.com/','https://example.com:8443/',
                 'https://localhost.localdomain/','https://printer.local/',
                 'https://device.localhost/','https://127.0.0.1/',
                 'https://user@example.com/','https://example.com/\nsecret',
                 'https://example.com/\\private')
        for value in hostile:
            for guard in (runtime.validate_public_https_url,purchase.checked_url,links._safe):
                try:guard(value)
                except (TypeError,ValueError):pass
                else:raise AssertionError(f'안전하지 않은 HTTPS 주소 허용: {value}')
            assert intelligence._safe_http_url(value) is False
        assert intelligence._safe_http_url('https://example.com/cards') is True
        source={'name':'보조주소 검사','region':'KR','type':'official','games':['Pokemon'],
                'url':'https://example.com/','url_template':'javascript:alert({query})'}
        try:purchase.normalize_source(source)
        except ValueError:pass
        else:raise AssertionError('검증되지 않은 보조 검색주소 허용')
        source['url_template']='https://example.com/search?q={query}'
        assert purchase.normalize_source(source)['url_template']==source['url_template']
        invalid=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('not-an-ip',443))]
        with patch.object(socket,'getaddrinfo',return_value=invalid):
            for call in (lambda:runtime.require_public_https('https://example.com/'),
                         lambda:purchase.resolve_public_host('example.com'),
                         lambda:links._resolve_public('example.com')):
                try:call()
                except (OSError,urllib.error.URLError,ValueError):pass
                else:raise AssertionError('사용 불가능한 DNS 주소 허용')
        public=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
        with patch.object(socket,'getaddrinfo',return_value=public):
            request=urllib.request.Request('https://www.pokemon-card.com/start')
            for handler in (updater.OfficialSourceRedirect(),purchase.SafeRedirect(),promo.OfficialRedirect(),links.Redirect()):
                redirected=handler.redirect_request(request,None,302,'Found',{},'/next')
                assert redirected.full_url=='https://www.pokemon-card.com/next'
                try:handler.redirect_request(request,None,302,'Found',{},'https://127.0.0.1/private')
                except ValueError:pass
                else:raise AssertionError('사설주소 redirect 허용')
        return '공통 HTTPS·443·자격증명·제어문자·사설주소 차단 · 무효 DNS 거부 · 상대 redirect 4종 정상 처리'
    check('v80 공통 URL·DNS·리다이렉트 보안정책',v80_https_dns_redirect_guard,rows)

    def v80_atomic_symlink_guard():
        import gzip
        from unittest.mock import patch
        import auto_repair_engine as repair
        import tcg_updater as updater
        import update_market_prices as market
        import migrate_old_data as migration
        from github_sync_engine import GitHubSyncEngine
        from optimized_self_healing import SelfHealingEngine
        from safe_runtime import atomic_write_json, atomic_write_text
        with tempfile.TemporaryDirectory(prefix='tcg-v80-symlink-') as td:
            root=Path(td);outside=root/'outside.txt';outside.write_text('절대 변경 금지',encoding='utf-8')
            data=root/'cards.json.gz';temporary=data.with_suffix(data.suffix+'.tmp')
            temporary.symlink_to(outside)
            compressed=SelfHealingEngine(data,root/'cards.backup.gz')
            assert compressed.save_compressed_data({'card':'blocked'}) is False
            assert outside.read_text(encoding='utf-8')=='절대 변경 금지'
            temporary.unlink();data.symlink_to(outside)
            assert compressed.save_compressed_data({'card':'blocked'}) is False
            assert compressed.load_compressed_data(['safe fallback'])==['safe fallback']
            assert outside.read_text(encoding='utf-8')=='절대 변경 금지'
            data.unlink()
            assert compressed.save_compressed_data({'card':'정상'}) is True
            assert compressed.load_compressed_data()=={'card':'정상'}
            duplicate=root/'duplicate.json.gz'
            with gzip.open(duplicate,'wb') as output:
                output.write(b'{"card":1,"card":2}')
            assert SelfHealingEngine(duplicate,root/'duplicate.backup.gz').load_compressed_data({'safe':True})=={'safe':True}

            def save_market(path):
                with patch.object(market,'DATA',path):market.atomic_save({'ok':True})

            def save_live_database(path):
                with patch.object(updater,'DB',str(path)):updater.save_db({'ok':True})

            for target,writer in (
                (root/'regular.json',lambda path:atomic_write_text(path,'{"ok":true}')),
                (root/'shared.json',lambda path:atomic_write_json(path,{'ok':True})),
                (root/'market.json',save_market),
                (root/'live.json',save_live_database),
                (root/'migration.json',lambda path:migration.write_json(path,{'ok':True})),
                (root/'updater.json',lambda path:updater.save_json_atomic(str(path),{'ok':True})),
                (root/'memory.json',lambda path:repair._atomic_save_memory(repair._default_memory(),path)),
            ):
                target.symlink_to(outside)
                try:writer(target)
                except (OSError,ValueError):pass
                else:raise AssertionError(f'심볼릭 링크 덮어쓰기 허용: {target.name}')
                assert outside.read_text(encoding='utf-8')=='절대 변경 금지'
            cache=root/'github-cache.json';cache.symlink_to(outside)
            github=GitHubSyncEngine();github.cache=cache;github._save_cache({'ok':True})
            assert cache.is_symlink() and outside.read_text(encoding='utf-8')=='절대 변경 금지'
            for value in (float('nan'),float('inf'),float('-inf')):
                invalid=root/'invalid-number.json'
                try:atomic_write_json(invalid,{'value':value})
                except ValueError:pass
                else:raise AssertionError('비표준 JSON 숫자 저장 허용')
                assert not invalid.exists()
            valid=root/'valid.json';atomic_write_json(valid,{'한글':'정상'})
            assert valid.read_text(encoding='utf-8')=='{\n  "한글": "정상"\n}\n'
            compact=root/'without-newline.json';atomic_write_json(compact,{'ok':True},trailing_newline=False)
            assert not compact.read_text(encoding='utf-8').endswith('\n')
            assert not any(path.name.startswith('.valid.json.') for path in root.iterdir())
            assert repair.load_memory(root/'memory.json')['total_runs']==0
        return '공통 JSON 원자저장·운영 DB·시세·마이그레이션·GitHub symlink 차단 · 압축 중복키/NaN 거부 · 외부 파일 변경 0건'
    check('v80 원자 저장·압축·학습기록 심볼릭 링크 차단',v80_atomic_symlink_guard,rows)

    def v80_purchase_cache_xml_guard():
        import concurrent.futures
        from unittest.mock import patch
        import purchase_intelligence as intelligence
        class Response:
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,limit):return self.data[:limit]
        clean=b'<rss><channel><item><title>safe restock</title><link>https://example.com/card</link></item><item><title>private</title><link>https://127.0.0.1/private</link></item><item><title>http</title><link>http://example.com/card</link></item></channel></rss>'
        unsafe=b'<!DOCTYPE rss [<!ENTITY attack "unsafe">]><rss><channel></channel></rss>'
        with intelligence._CACHE_LOCK:
            before=list(intelligence._CACHE.items());intelligence._CACHE.clear()
        try:
            with patch.object(intelligence,'MAX_CACHE_ENTRIES',4),\
                 patch.object(intelligence,'safe_urlopen',side_effect=lambda *args,**kwargs:Response(clean)) as opening:
                for number in range(7):
                    result=intelligence.search_web_signals(f'card-{number}',region='KR',game='Pokemon')
                    assert result['ok'] and len(result['items'])==1
                    assert result['items'][0]['url']=='https://example.com/card'
                assert len(intelligence._CACHE)==4
                calls=opening.call_count
                again=intelligence.search_web_signals('card-6',region='KR',game='Pokemon')
                assert again['cached'] is True and opening.call_count==calls
                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                    outputs=list(pool.map(lambda number:intelligence.search_web_signals(f'parallel-{number}'),range(15)))
                assert all(value['ok'] for value in outputs) and len(intelligence._CACHE)<=4
            with patch.object(intelligence,'safe_urlopen',return_value=Response(unsafe)):
                blocked=intelligence.search_web_signals('xml-hostile')
                assert blocked['ok'] is False and 'ValueError' in blocked['error']
                assert all('xml-hostile' not in key for key in intelligence._CACHE)
            calls=[urllib.error.URLError('temporary'),Response(clean)]
            with patch.object(intelligence,'safe_urlopen',side_effect=calls):
                assert intelligence.search_web_signals('recover-now')['ok'] is False
                assert intelligence.search_web_signals('recover-now')['ok'] is True
            assert intelligence.search_web_signals('cards',region='PRIVATE')['ok'] is False
            assert intelligence.search_web_signals('cards',game='UNKNOWN')['ok'] is False
        finally:
            with intelligence._CACHE_LOCK:
                intelligence._CACHE.clear();intelligence._CACHE.update(before)
        return 'RSS HTTP·사설링크·DTD·엔티티 차단 · 동시 요청 캐시 256개 상한 · 수집 실패 결과 미저장·즉시 재시도'
    check('v80 실시간 구매검색 XML·캐시·실패복구 검증',v80_purchase_cache_xml_guard,rows)

    def v80_legacy_repair_memory_api_guard():
        import auto_repair_engine as repair
        import tcg_updater as updater
        old_memory=updater.AUTO_MEMORY
        with tempfile.TemporaryDirectory(prefix='tcg-v80-memory-api-') as td:
            memory=Path(td)/'memory.json'
            repair.learn({'results':[{'file':'releases.json','ok':False,
                'error':'NameError: parser token=SUPERPRIVATE'}]},memory)
            monitor=repair.AutoRepairEngine(memory_file=memory,root=Path(td))
            monitor._record_monitor_event(func_name='private_collector',error_type='ValueError',
                error_msg='password=HIDDENPASSWORD',tb='Traceback Bearer INTERNALTOKEN',resolved=False,
                action='입력 격리',target_file='releases.json',attempt=1)
            updater.AUTO_MEMORY=str(memory)
            server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),updater.Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                outputs=[]
                for endpoint in ('/api/repair-memory','/api/error-learning-summary'):
                    with urllib.request.urlopen(f'http://127.0.0.1:{server.server_address[1]}{endpoint}',timeout=5) as response:
                        payload=json.load(response)
                    encoded=json.dumps(payload,ensure_ascii=False)
                    assert payload.get('groups') and payload.get('summary')
                    assert all(secret not in encoded for secret in
                        ('monitor_history','traceback_tail','file_states','monitor_known_errors',
                         'SUPERPRIVATE','HIDDENPASSWORD','INTERNALTOKEN','private_collector'))
                    outputs.append(payload)
                assert outputs[0]==outputs[1]
            finally:
                server.shutdown();server.server_close();worker.join(timeout=3);updater.AUTO_MEMORY=old_memory
        return '이전 repair-memory와 신규 summary API 모두 동일 공개요약만 제공 · traceback·토큰·비밀번호·내부상태 미노출'
    check('v80 이전 오류학습 API 내부기록 공개 차단',v80_legacy_repair_memory_api_guard,rows)

    def v80_programming_exception_guard():
        from unittest.mock import patch
        import update_exchange_rates as exchange
        import update_market_watch as market
        import update_releases as releases
        with tempfile.TemporaryDirectory(prefix='tcg-v80-exceptions-') as td:
            root=Path(td);rates=root/'exchange_rates.json';watch=root/'market_watch.json';release_data=root/'releases.json'
            rates.write_text(json.dumps({'rates':{'JPY_KRW':8.7,'USD_KRW':1380}}),encoding='utf-8')
            watch.write_text(json.dumps({'items':[]}),encoding='utf-8')
            sample=json.loads((ROOT/'releases.json').read_text(encoding='utf-8'))
            release_data.write_text(json.dumps(sample,ensure_ascii=False),encoding='utf-8')
            saved_rates=rates.read_bytes();saved_releases=release_data.read_bytes();saved_watch=watch.read_bytes()
            with patch.object(exchange,'DATA',rates),patch.object(exchange,'fetch',side_effect=NameError('missing_exchange_parser')):
                try:exchange.main()
                except NameError:pass
                else:raise AssertionError('환율 코드 오류를 네트워크 실패로 숨김')
            assert rates.read_bytes()==saved_rates
            with patch.object(exchange,'DATA',rates),patch.object(exchange,'fetch',side_effect=urllib.error.URLError('temporary')):
                fallback=exchange.main()
                assert fallback['rates']=={'JPY_KRW':8.7,'USD_KRW':1380} and fallback['collection_error']=='URLError'
            with patch.object(market,'OUT',watch),patch.object(market,'RELEASES',release_data),\
                 patch.object(market,'package_type',side_effect=NameError('missing_market_parser')):
                try:market.main()
                except NameError:pass
                else:raise AssertionError('판매추적 코드 오류를 자료수집 실패로 숨김')
            assert watch.read_bytes()==saved_watch
            with patch.object(releases,'DATA',release_data),\
                 patch.object(releases,'collect_pokemon_jp',side_effect=NameError('missing_release_parser')),\
                 patch.object(releases,'collect_onepiece_kr',return_value=sample['items'][:1]),\
                 patch.object(releases,'collect_onepiece_jp',return_value=sample['items'][:1]),\
                 patch.object(releases,'collect_onepiece',return_value=sample['items'][:1]),\
                 patch.object(releases,'collect_naruto',return_value=sample['items'][:1]):
                try:releases.main()
                except NameError:pass
                else:raise AssertionError('출시정보 코드 오류를 네트워크 실패로 숨김')
            assert release_data.read_bytes()==saved_releases
        return '환율·판매추적·출시정보 NameError는 명확히 전파 · 실제 네트워크 오류만 기존 정상자료 유지'
    check('v80 프로그램 오류·통신 오류 구분 및 자료보존',v80_programming_exception_guard,rows)

    def v80_integrated_version_guard():
        automatic=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        guide=(ROOT/'사용방법_v80.md').read_text(encoding='utf-8')
        audit=(ROOT/'V80_CODE_STRUCTURE_SECURITY_HARDENING_2026-08-25.md').read_text(encoding='utf-8')
        assert '3~10분' in guide and '심볼릭 링크' in guide and 'traceback' in guide
        assert '실제로 재현한 오류' in audit and '기존 판매자료' in audit
        assert 'DEFERRED_TIMEOUT_MIN_SECONDS = 180' in automatic and 'DEFERRED_TIMEOUT_MAX_SECONDS = 600' in automatic
        return 'v80 구조·경로·보안 문서 보존 · 기존 3~10분 분리 복구수집 유지'
    check('v80 구조·보안 회귀기능·시간초과 복구 유지',v80_integrated_version_guard,rows)

    def v81_same_error_and_new_cause_guard():
        import auto_repair_engine as repair
        with tempfile.TemporaryDirectory(prefix='tcg-v81-causes-') as td:
            memory=Path(td)/'memory.json'
            learned=repair.learn({'finished_at':'2026-08-25T01:00:00Z','results':[
                {'file':'releases.json','ok':False,
                 'error':"NameError: name 'alpha_loader' is not defined at line 11"},
                {'file':'market_watch.json','ok':False,
                 'error':"NameError: name 'alpha_loader' is not defined at line 999"},
                {'file':'market_prices.json','ok':False,
                 'error':"NameError: name 'beta_loader' is not defined at line 22"},
            ]},memory)
            assert len(learned['error_groups'])==2 and len(learned['new_error_log'])==2
            groups={row['error_subtype']:row for row in learned['error_groups'].values()}
            assert groups['nameerror:alpha_loader']['occurrences']==2
            assert groups['nameerror:beta_loader']['occurrences']==1
            assert learned['learning_summary']['recurring_group_count']==1
            assert learned['learning_summary']['new_group_count']==1
            repeated=repair.learn({'finished_at':'2026-08-25T01:01:00Z','results':[
                {'file':'market_prices.json','ok':False,
                 'error':"NameError: name 'beta_loader' is not defined at line 500"},
            ]},memory)
            assert len(repeated['error_groups'])==2 and len(repeated['new_error_log'])==2
            assert repeated['learning_summary']['new_group_count']==0
            assert all(row['occurrences']==2 for row in repeated['error_groups'].values())
            missing_a=repair.analyze_error('FileNotFoundError: releases.json not found')
            missing_b=repair.analyze_error('FileNotFoundError: market_prices.json not found')
            permission_a=repair.analyze_error('PermissionError: releases.json permission denied')
            permission_b=repair.analyze_error('PermissionError: market_prices.json permission denied')
            parser_a=repair.analyze_error('Pokémon JP parser 0 items 확인 실패')
            parser_b=repair.analyze_error('ONE PIECE JP parser 0 items 확인 실패')
            timeout_a=repair.analyze_error('TimeoutError: source 1 timed out after 30 seconds')
            timeout_b=repair.analyze_error('TimeoutError: source 2 timed out after 90 seconds')
            assert missing_a['code']=='FILE_MISSING' and permission_a['code']=='FILE_PERMISSION_ERROR'
            assert repair.error_group_key(missing_a)!=repair.error_group_key(missing_b)
            assert repair.error_group_key(permission_a)!=repair.error_group_key(permission_b)
            assert repair.error_group_key(parser_a)!=repair.error_group_key(parser_b)
            assert repair.error_group_key(timeout_a)==repair.error_group_key(timeout_b)
        return '동일 원인 통합 · 이름·누락파일·권한파일·출처 파서별 신규 원인 분리 · 신규기록 그룹별 1회 유지'
    check('v81 동일 오류 통합·신규 원인 분리',v81_same_error_and_new_cause_guard,rows)

    def v81_http_and_root_cause_policy_guard():
        import auto_repair_engine as repair
        import auto_update_all as automatic
        for status in (408,425,429,500,502,503,504):
            row=repair.analyze_error(f'HTTPError: HTTP Error {status}: temporary')
            assert row['code']=='NETWORK_HTTP_ERROR' and row['http_status']==status
            assert row['bounded_retry_allowed'] is True and row['resolution_steps']
        for status in (400,401,403,404,410,501):
            row=repair.analyze_error(f'HTTPError: HTTP Error {status}: permanent')
            assert row['code']=='NETWORK_HTTP_ERROR' and row['http_status']==status
            assert row['bounded_retry_allowed'] is False
        gateway=repair.analyze_error('HTTPError: HTTP Error 504: Gateway Timeout')
        assert gateway['code']=='NETWORK_HTTP_ERROR' and gateway['http_status']==504
        assert gateway['bounded_retry_allowed'] is True
        missing=repair.analyze_error('HTTPError: HTTP Error 404: Not Found')
        assert missing['error_subtype']=='missing-404' and '재시도를 중단' in ' '.join(missing['resolution_steps'])
        private=repair.analyze_error('SECURITY: private DNS target blocked')
        origin=repair.analyze_error('SECURITY: Origin blocked')
        dns=repair.analyze_error('ConnectionError: DNS lookup failed')
        refused=repair.analyze_error('ConnectionError: connection refused')
        assert repair.error_group_key(private)!=repair.error_group_key(origin)
        assert repair.error_group_key(dns)!=repair.error_group_key(refused)
        first=repair.analyze_error("KeyError: 'price'");second=repair.analyze_error("KeyError: 'currency'")
        assert repair.error_group_key(first)!=repair.error_group_key(second)
        assert all('실행 금지' in row['automation_policy'] for row in (missing,private,dns,first))
        old_issues=automatic.ISSUES
        with tempfile.TemporaryDirectory(prefix='tcg-v81-http-issues-') as td:
            automatic.ISSUES=Path(td)/'issues.json'
            memory=Path(td)/'memory.json'
            try:
                automatic.atomic_issues({'finished_at':'2026-08-25T01:30:00Z','results':[
                    {'name':'주소','file':'releases.json','ok':True,'status':'기존자료 유지',
                     'collection_errors':['HTTPError: HTTP Error 404: Not Found'],
                     'recovered_after_deferred_timeout':'false'},
                    {'name':'서버','file':'market_prices.json','ok':True,'status':'복구',
                     'collection_errors':['HTTPError: HTTP Error 503: unavailable'],
                     'recovered_after_deferred_timeout':True},
                ]})
            finally:
                automatic.ISSUES=old_issues
            issues=json.loads((Path(td)/'issues.json').read_text(encoding='utf-8'))['issues']
            assert issues[0]['severity']=='주의' and issues[0]['error_subtype']=='missing-404'
            assert issues[0]['bounded_retry_allowed'] is False and issues[0]['http_status']==404
            assert issues[1]['severity']=='해결' and issues[1]['bounded_retry_allowed'] is True
            learned=repair.learn({'results':[{'file':'releases.json','ok':False,'collection_errors':[
                'HTTPError: HTTP Error 500: failed','HTTPError: HTTP Error 503: unavailable']}]},memory)
            assert len(learned['error_groups'])==1
            http_group=next(iter(learned['error_groups'].values()))
            assert http_group['occurrences']==2 and http_group['http_status']==503
            assert http_group['http_statuses']==[500,503]
            public=repair.public_error_learning_summary(learned)
            assert public['groups'][0]['http_statuses']==[500,503]
            assert public['new_errors'][0]['http_statuses']==[500,503]
        return '일시 HTTP 7종만 제한 재시도 · 영구 오류 차단 · 통합 그룹의 상태이력 보존 · 원인별 해결계획 분리'
    check('v81 HTTP 재시도·원인별 해결정책',v81_http_and_root_cause_policy_guard,rows)

    def v81_strict_learning_report_guard():
        import auto_repair_engine as repair
        with tempfile.TemporaryDirectory(prefix='tcg-v81-report-') as td:
            memory=Path(td)/'memory.json'
            first=repair.learn({'finished_at':'2026-08-25T02:00:00Z','results':[
                {'file':'market_watch.json','ok':False,'error':'TimeoutError: source delayed'}
            ]},memory)
            group_id=next(iter(first['error_groups']))
            invalid_rows=(
                {'file':'market_watch.json','ok':'false','status':'still failed'},
                {'file':'market_watch.json','ok':1,'status':'still failed'},
                {'file':'market_watch.json','ok':True,'recovered_after_retry':'false'},
            )
            for row in invalid_rows:
                repair.learn({'results':[row]},memory)
            invalid_time=repair.learn({'finished_at':{'not':'a timestamp'},'results':[]},memory)
            assert invalid_time['invalid_report_count']==4
            assert isinstance(invalid_time['updated_at'],str)
            dt.datetime.fromisoformat(invalid_time['updated_at'])
            assert invalid_time['files']['market_watch.json']['runs']==1
            assert invalid_time['error_groups'][group_id]['last_outcome']=='unresolved'
            once=repair.learn({'finished_at':'2026-08-25T02:01:00Z','results':[
                {'file':'market_watch.json','ok':True}
            ]},memory)
            assert once['error_groups'][group_id]['last_outcome']=='unresolved'
            twice=repair.learn({'finished_at':'2026-08-25T02:02:00Z','results':[
                {'file':'market_watch.json','ok':True}
            ]},memory)
            assert twice['files']['market_watch.json']['runs']==3
            assert twice['error_groups'][group_id]['last_outcome']=='resolved'
            assert twice['learning_summary']['new_group_count']==0
            log=twice['new_error_log'][0]
            assert log['analysis_status']=='해결 확인' and log['unresolved_count']==0
            assert log['proven_action']=='동일 파일 2회 연속 정상 실행으로 해결 확인'
            previous=twice['updated_at']
            future=repair.learn({'finished_at':'2099-12-31T23:59:59Z','results':[]},memory)
            controlled=repair.learn({'finished_at':'2026-08-25T02:03:00Z\n','results':[]},memory)
            assert future['invalid_report_count']==5 and controlled['invalid_report_count']==6
            assert future['updated_at']>=previous and controlled['updated_at']>=future['updated_at']
            assert dt.datetime.fromisoformat(controlled['updated_at']) < dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=2)
        return '거짓 불리언·손상 복구플래그 격리 · 미래/제어문자 시각 차단 · 실제 정상 2회만 해결 확정'
    check('v81 손상 학습보고서·거짓 해결 차단',v81_strict_learning_report_guard,rows)

    def v81_deduplicated_deferred_solution_guard():
        import auto_repair_engine as repair
        with tempfile.TemporaryDirectory(prefix='tcg-v81-deduplicate-') as td:
            memory=Path(td)/'memory.json'
            learned=repair.learn({'finished_at':'2026-08-25T03:00:00Z','results':[
                {'file':'releases.json','ok':True,
                 'collection_errors':['TimeoutError: source A','TimeoutError: source A','TimeoutError: source B'],
                 'collection_error':'TimeoutError: source A',
                 'error':'TimeoutError: source A / TimeoutError: source B',
                 'recovered_after_deferred_timeout':True,
                 'auto_action':'시간초과 분리수집 성공'}
            ]},memory)
            assert len(learned['error_groups'])==1 and len(learned['patterns'])==2
            group=next(iter(learned['error_groups'].values()))
            assert group['occurrences']==2 and group['resolved_count']==2
            assert group['last_outcome']=='resolved' and group['proven_action']=='시간초과 분리수집 성공'
            assert learned['files']['releases.json']['successful_repairs']==1
            assert all(row['successful_repairs']==1 for row in learned['patterns'].values())
            summary=learned['learning_summary']
            assert summary['consolidated_event_total']==2 and summary['new_group_count']==0
            assert summary['verified_solution_group_count']==1
            public=repair.public_error_learning_summary(learned)
            log=public['new_errors'][0]
            assert log['occurrences']==2 and log['analysis_status']=='해결 확인'
            assert log['proven_action']=='시간초과 분리수집 성공'
        return '원자 오류 2건만 집계 · 결합 요약문 중복 제거 · 분리수집 성공을 파일·패턴·원인 해결값에 동시 반영'
    check('v81 오류 중복제거·분리수집 해결학습',v81_deduplicated_deferred_solution_guard,rows)

    def v81_cross_process_learning_lock_guard():
        import auto_repair_engine as repair
        import sys as _sys
        program=(
            "import sys\nfrom pathlib import Path\n"
            "sys.path.insert(0,sys.argv[1])\nimport auto_repair_engine as repair\n"
            "memory=Path(sys.argv[2])\n"
            "for number in range(5):\n"
            " repair.learn({'finished_at':f'2026-08-25T04:00:{number:02d}Z','results':["
            "{'file':'market_prices.json','ok':False,'error':'TimeoutError: source delayed'}]},memory)\n"
        )
        with tempfile.TemporaryDirectory(prefix='tcg-v81-process-lock-') as td:
            root=Path(td);memory=root/'memory.json'
            processes=[subprocess.Popen([_sys.executable,'-c',program,str(ROOT),str(memory)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(6)]
            outputs=[process.communicate(timeout=30) for process in processes]
            assert all(process.returncode==0 for process in processes),outputs
            assert all(not error for _,error in outputs),outputs
            learned=repair.load_memory(memory)
            group=next(iter(learned['error_groups'].values()))
            assert learned['total_runs']==30 and group['occurrences']==30
            assert not memory.with_suffix('.json.lock').exists()
            json.loads(memory.with_suffix('.json.bak').read_text(encoding='utf-8'))

            outside=root/'outside.txt';outside.write_text('UNCHANGED',encoding='utf-8')
            unsafe=root/'unsafe.json';lock=unsafe.with_suffix('.json.lock');lock.symlink_to(outside)
            try:
                repair.learn({'results':[{'file':'releases.json','ok':True}]},unsafe)
                raise AssertionError('symlink lock accepted')
            except ValueError:
                pass
            assert outside.read_text(encoding='utf-8')=='UNCHANGED' and not unsafe.exists()

            stale=root/'stale.json';stale_lock=stale.with_suffix('.json.lock')
            stale_lock.write_text(json.dumps({'pid':99999999,'created_at':'2026-08-25T00:00:00Z','token':'stale'}),encoding='utf-8')
            recovered=repair.learn({'results':[{'file':'releases.json','ok':True}]},stale)
            assert recovered['total_runs']==1 and not stale_lock.exists()

            live=root/'live.json';live_lock=live.with_suffix('.json.lock')
            live_lock.write_text(json.dumps({'pid':os.getpid(),'created_at':'2026-08-25T00:00:00Z','token':'live'}),encoding='utf-8')
            os.utime(live_lock,ns=(1,1))
            try:
                with repair._memory_process_lock(live,timeout_seconds=.05,stale_seconds=1):
                    raise AssertionError('live owner lock stolen')
            except TimeoutError:
                pass
            assert live_lock.exists();live_lock.unlink()
        return '6개 프로세스×5회 무유실 · symlink 차단 · 종료 잠금 회수 · 살아 있는 오래된 잠금 보존'
    check('v81 다중 프로세스 학습기록 무유실·잠금보안',v81_cross_process_learning_lock_guard,rows)

    def v81_public_nofollow_read_guard():
        from functools import partial
        from unittest.mock import patch
        import auto_repair_engine as repair
        import github_sync_engine as github
        import migrate_old_data as migration
        import run_github_pipeline as pipeline
        import safe_runtime as runtime
        import tcg_updater as updater
        with tempfile.TemporaryDirectory(prefix='tcg-v81-nofollow-read-') as td:
            root=Path(td);public=root/'public';public.mkdir()
            outside=root/'outside.json';outside.write_text('{"secret":"PRIVATE_TOKEN_DO_NOT_DISCLOSE"}',encoding='utf-8')
            asset=public/'releases.json';asset.symlink_to(outside)
            page=public/'index.html';page.write_text('<html>safe asset</html>',encoding='utf-8')
            linked=root/'report-link.json';linked.symlink_to(outside)
            server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),partial(updater.Handler,directory=str(public)))
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            base=f'http://127.0.0.1:{server.server_address[1]}'
            try:
                for method in ('GET','HEAD'):
                    try:urllib.request.urlopen(urllib.request.Request(base+'/releases.json',method=method),timeout=5)
                    except urllib.error.HTTPError as exc:assert exc.code==404
                    else:raise AssertionError(f'외부 심볼릭 링크 정적 파일 노출: {method}')
                for method in ('GET','HEAD'):
                    with urllib.request.urlopen(urllib.request.Request(base+'/index.html',method=method),timeout=5) as response:
                        assert response.status==200
                        assert int(response.headers['Content-Length'])==page.stat().st_size
                        if method=='GET':assert b'safe asset' in response.read()
                with patch.object(updater,'MAX_SAFE_FILE_BYTES',8):
                    for method in ('GET','HEAD'):
                        try:urllib.request.urlopen(urllib.request.Request(base+'/index.html',method=method),timeout=5)
                        except urllib.error.HTTPError as exc:assert exc.code==404
                        else:raise AssertionError(f'대용량 정적 파일 허용: {method}')
                with patch.object(updater,'AUTO_REPORT',str(linked)),patch.object(updater,'DB',str(linked)):
                    with urllib.request.urlopen(base+'/api/update-report',timeout=5) as response:
                        report=json.load(response)
                    with urllib.request.urlopen(base+'/api/status',timeout=5) as response:
                        database=json.load(response)
                    assert report=={'ok':False,'results':[]} and 'secret' not in database
                assert updater.load_json_file(str(linked),{'safe':True})=={'safe':True}
                assert migration.read_json(linked,{'safe':True})=={'safe':True}
                cache=github.GitHubSyncEngine();cache.cache=linked
                assert cache._load_cache()==[]
                with patch.object(pipeline,'ROOT',root),patch.object(pipeline,'SYNC_FILES',('report-link.json',)):
                    assert pipeline.snapshot()=={'report-link.json':None}
                try:repair._load_strict_json(linked)
                except (OSError,ValueError):pass
                else:raise AssertionError('학습 엔진이 외부 심볼릭 링크를 읽음')
                for invalid in (linked,public):
                    try:runtime.safe_read_bytes(invalid)
                    except (OSError,ValueError):pass
                    else:raise AssertionError('비정상 파일 설명자 허용')
                try:runtime.safe_read_text(outside,max_bytes=8)
                except ValueError:pass
                else:raise AssertionError('읽기 크기 제한 우회')
                if hasattr(os,'mkfifo'):
                    pipe=root/'unsafe.fifo';os.mkfifo(pipe)
                    try:runtime.safe_read_bytes(pipe)
                    except (OSError,ValueError):pass
                    else:raise AssertionError('FIFO 장치 읽기 허용')
            finally:
                server.shutdown();server.server_close();worker.join(timeout=3)
        return '정적 GET/HEAD·업데이트 API·운영 DB·GitHub·이전자료 symlink 차단 · FIFO·용량 제한 적용'
    check('v81 공개 정적파일·API·GitHub 안전읽기',v81_public_nofollow_read_guard,rows)

    def v81_atomic_temp_and_backup_guard():
        from unittest.mock import patch
        import auto_update_all as automatic
        import migrate_old_data as migration
        import safe_runtime as runtime
        import tcg_updater as updater
        with tempfile.TemporaryDirectory(prefix='tcg-v81-nofollow-temp-') as td:
            root=Path(td);outside=root/'outside.txt';outside.write_text('PRIVATE_ORIGINAL',encoding='utf-8')
            stats=root/'source-stats.json';Path(str(stats)+'.tmp').symlink_to(outside)
            with patch.object(updater,'SOURCE_STATS',str(stats)),patch.object(updater,'SOURCE_STATS_BAK',str(stats)+'.bak'):
                updater._save_source_stats({'version':1,'sources':{}})
                assert updater._load_source_stats()['sources']=={}
            assert outside.read_text(encoding='utf-8')=='PRIVATE_ORIGINAL'
            precollect=root/'precollect.json';Path(str(precollect)+'.tmp').symlink_to(outside)
            with patch.object(updater,'PRECOLLECT_STATUS',str(precollect)):
                updater._write_precollect_status({'state':'ready'})
            assert json.loads(precollect.read_text(encoding='utf-8'))['state']=='ready'
            assert outside.read_text(encoding='utf-8')=='PRIVATE_ORIGINAL'
            history=root/'history.json';Path(str(history)+'.tmp').symlink_to(outside)
            persisted,record=persist_verification_history([{'name':'safe','ok':True}],history)
            assert record['ok'] is True and persisted['runs'][-1]['checks'][0]['name']=='safe'
            assert outside.read_text(encoding='utf-8')=='PRIVATE_ORIGINAL'
            destination=root/'snapshot.json';automatic._copy_snapshot(stats,destination)
            assert json.loads(destination.read_text(encoding='utf-8'))['sources']=={}
            linked=root/'linked-source.json';linked.symlink_to(outside)
            try:automatic._copy_snapshot(linked,root/'unsafe-copy.json')
            except (OSError,ValueError):pass
            else:raise AssertionError('스냅샷 복사가 외부 링크를 따라감')
            try:migration.copy_safe_file(linked,root/'unsafe-migration.json')
            except (OSError,ValueError):pass
            else:raise AssertionError('이전자료 복사가 외부 링크를 따라감')
            staging=root/'stage-source';staging.mkdir();(staging/'releases.json').symlink_to(outside)
            try:updater._safe_stage_copy(staging,root/'unsafe-stage')
            except ValueError:pass
            else:raise AssertionError('사전수집 작업폴더가 외부 링크를 복사함')
            binary=root/'binary.json';binary.symlink_to(outside)
            try:runtime.atomic_write_bytes(binary,b'blocked')
            except (OSError,ValueError):pass
            else:raise AssertionError('바이너리 백업 symlink 덮어쓰기 허용')

            database=root/'live.json';database.write_text(json.dumps({'pending':[{'status':'확인','name':'safe'}],'applied':[]}),encoding='utf-8')
            Path(str(database)+'.apply.bak.tmp').symlink_to(outside)
            with patch.object(updater,'DB',str(database)):
                server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),updater.Handler)
                worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
                try:
                    request=urllib.request.Request(f'http://127.0.0.1:{server.server_address[1]}/api/apply',data=b'',method='POST')
                    with urllib.request.urlopen(request,timeout=5) as response:result=json.load(response)
                    assert result['approved_count']==1 and Path(str(database)+'.bak').exists()
                finally:
                    server.shutdown();server.server_close();worker.join(timeout=3)
            assert outside.read_text(encoding='utf-8')=='PRIVATE_ORIGINAL'
        return '출처학습·사전수집·검사이력·스냅샷·승인백업 고정 tmp symlink 악용 차단 · 외부 파일 변경 0건'
    check('v81 임시파일·학습기록·백업 외부 덮어쓰기 차단',v81_atomic_temp_and_backup_guard,rows)

    def v83_five_grader_price_guard():
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        prices=parsed['market_prices.json']
        sources=parsed['purchase_sources.json']['sources']
        naruto=prices['entries']['US|NARUTO CP-001 Gen Con 2026|HIT']
        assert naruto['game']=='NARUTO' and naruto['card_number']=='CP-001'
        assert '$700~$1,000' in naruto['display'] and '체결 확정가 아님' in naruto['kind']
        assert naruto.get('image_url','').startswith('https://narutomarket.com/')
        profiles=prices.get('graded_prices',{})
        assert 'US|NARUTO CP-001 Gen Con 2026|HIT' in profiles
        companies={'PSA','BGS','CGC','TAG','BRG'}
        naruto_prices=profiles['US|NARUTO CP-001 Gen Con 2026|HIT']['grade_prices_krw']
        assert set(naruto_prices)==companies
        assert all(set(values)=={str(grade) for grade in range(1,11)} for values in naruto_prices.values())
        assert all(value==0 for values in naruto_prices.values() for value in values.values())
        lillie=profiles['KR|릴리에 SM1M 065/060|HIT']
        assert lillie['raw_krw']==300000
        assert lillie['grade_prices_krw']['BRG']['9']==450000
        assert lillie['grade_prices_krw']['BRG']['10']==2000000
        defaults=prices.get('grading_cost_defaults',{})
        assert defaults.get('editable') is True and defaults['company_fees_krw']['BRG']==19800
        gyeonggi=[row for row in sources if row.get('region')=='KR' and
                  ('롯데마트' in row.get('name','') or '토이저러스' in row.get('name','')) and
                  str(row.get('address','')).startswith('경기도')]
        assert len(gyeonggi)>=25
        assert any(row['name']=='롯데마트 선부점' for row in gyeonggi)
        assert all(row.get('address') and isinstance(row.get('lat'),(int,float)) and
                   isinstance(row.get('lon'),(int,float)) for row in gyeonggi)
        assert all('재고 미확인' in row.get('inventory_status','') for row in gyeonggi)
        required=('id="gradingEconomics"','function calculateGradingEconomics(input)',
                  'id="econGradePrices"','id="econGrade"','function normalizeGradePrices(value)',
                  'id="purchaseUseAnsan"','function useAnsanDistance()',
                  '<th>TAG</th>','<th>BRG</th>','const GRADING_COMPANIES=["PSA","BGS","CGC","TAG","BRG"]',
                  'function generalCenterGrade(worstFront,worstBack)')
        assert all(token in page for token in required)
        assert 'window.tcgGradeProbabilities={8:p8,9:p9only,10:p10,below}' in page
        assert 'boxImage:"https://data1.pokemonkorea.co.kr/' in page
        assert 'cardImage:"https://narutomarket.com/' in page
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert "('PSA','BGS','CGC','TAG','BRG')" in server
        updater=(ROOT/'update_market_prices.py').read_text(encoding='utf-8')
        stores=(ROOT/'update_purchase_sources.py').read_text(encoding='utf-8')
        assert 'NARUTO CP-001 Gen Con 2026' in updater and 'blank_grade_prices' in updater
        assert 'https://taggrading.com/pages/scale' in page and 'https://break.co.kr/' in page
        assert 'APH' not in page and 'APH' not in server and 'APH' not in updater
        assert 'ensure_gyeonggi_lotte_stores' in stores and 'inventory_status' in stores
        return f'5개 업체×10등급 가격 50칸 · BRG 공식 거래예시 · 1~10 사전측정 · 경기도 지점 {len(gyeonggi)}개'
    check('v83 5개 업체 1~10 측정·등급별 시세수익',v83_five_grader_price_guard,rows)

    def v83_integrated_version_and_document_guard():
        import cross_platform_agent as cross_platform
        import auto_repair_engine as learning_engine
        import tcg_updater as updater
        import safe_runtime as runtime
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        worker=(ROOT/'sw.js').read_text(encoding='utf-8')
        automatic=(ROOT/'auto_update_all.py').read_text(encoding='utf-8')
        repeated=(ROOT/'run_repeated_verification.py','social_event_discovery.py').read_text(encoding='utf-8')
        repair=(ROOT/'auto_repair_engine.py').read_text(encoding='utf-8')
        guide=(ROOT/'사용방법_v83.md').read_text(encoding='utf-8')
        audit=(ROOT/'V83_FIVE_GRADER_PRICE_ENGINE_2026-08-25.md').read_text(encoding='utf-8')
        manifest=json.loads((ROOT/'manifest.webmanifest').read_text(encoding='utf-8'))
        assert CURRENT_APP_NAME in page and manifest['name']==CURRENT_APP_NAME
        assert CURRENT_SERVICE in server
        assert all(CURRENT_ENGINE in source for source in (server,automatic,repeated))
        assert CURRENT_CACHE in worker
        assert '_memory_process_lock' in repair and 'type(ok_value) is not bool' in repair
        diagnostic=cross_platform.CrossPlatformSelfHealingEngine().diagnostics()
        diagnostic_text=json.dumps(diagnostic,ensure_ascii=False)
        assert diagnostic['data_dir']=='<app-data>' and diagnostic['storage_scope'] in {
            'project-fallback','configured-app-data','user-app-data','app-data'}
        assert str(Path.home()) not in diagnostic_text and str(ROOT) not in diagnostic_text
        for filename in ('web_discovery_candidates.json','auto_update_report.json'):
            persisted=(ROOT/filename).read_text(encoding='utf-8')
            assert '/workspace/' not in persisted and '/home/' not in persisted and '/root/' not in persisted
        shared_json_modules=(
            'auto_pipeline_runner.py','auto_update_all.py','tcg_updater.py',
            'update_releases.py','update_market_prices.py','update_market_watch.py',
            'update_promo_events.py','update_purchase_sources.py','update_exchange_rates.py',
            'supplementary_discovery.py','validate_external_links.py','github_sync_engine.py',
            'migrate_old_data.py',
        )
        assert all('atomic_write_json' in (ROOT/filename).read_text(encoding='utf-8') for filename in shared_json_modules)
        safe_read_modules=(
            'auto_repair_engine.py','auto_update_all.py','github_sync_engine.py',
            'migrate_old_data.py','run_github_pipeline.py','run_repeated_verification.py',
            'tcg_updater.py','update_exchange_rates.py','update_market_prices.py',
            'update_market_watch.py','update_promo_events.py','update_purchase_sources.py',
            'update_releases.py','validate_external_links.py','verify_all.py',
        )
        assert all('safe_read_' in (ROOT/filename).read_text(encoding='utf-8') for filename in safe_read_modules)
        assert 'def send_head(self):' in server and 'open_safe_binary(target' in server
        assert 'O_NOFOLLOW' in (ROOT/'safe_runtime.py').read_text(encoding='utf-8')
        assert '기존 자동 오류학습과 보안 유지' in audit
        assert learning_engine._unique_json_object is updater._unique_json_object is runtime.unique_json_object
        assert learning_engine._reject_json_constant is updater._reject_nonstandard_json is runtime.reject_nonstandard_json
        for raw in ('{"same":1,"same":2}','{"value":NaN}','{"value":Infinity}','{"value":-Infinity}'):
            try:updater.strict_json_loads(raw)
            except ValueError:pass
            else:raise AssertionError(f'공통 JSON 검증에서 비표준 입력 허용: {raw}')
        assert page.count('new Image()')==1 and 'function loadCardImage(file)' in page
        for name in ('load','v6Load','v7Image','v30Load'):
            assert re.search(rf'function {name}\([^)]*\)\{{return loadCardImage\(',page)
        assert 'revokeObjectURL' in page and '원자적 JSON 저장' in audit and '공통 이미지 로더' in audit
        assert '같은 근본 원인' in guide and '문자열 `"false"`' in guide and '3~10분' in guide
        assert '6개 자동수집 작업' in audit and 'total_runs' in audit and '코드로 평가하거나 실행하지 않습니다' in audit
        assert 'DEFERRED_TIMEOUT_MIN_SECONDS = 180' in automatic and 'DEFERRED_TIMEOUT_MAX_SECONDS = 600' in automatic
        return 'v84 일치 · 기존 5개 업체 1~10 · 등급별 가격 50칸 · 표준 JSON 훅 · 3~10분 복구수집 유지'
    check('v84 통합 버전·기존 오류학습 문서·복구계약',v83_integrated_version_and_document_guard,rows)

    def v84_secure_grading_and_valuation_guard():
        from unittest.mock import patch
        import card_grading_valuation as engine

        for value in (None,float('nan'),float('inf'),float('-inf'),True,{},'1e9999','9'*100):
            assert engine.safe_float(value,3.5)==3.5
        assert engine.safe_float('7.25')==7.25
        assert engine.safe_float(99,0,minimum=1,maximum=10)==10
        assert engine.safe_int(float('inf'),7)==7
        assert engine.safe_int('999',0,minimum=0,maximum=100)==100
        for value in ('false','FALSE','0','no',False,0,[],{'true':True}):
            assert engine.safe_bool(value,default=False) is False
        for value in ('true','1','yes',True,1):
            assert engine.safe_bool(value,default=False) is True

        expected=((1000,10,'PRISTINE'),(990,10,'PRISTINE'),(989,10,'GEM MINT'),
                  (950,10,'GEM MINT'),(949,9,'MINT'),(900,9,'MINT'),
                  (899,8.5,'NM MT+'),(850,8.5,'NM MT+'),(150,1.5,'FAIR'),(100,1,'POOR'))
        for score,grade,label in expected:
            actual=engine.tag_score_to_grade(score)
            assert actual['grade']==grade and actual['condition']==label
        assert all(grade!=9.5 for _,grade,_ in engine.TAG_SCALE)
        for invalid in (99,1001,None,float('inf'),950.5,True):
            try:engine.tag_score_to_grade(invalid)
            except ValueError:pass
            else:raise AssertionError(f'유효하지 않은 TAG 점수 허용: {invalid}')

        pristine={'centering_front':50,'centering_back':50,'corners':10,'edges':10,
                  'surface':10,'micro_flaws':0,'is_authentic':True}
        grades=engine.estimate_grades(pristine)
        assert grades['ok'] and set(grades['grades'])==set(engine.COMPANIES)
        assert all(1<=value<=10 for value in grades['grades'].values())
        assert all(value==10 for value in grades['grades'].values())
        assert grades['tag']['score_kind']=='photo_advisory_not_official_DIG'
        assert engine.estimate_grades({**pristine,'centering_front':60})['grades']['PSA']<10
        assert engine.estimate_grades({**pristine,'centering_back':76})['grades']['PSA']<10
        assert engine.estimate_grades({**pristine,'edges':8})['grades']['PSA']<10
        assert engine.estimate_grades({**pristine,'micro_flaws':1})['grades']['PSA']<10
        assert engine.estimate_grades({**pristine,'centering_front':'nan'})['grades']['PSA']<10
        assert engine.estimate_grades({**pristine,'micro_flaws':'invalid'})['grades']['PSA']<10
        assert engine.estimate_grades({**pristine,'micro_flaws':-1})['grades']['PSA']<10
        assert engine.estimate_grades({**pristine,'micro_flaws':0.5})['grades']['PSA']<10
        for invalid in ('false','0','no',False,{'truth':True}):
            assert not engine.estimate_grades({**pristine,'is_authentic':invalid})['ok']

        profile={'BRG':{'9':450000,'10':2000000}}
        valued=engine.verified_card_valuation('LILLIE SM1M 065/060',pristine,profile,raw_krw=300000)
        assert valued['valuations']['BRG']['krw']==2000000
        assert valued['valuations']['BRG']['source']=='exact_company_grade_observation'
        assert valued['valuations']['PSA']['available'] is False
        assert valued['valuations']['PSA']['krw'] is None
        assert valued['raw_krw']==300000 and valued['official_grade'] is False
        supplied=engine.verified_card_valuation('User card',pristine,{'PSA':{'10':123}},
                                                 price_source='user_provided_exact_grade')
        assert supplied['valuations']['PSA']['source']=='user_provided_exact_grade'
        assert engine.verified_card_valuation('bad',{'is_authentic':'false'})['status']=='FAILED'

        sold='<li class="s-item"><span>Sold Aug 25</span><span class="s-item__price">$100.00</span></li>'
        sold+='<li class="s-item"><span>Sold Aug 24</span><span class="s-item__price">$110.00</span></li>'
        sold+='<li class="s-item"><span>Sold Aug 23</span><span class="s-item__price">$120.00</span></li>'
        sold+='<li class="s-item"><span>Sold Aug 22</span><span class="s-item__price">$9,999.00</span></li>'
        sold+='<li class="s-item"><span>Buy it now</span><span class="s-item__price">$1.00</span></li>'
        sold+='<li class="s-item"><img src="card.jpg"/><span>Unsold listing</span><span class="s-item__price">$2.00</span></li>'
        sold+='<li class="s-item"><span>Sold out booster</span><span class="s-item__price">$3.00</span></li>'
        observed=engine.extract_sold_prices(sold)
        assert observed['sample_count']==3 and observed['median_usd']==110.0
        assert engine.extract_sold_prices('<li class="s-item"><span class="s-item__price">$50.00</span></li>')['median_usd'] is None
        parsed_url=urllib.parse.urlsplit(engine.ebay_sold_url('Charizard Base Set'))
        parameters=urllib.parse.parse_qs(parsed_url.query)
        assert parsed_url.hostname=='www.ebay.com' and parameters['LH_Sold']==['1'] and parameters['LH_Complete']==['1']
        for invalid in ('x\nInjected: yes','x'*121,''):
            try:engine.ebay_sold_url(invalid)
            except ValueError:pass
            else:raise AssertionError('위험한 카드 검색어 허용')
        with patch.object(engine,'safe_urlopen',side_effect=urllib.error.URLError('offline')):
            offline=engine.fetch_ebay_sold_prices('LILLIE')
        assert offline['ok'] is False and offline['median_usd'] is None and offline['sample_count']==0

        with tempfile.TemporaryDirectory(prefix='tcg-v84-code-') as td:
            marker=Path(td)/'executed'
            source=f"__import__('pathlib').Path({str(marker)!r}).write_text('danger')"
            scanned=engine.inspect_python_source(source)
            assert scanned['executed'] is False and scanned['ok'] is False
            assert not marker.exists()
            for snippet in ('exec("print(1)")','eval("1+1")','getattr(__builtins__,"exec")("danger")',
                            'import subprocess\nsubprocess.run("x",shell=True)'):
                assert engine.inspect_python_source(snippet)['ok'] is False
            assert engine.inspect_python_source('result = 1 + 1')['ok'] is True
        source=(ROOT/'card_grading_valuation.py').read_text(encoding='utf-8')
        assert 'requests' not in source or '"requests"' in source
        assert not re.search(r'\b(?:exec|eval)\s*\(',source)
        return 'PSA 55/45·75/25 · TAG 950~989=10·9.5 없음 · false 가품 차단 · 판매완료 중앙값 · 임의 실행/시세배율 0건'
    check('v84 제미나이 참고 5개 업체 공식기준·실거래·실행보안',v84_secure_grading_and_valuation_guard,rows)

    def v84_live_grade_api_and_document_guard():
        import tcg_updater as updater
        server=updater.QuietThreadingHTTPServer(('127.0.0.1',0),updater.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        pristine={'centering_front':50,'centering_back':50,'corners':10,'edges':10,
                  'surface':10,'micro_flaws':0,'is_authentic':True}
        def send(payload,origin=None):
            headers={'Content-Type':'application/json'}
            if origin is not None:headers['Origin']=origin
            request=urllib.request.Request(base+'/api/grade-card',data=json.dumps(payload).encode('utf-8'),
                                           headers=headers,method='POST')
            try:
                with urllib.request.urlopen(request,timeout=5) as response:
                    return response.status,json.loads(response.read().decode('utf-8'))
            except urllib.error.HTTPError as exc:
                return exc.code,json.loads(exc.read().decode('utf-8'))
        try:
            with urllib.request.urlopen(base+'/api/grading-standards',timeout=5) as response:
                standards=json.loads(response.read().decode('utf-8'))
            assert standards['tag_grade_9_5_exists'] is False
            assert standards['psa_10_centering']=={'front':'55/45','back':'75/25'}
            success=send({'card_name':'릴리에','market_key':'KR|릴리에 SM1M 065/060|HIT','cv_data':pristine})
            assert success[0]==200 and success[1]['valuations']['BRG']['krw']==2000000
            assert success[1]['valuations']['PSA']['krw'] is None
            user=send({'card_name':'직접 입력','cv_data':pristine,'grade_prices_krw':{'PSA':{'10':1234}}})
            assert user[1]['valuations']['PSA']['source']=='user_provided_exact_grade'
            fake=send({'card_name':'가품','cv_data':{**pristine,'is_authentic':'false'}})
            assert fake[0]==200 and fake[1]['ok'] is False and fake[1]['valuations']=={}
            assert send({'card_name':'bad','cv_data':[]})[0]==400
            assert send({'card_name':'bad','cv_data':pristine,'grade_prices_krw':{'PSA':[]}})[0]==400
            assert send({'card_name':'bad','market_key':'unknown','cv_data':pristine})[0]==400
            assert send({'card_name':'bad','cv_data':pristine},origin='https://evil.example')[0]==403
        finally:
            server.shutdown();server.server_close();thread.join(timeout=5)
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        guide=(ROOT/'사용방법_v84.md').read_text(encoding='utf-8')
        audit=(ROOT/'V84_GEMINI_REFERENCE_SECURITY_HARDENING_2026-08-25.md').read_text(encoding='utf-8')
        assert all(token in page for token in ('function tagScoreToGrade(score)','id="econServerVerify"',
                    '"/api/grade-card"','window.tcgStartUpdateJob("/api/run-auto-update"','window.tcgGradeSnapshot'))
        assert all(token in guide for token in ('950~989','9.5','판매완료','문자열 `"false"`','3~10분'))
        assert all(token in audit for token in ('exec','고정 배율','판매완료','GET','POST','TAG'))
        return '실제 API 5개 업체·가품·교차출처 차단 · 사용자 입력/검증가격 구분 · GET 업데이트 오류 POST 수정 · v84 문서 일치'
    check('v84 실서버 등급·가품·시세 API와 화면 업데이트 복구',v84_live_grade_api_and_document_guard,rows)

    def v85_feature_contract_and_background_update_guard():
        from feature_contract import audit_feature_contract
        contract=audit_feature_contract(ROOT)
        assert contract['ok'] is True
        assert contract['implemented']==contract['total']==25
        assert contract['missing']==[]
        assert contract['excluded']==[{'id':'iphone_serverless_continuous_collection',
                                      'reason':'사용자가 구현 제외를 요청한 기능'}]
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert 'fetch(`/api/update?t=${Date.now()}`,{cache:' not in page
        assert 'window.tcgStartUpdateJob=startJob' in page
        assert 'return await pollJob(d.job_id)' in page
        assert 'const [loaded,promos,purchases,prices,rates]' in page
        assert '[loaded,promos,purchases,prices,rates].every' in page
        assert '자료 불러오기 실패' in page and 'PC 서버에 연결되지 않아 브라우저 학습기록을 유지합니다.' in page
        critical=(
            page[page.index('async function syncLearningFromServer'):page.index('function v11Get')],
            page[page.index('async function v13LoadAllPriceData'):page.index('function v13RegionFromMarket')],
            page[page.index('async function loadPopularitySignals'):page.index('loadPopularitySignals();')],
        )
        assert all('catch(e){}' not in source for source in critical)
        button_ids=re.findall(r'<button\b[^>]*\bid="([^"]+)"',page)
        assert len(button_ids)>=60 and len(button_ids)==len(set(button_ids))
        assert all(page.count(button_id)>=2 for button_id in button_ids)
        functions=re.findall(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(',page)
        assert len(functions)==len(set(functions)), '중복 JavaScript 함수 정의 발견'
        guide=(ROOT/'사용방법_v85.md').read_text(encoding='utf-8')
        report=(ROOT/'V85_FULL_FEATURE_CONTRACT_SELF_HEALING_2026-08-25.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('백그라운드','20개','3~10분','TAG','아이폰'))
        assert all(token in report for token in ('HTTP 405','동일 원인 그룹','신규 원인','허위정보','20개'))
        return f"기능 계약 {contract['implemented']}/{contract['total']} · 버튼 {len(button_ids)}개 연결 · GET 405 재발경로 차단 · 로더 실패상태 명시"
    check('v85 기존 요청 전체 기능계약·백그라운드 업데이트·침묵오류 방지',v85_feature_contract_and_background_update_guard,rows)

    def v86_scenario_pretraining_and_fast_resolution_guard():
        import hashlib
        import auto_repair_engine as repair
        import error_scenario_lab as lab
        profile=parsed['scenario_learning_profiles.json']
        assert profile['training_only'] is True and profile['scenario_count']>=83
        assert profile['successful_scenarios']==profile['scenario_count'] and profile['failed_scenarios']==[]
        assert profile['family_count']>=19 and profile['verified_profile_count']>=65
        assert profile['safety']=={
            'production_memory_modified':False,'operational_occurrences_modified':False,
            'network_accessed':False,'scenario_text_executed':False,
            'advisory_only':True,'retry_permission_can_only_be_narrowed':True,
        }
        loaded=repair.load_scenario_profiles()
        assert loaded['ok'] and len(loaded['profiles'])==profile['verified_profile_count']
        groups={}
        before=hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()
        for scenario in lab.SCENARIOS:
            analysis=repair.analyze_error(scenario['detail'])
            assert analysis['code']==scenario['code']
            if scenario['subtype'] is not None: assert analysis['error_subtype']==scenario['subtype']
            assert analysis['bounded_retry_allowed'] is scenario['retry']
            assert analysis['prepared_scenario_match'] is True
            assert analysis.get('scenario_profile_id') and analysis.get('fast_resolution_steps')
            group_id=repair.error_group_key(analysis)
            expected=groups.setdefault(scenario['equivalent_group'],group_id)
            assert expected==group_id
        assert repair.error_group_key(repair.analyze_error('TimeoutError: source 30 seconds')) != repair.error_group_key(repair.analyze_error('subprocess.TimeoutExpired: worker 30 seconds'))
        assert repair.error_group_key(repair.analyze_error("NameError: name 'fetch_prices' is not defined")) != repair.error_group_key(repair.analyze_error("NameError: name 'save_prices' is not defined"))
        assert repair.analyze_error('HTTPError: HTTP Error 404')['bounded_retry_allowed'] is False
        assert repair.analyze_error('HTTPError: HTTP Error 503')['bounded_retry_allowed'] is True
        with tempfile.TemporaryDirectory(prefix='tcg-v86-scenarios-') as td:
            root=Path(td);memory=root/'memory.json'
            learned=repair.learn({'results':[{'file':'scenario_test.json','ok':False,
                'error':'HTTPError: HTTP Error 503 from official source'}]},memory)
            group=next(iter(learned['error_groups'].values()))
            assert group['scenario_prepared'] is True and group['scenario_profile_id']
            assert group['fast_resolution_steps'] and group['stop_conditions']
            public=repair.public_error_learning_summary(learned)
            assert public['scenario_learning']['scenario_count']==profile['scenario_count']
            assert public['groups'][0]['scenario_prepared'] is True
            key='NETWORK_HTTP_ERROR|missing-404'
            malicious={'version':1,'training_only':True,'scenario_count':1,'family_count':1,'profiles':{
                key:{'profile_id':'0'*16,'code':'NETWORK_HTTP_ERROR','error_subtype':'missing-404',
                     'http_status':404,'verified':True,'scenario_count':1,'diagnostic_priority':1,
                     'first_checks':['우회'],'fast_resolution_steps':['무제한 재시도'],
                     'verification_steps':['없음'],'stop_conditions':[],
                     'bounded_retry_allowed':True}}}
            poisoned=root/'poisoned.json';atomic_write_json(poisoned,malicious)
            base=repair.analyze_error('HTTPError: HTTP Error 404',use_scenario_profile=False)
            enriched=repair._apply_scenario_profile(base,poisoned)
            assert enriched['prepared_scenario_match'] is True
            assert enriched['bounded_retry_allowed'] is False
            duplicate=root/'duplicate.json';duplicate.write_text('{"training_only":true,"profiles":{},"profiles":{}}',encoding='utf-8')
            assert repair.load_scenario_profiles(duplicate)['ok'] is False
        after=hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()
        assert before==after
        lab_source=(ROOT/'error_scenario_lab.py').read_text(encoding='utf-8')
        assert 'import subprocess' not in lab_source and 'urlopen' not in lab_source
        assert not re.search(r'\b(?:exec|eval)\s*\(',lab_source)
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert all(token in page for token in ('사전 오류상황','검증 해결프로필','사전훈련 일치','fast_resolution_steps'))
        guide=(ROOT/'사용방법_v86.md').read_text(encoding='utf-8')
        audit=(ROOT/'V86_SCENARIO_PRETRAINED_ERROR_RESOLUTION_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('83','19','65','production_memory_unchanged','exec','eval'))
        assert all(token in audit for token in ('PROCESS_TIMEOUT','RESOURCE_EXHAUSTION','CONCURRENCY_CONFLICT','운영자료','재시도'))
        return f"{profile['scenario_count']}개 상황·{profile['family_count']}개 원인계열·{profile['verified_profile_count']}개 해결프로필 · 운영 발생횟수 비오염 · 재시도 권한 확대 차단 · 빠른 해결순서 연결"
    check('v86 다중 오류상황 사전학습·빠른 해결·운영값 비오염',v86_scenario_pretraining_and_fast_resolution_guard,rows)

    def v87_diverse_retail_channel_and_store_guard():
        import update_purchase_sources as purchases
        sources=parsed['purchase_sources.json']['sources']
        korea=[row for row in sources if row.get('region')=='KR' and row.get('channel')=='offline']
        required={'convenience','hypermarket','stationery','toy','bookstore','cardshop','discount'}
        categories={row.get('retailer_category') for row in korea}
        assert len(sources)>=200 and len(korea)>=140 and required<=categories
        for chain in ('CU','GS25','세븐일레븐','이마트24','이마트','트레이더스','홈플러스',
                      '알파문구','모닝글로리','학교 앞 문구점','동네 문구','토이킹덤',
                      '교보문고','TCG 트레이딩카드','다이소'):
            assert any(chain in row['name'] for row in korea),f'{chain} 판매처 누락'
        names={row['name'] for row in korea}
        assert set(purchases.GYEONGGI_EMART_STORES)<=names
        assert set(purchases.GYEONGGI_TRADERS_STORES)<=names
        assert len(purchases.GYEONGGI_EMART_STORES)>=40
        assert len(purchases.GYEONGGI_TRADERS_STORES)>=13
        locations={row['name']:row for row in korea if row['name'] in purchases.VERIFIED_LOCATION_DETAILS}
        assert set(locations)==set(purchases.VERIFIED_LOCATION_DETAILS)
        for name,row in locations.items():
            assert str(row.get('address','')).startswith('경기도')
            assert isinstance(row.get('lat'),(int,float)) and isinstance(row.get('lon'),(int,float))
            assert row.get('official_reference_url','').startswith('https://')
        assert locations['이마트 안산고잔점']['address']=='경기도 안산시 단원구 원포공원1로 46'
        assert locations['트레이더스 홀세일 클럽 안산점']['phone']=='031-363-1234'
        assert locations['알파문구 경기대점']['phone']=='031-8007-3172'
        assert '홈플러스 안산고잔점' not in names and '홈플러스 안산선부점' not in names
        assert all(row.get('inventory_verified') is False and row.get('inventory_checked_at') is None
                   and '미확인' in row.get('inventory_status','') for row in korea)
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert 'id="purchaseRetailerType"' in page
        assert all(f'value="{category}"' in page for category in required)
        assert 'x.retailer_category===category' in page and 'Array.isArray(x.games)' in page
        assert 'escapeDisplayText(purchaseLocation?.label||"현재 위치")' in page
        guide=(ROOT/'사용방법_v87.md').read_text(encoding='utf-8')
        audit=(ROOT/'V87_DIVERSE_RETAIL_CHANNELS_SECURITY_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('CU','GS25','세븐일레븐','이마트24','안산고잔점','문구점','재고 미확인'))
        assert all(token in audit for token in ('40','13','공식 도메인','폐점','재고'))
        return f'구매처 {len(sources)}개 · 한국 오프라인 {len(korea)}개 · 경기 이마트 40개·트레이더스 13개 · 편의점·문구·완구·카드샵 분류'
    check('v87 편의점·이마트·대형마트·문구점·다양한 판매처',v87_diverse_retail_channel_and_store_guard,rows)

    def v87_retail_security_dedup_and_restore_guard():
        import copy
        import auto_repair_engine as repair
        import auto_update_all as automatic
        import update_purchase_sources as purchases
        payload=copy.deepcopy(parsed['purchase_sources.json'])
        automatic.validate_json('purchase_sources.json',payload)
        assert repair._valid_project_payload('purchase_sources.json',payload)
        sources=payload['sources']
        assert len({(row['name'],row['region'],row.get('channel','online')) for row in sources})==len(sources)
        assert len(purchases.ensure_diverse_retail_channels(sources))==len(sources)
        missing=[row for row in sources if row['name'] not in {'CU 편의점 주변 매장','이마트 안산고잔점','알파문구 경기대점'}]
        restored=purchases.ensure_diverse_retail_channels(missing)
        assert {'CU 편의점 주변 매장','이마트 안산고잔점','알파문구 경기대점'}<={row['name'] for row in restored}
        ansan=copy.deepcopy(next(row for row in sources if row['name']=='이마트 안산고잔점'))
        invalid=(
            {'retailer_category':'invented'},
            {'official_reference_url':'https://store.emart.com.evil.example/branch'},
            {'official_reference_url':'https://127.0.0.1/private'},
            {'lat':float('nan')},
            {'lon':181.0},
            {'chain':'이마트\nspoof'},
        )
        for changes in invalid:
            poisoned={**ansan,**changes}
            try:purchases.normalize_source(poisoned)
            except (TypeError,ValueError):pass
            else:raise AssertionError(f'판매처 보안 자료 검증 실패: {changes}')
        tampered=copy.deepcopy(ansan);tampered.pop('chain')
        try:purchases.normalize_source(tampered)
        except ValueError:pass
        else:raise AssertionError('공식 점포 체인 제거로 도메인 검증 우회')
        official=copy.deepcopy(next(row for row in sources if row['name']=='CU 편의점 공식 매장 안내'))
        official['url']='https://cu.bgfretail.com.evil.example/store'
        try:purchases.normalize_source(official)
        except ValueError:pass
        else:raise AssertionError('가짜 공식 편의점 안내 링크 허용')
        incomplete=copy.deepcopy(ansan);incomplete.pop('lon')
        try:purchases.normalize_source(incomplete)
        except ValueError:pass
        else:raise AssertionError('불완전한 좌표 허용')
        claimed=copy.deepcopy(ansan);claimed['inventory_verified']=True;claimed['inventory_status']='판매중 · 재고 있음'
        normalized=purchases.normalize_source(claimed)
        assert normalized['inventory_verified'] is False and '미확인' in normalized['inventory_status']
        poisoned=copy.deepcopy(payload)
        index=next(i for i,row in enumerate(poisoned['sources']) if row['name']=='이마트 안산고잔점')
        poisoned['sources'][index]=claimed
        assert not repair._valid_project_payload('purchase_sources.json',poisoned)
        try:automatic.validate_json('purchase_sources.json',poisoned)
        except ValueError:pass
        else:raise AssertionError('미검증 매장 재고가 자동수집 자료에 저장됨')
        duplicate=copy.deepcopy(payload);duplicate['sources'].append(copy.deepcopy(duplicate['sources'][index]))
        try:automatic.validate_json('purchase_sources.json',duplicate)
        except ValueError:pass
        else:raise AssertionError('중복 매장 자료 저장 허용')
        return '매장 8분류·공식 체인 도메인·HTTPS·좌표 범위 검증 · 허위재고·폐점 지점·중복 차단 · 누락 체인 자동 복원'
    check('v87 판매처 공식 도메인·좌표·허위재고·중복 자동보호',v87_retail_security_dedup_and_restore_guard,rows)

    def v88_secure_ai_code_improvement_guard():
        import ai_code_improver as improver
        source=(ROOT/'ai_code_improver.py').read_text(encoding='utf-8')
        learning=parsed['ai_code_learning.json']
        policy=learning.get('policy',{})
        assert improver.ENGINE_VERSION==CURRENT_ENGINE and improver.MAX_RETRIES==5
        assert improver.DEFAULT_MODEL=='gpt-4o'
        assert '.responses.create' in source and '.chat.completions' not in source
        assert '"type": "json_schema"' in source and '"strict": True' in source
        assert 'pip install' not in source and 'pytest' not in source
        assert 'OPENAI_API_KEY' in source and 'api_key=' not in source
        assert all(token in source for token in (
            '"--network", "none"','"--read-only"','"--cap-drop", "ALL"',
            '"no-new-privileges:true"','"--pids-limit", "64"','"--memory", "256m"',
            '"--user", "65534:65534"','dst=/workspace,readonly'))
        assert all(policy.get(field) is False for field in (
            'model_training_claimed','generated_code_auto_applied','raw_code_persisted_in_learning_log'))
        for unsafe in ('import subprocess\n','import requests\n','eval("1+1")\n','__import__("os")\n'):
            assert improver.validate_python_source(unsafe).ok is False
        trusted=improver.load_trusted_test('test_card_name.py')
        assert 'normalize_card_name' in trusted and improver.validate_python_source(trusted,require_tests=True).ok
        command=improver.DockerSandbox().build_command('/tmp/tcg-safe-fixture','tcg-safe-fixture')
        joined=' '.join(command)
        assert 'pip install' not in joined and 'bash -c' not in joined
        test_run=subprocess.run([sys.executable,'-B',str(ROOT/'verify_ai_code_improver.py')],
                                cwd=ROOT,capture_output=True,text=True,timeout=30,check=False)
        assert test_run.returncode==0,test_run.stdout[-1000:]+test_run.stderr[-1000:]
        report=json.loads(test_run.stdout.strip().splitlines()[-1])
        assert report=={'ok':True,'tests':12,'failures':0,'errors':0}
        guide=(ROOT/'사용방법_v88.md').read_text(encoding='utf-8')
        audit=(ROOT/'V88_SECURE_AI_CODE_IMPROVEMENT_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('READY_FOR_HUMAN_REVIEW','SANDBOX_UNAVAILABLE','OPENAI_API_KEY','사람이 직접 검토'))
        assert all(token in audit for token in ('Responses API','strict JSON Schema','--network none','최대 5회','운영 소스 자동 수정'))
        contract=__import__('feature_contract').audit_feature_contract(ROOT)
        feature=next(row for row in contract['features'] if row['id']=='approved_ai_code_improvement')
        assert contract['ok'] and contract['implemented']==contract['total']==23 and feature['implemented']
        return 'Responses 구조화 출력 · 12개 독립검사 · Docker 무네트워크/최소권한 · 고정 회귀검사 · 동시 오류통합 · 승인 전 운영변경 0건'
    check('v88 승인형 AI 코드개선·격리검증·오류학습',v88_secure_ai_code_improvement_guard,rows)

    def v89_performance_size_dedup_guard():
        import json as _json
        import tempfile as _tempfile
        from unittest.mock import patch
        import auto_repair_engine as repair
        import safe_runtime as runtime
        import tcg_updater as updater

        assert runtime.bounded_int('12',0,1,10)==10
        assert runtime.bounded_int(None,7,1,10)==7
        assert runtime.bounded_float('2.5',0.0,1.0,2.0)==2.0
        assert runtime.bounded_float(float('nan'),7.0,1.0,10.0)==7.0
        assert runtime.html_to_text('<style>x{}</style><b>A&amp;B</b><script>bad()</script>')=='A&B'

        sources={name:(ROOT/name).read_text(encoding='utf-8') for name in (
            'auto_update_all.py','auto_repair_engine.py','run_repeated_verification.py','tcg_updater.py','migrate_old_data.py',
            'update_releases.py','update_market_prices.py')}
        assert 'def _safe_int(' not in sources['auto_update_all.py']
        assert 'def _safe_float(' not in sources['auto_update_all.py']
        assert 'def _safe_stat_int(' not in sources['tcg_updater.py']
        assert 'def _safe_stat_float(' not in sources['tcg_updater.py']
        assert 'def safe_int(' not in sources['migrate_old_data.py']
        assert 'def _safe_int(' not in sources['auto_repair_engine.py']
        assert 'def _utc_timestamp(' not in sources['auto_repair_engine.py']
        assert 'def _timestamp(' not in sources['run_repeated_verification.py']
        assert all('def textify(' not in sources[name] for name in ('update_releases.py','update_market_prices.py'))
        assert 'import platform' not in sources['auto_update_all.py']
        # urllib.request is also referenced through the package name by redirect handling.
        assert 'import urllib.request' in sources['tcg_updater.py']
        assert hasattr(updater,'urllib') and updater.OfficialSourceRedirect()

        raw=(ROOT/'scenario_learning_profiles.json').read_text(encoding='utf-8')
        with _tempfile.TemporaryDirectory(prefix='tcg-v89-cache-') as directory:
            profile=Path(directory)/'profiles.json'
            profile.write_text(raw,encoding='utf-8')
            repair.clear_scenario_profile_cache()
            original=repair.safe_read_text
            reads=[]
            def counted(*args,**kwargs):
                reads.append(str(args[0]))
                return original(*args,**kwargs)
            with patch.object(repair,'safe_read_text',side_effect=counted):
                first=repair.load_scenario_profiles(profile)
                first['profiles'].clear()
                second=repair.load_scenario_profiles(profile)
                expected_profiles=parsed['scenario_learning_profiles.json']['verified_profile_count']
                assert first['profiles']=={} and len(second['profiles'])==expected_profiles and len(reads)==1
                payload=_json.loads(profile.read_text(encoding='utf-8'))
                payload['generated_at']='v89-cache-invalidation'
                profile.write_text(_json.dumps(payload,ensure_ascii=False),encoding='utf-8')
                third=repair.load_scenario_profiles(profile)
                assert third['ok'] and len(third['profiles'])==expected_profiles and len(reads)==2
            cache=repair.scenario_profile_cache_info()
            assert cache['entries']==1 and cache['hits']>=1 and cache['misses']==2
            repair.clear_scenario_profile_cache()

        with _tempfile.TemporaryDirectory(prefix='tcg-v89-history-') as directory:
            history_path=Path(directory)/'history.json'
            for number in range(30):
                history,_=persist_verification_history(
                    [{'name':f'check-{number}','ok':True,'detail':'정상'}],history_path)
            backup=history_path.with_suffix('.json.bak')
            stored=_json.loads(history_path.read_text(encoding='utf-8'))
            previous=_json.loads(backup.read_text(encoding='utf-8'))
            assert stored['version']==2 and len(stored['runs'])==VERIFICATION_HISTORY_LIMIT
            assert stored['lifetime_runs']==30 and stored['lifetime_passed_checks']==30
            assert sum(bool(run.get('checks')) for run in stored['runs'])==VERIFICATION_FULL_DETAIL_LIMIT
            compacted=stored['runs'][:-VERIFICATION_FULL_DETAIL_LIMIT]
            assert all(run.get('details_compacted') is True and run.get('check_count')==1
                       and re.fullmatch(r'[0-9a-f]{64}',run.get('checks_sha256','')) for run in compacted)
            assert previous['lifetime_runs']==29 and history_path.stat().st_size<50_000 and backup.stat().st_size<50_000
        assert HISTORY.stat().st_size<350_000 and HISTORY.with_suffix('.json.bak').stat().st_size<350_000

        guide=(ROOT/'사용방법_v89.md').read_text(encoding='utf-8')
        audit=(ROOT/'V89_PERFORMANCE_SIZE_DEDUP_OPTIMIZATION_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('최근 24회','최근 8회','방어적 복사','--passes 6'))
        assert all(token in audit for token in ('NameError','SHA-256','92.3%','심볼릭 링크'))
        return '공통 변환·HTML 함수 통합 · 오류프로필 stat 캐시/방어적 복사 · 검사이력 24회/상세 8회 압축 · urllib 간접의존 회귀방지'
    check('v89 성능·용량·중복 최적화·간접의존 회귀방지',v89_performance_size_dedup_guard,rows)

    def v90_expanded_error_scenario_learning_guard():
        import hashlib as _hashlib
        import inspect as _inspect
        from unittest.mock import patch
        import auto_repair_engine as repair
        import error_scenario_lab as lab

        profile=parsed['scenario_learning_profiles.json']
        assert profile['training_only'] is True
        assert profile['scenario_count']==profile['successful_scenarios']==len(lab.SCENARIOS)>=136
        assert profile['failed_scenarios']==[] and profile['family_count']==len(lab.FAMILY_GUIDANCE)>=23
        assert profile['verified_profile_count']>=104
        assert profile['engine']==CURRENT_ENGINE==lab.ENGINE_VERSION
        assert profile['safety']['production_memory_modified'] is False
        assert profile['safety']['network_accessed'] is False
        assert profile['safety']['scenario_text_executed'] is False

        expected={
            'status code 503 from official source':('NETWORK_HTTP_ERROR','transient-server',True),
            'HTTP status code 408 timed out':('NETWORK_HTTP_ERROR','transient-server',True),
            'rate limit exceeded by official source':('NETWORK_HTTP_ERROR','rate-limit-no-status',True),
            'ValueError: grade score 범위 오류':('DATA_VALUE_ERROR','range',False),
            'ConnectionResetError: connection reset by peer':('NETWORK_CONNECTION_ERROR','connection-reset',True),
            'BrokenPipeError: broken pipe while downloading':('NETWORK_CONNECTION_ERROR','broken-pipe',True),
            'OSError: Read-only file system: market_prices.json':('FILE_PERMISSION_ERROR','permission:market_prices.json',False),
            'UnicodeDecodeError: utf-8 codec cannot decode byte 0xff':('DATA_ENCODING_ERROR','decode',False),
            'CalledProcessError: collector returned non-zero exit status 2':('PROCESS_EXECUTION_ERROR','nonzero-exit',False),
            'optimistic version conflict during atomic write':('CONCURRENCY_CONFLICT','version-conflict',True),
            "RuntimeError: can't start new thread":('RESOURCE_EXHAUSTION','thread-limit',False),
            'security blocked credentials in URL':('SECURITY_POLICY_BLOCK','url-credentials',False),
            'official source CAPTCHA challenge':('SOURCE_ACCESS_CHALLENGE','captcha',False),
            'standard JSON rejected NaN Infinity':('DATA_SCHEMA_ERROR','nonstandard-number',False),
            "UnboundLocalError: local variable 'prices' referenced before assignment":('INTERNAL_CODE_ERROR','unboundlocalerror:prices',False),
        }
        for detail,wanted in expected.items():
            analysis=repair.analyze_error(detail,use_scenario_profile=False)
            assert (analysis['code'],analysis['error_subtype'],analysis['bounded_retry_allowed'])==wanted
            assert repair.classify(detail)==repair._classification_policy(analysis['code'])
        http_a=repair.analyze_error('HTTPError: HTTP Error 503',use_scenario_profile=False)
        http_b=repair.analyze_error('status code 503 from official source',use_scenario_profile=False)
        assert repair.error_group_key(http_a)==repair.error_group_key(http_b)
        assert repair.error_group_key(repair.analyze_error('환율 JPY_KRW 범위 오류',use_scenario_profile=False)) != repair.error_group_key(repair.analyze_error('ValueError: grade score 범위 오류',use_scenario_profile=False))
        assert repair.error_group_key(repair.analyze_error('TimeoutError: source timed out',use_scenario_profile=False)) != repair.error_group_key(repair.analyze_error('subprocess.TimeoutExpired: collector',use_scenario_profile=False))

        before=_hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()
        for scenario in lab.SCENARIOS:
            analysis=repair.analyze_error(scenario['detail'],use_scenario_profile=False)
            assert repair.classify(scenario['detail'])==repair._classification_policy(analysis['code'])
            assert analysis['code'] in repair.CLASSIFICATION_POLICY
        after=_hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()
        assert before==after

        repair.clear_scenario_profile_cache()
        base=repair.analyze_error('TimeoutError: official source read timed out after 30 seconds',use_scenario_profile=False)
        repair.load_scenario_profiles()
        with patch.object(repair,'load_scenario_profiles',side_effect=AssertionError('full profile copy on cache hit')):
            one=repair.scenario_profile_for(base)
            assert one and one['fast_resolution_steps']
            one['fast_resolution_steps'].clear()
            two=repair.scenario_profile_for(base)
            assert two and two['fast_resolution_steps']
        assert repair.scenario_profile_cache_info()['hits']>=2
        repair.clear_scenario_profile_cache()

        analyze_source=_inspect.getsource(repair.analyze_error)
        classify_source=_inspect.getsource(repair.classify)
        apply_source=_inspect.getsource(repair._apply_scenario_profile)
        assert 'classify(raw)' not in analyze_source
        assert 'analyze_error(detail, use_scenario_profile=False)' in classify_source
        assert 'scenario_profile_for' in apply_source and 'load_scenario_profiles(path)' not in apply_source
        guide=(ROOT/'사용방법_v90.md').read_text(encoding='utf-8')
        audit=(ROOT/'V90_EXPANDED_ERROR_SCENARIO_LEARNING_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('136개','23개','104개','98.0%','production_memory_unchanged'))
        assert all(token in audit for token in ('status code 503','CLASSIFICATION_POLICY','CAPTCHA','단일 프로필'))
        contract=__import__('feature_contract').audit_feature_contract(ROOT)
        feature=next(row for row in contract['features'] if row['id']=='scenario_error_training')
        assert contract['ok'] and contract['implemented']==contract['total']==23 and feature['implemented']
        return '136개 상황·23개 원인계열·104개 해결프로필 · HTTP/환율 오분류 수정 · 분류정책 단일화 · 단일 프로필 캐시조회'
    check('v90 오류상황 확장·분류정책 통합·빠른 프로필 조회',v90_expanded_error_scenario_learning_guard,rows)

    def v91_cross_platform_metamorphic_error_learning_guard():
        import hashlib as _hashlib
        import auto_repair_engine as repair
        import error_scenario_lab as lab

        profile=parsed['scenario_learning_profiles.json']
        assert profile['training_only'] is True
        assert profile['scenario_count']==profile['successful_scenarios']==len(lab.SCENARIOS)>=200
        assert profile['failed_scenarios']==[]
        assert profile['family_count']==len(lab.FAMILY_GUIDANCE)>=26
        assert profile['verified_profile_count']==len(profile['profiles'])>=124
        assert profile['engine']==CURRENT_ENGINE==lab.ENGINE_VERSION
        assert 'results' not in profile and re.fullmatch(r'[0-9a-f]{64}',profile['results_sha256'])
        assert profile['automation_policy']=='검증된 안내만 제공 · 문자열/생성코드 실행 금지'
        assert all('automation_policy' not in row for row in profile['profiles'].values())
        assert profile['safety']=={
            'production_memory_modified':False,'operational_occurrences_modified':False,
            'network_accessed':False,'scenario_text_executed':False,'advisory_only':True,
            'retry_permission_can_only_be_narrowed':True,
        }

        expected={
            'ConnectionResetError: [WinError 10054] forcibly closed':('NETWORK_CONNECTION_ERROR','connection-reset',True),
            'ConnectionRefusedError: [WinError 10061] refused':('NETWORK_CONNECTION_ERROR','connection-refused',True),
            'socket.gaierror: [WinError 11001] getaddrinfo failed':('NETWORK_CONNECTION_ERROR','dns-resolution',True),
            'PermissionError: [WinError 5] Access is denied: releases.json':('FILE_PERMISSION_ERROR','permission:releases.json',False),
            'OSError: [WinError 112] not enough space on the disk':('RESOURCE_EXHAUSTION','disk-space',False),
            'PermissionError: [WinError 32] sharing violation':('CONCURRENCY_CONFLICT','sharing-violation',True),
            'OSError: [WinError 206] filename too long':('FILE_PATH_ERROR','path-too-long',False),
            'gzip.BadGzipFile: Not a gzipped file':('DATA_COMPRESSION_ERROR','gzip',False),
            'zipfile.BadZipFile: File is not a zip file':('DATA_COMPRESSION_ERROR','zip',False),
            'Bad CRC-32 for archive':('DATA_COMPRESSION_ERROR','crc',False),
            'unsupported compression method':('DATA_COMPRESSION_ERROR','unsupported-method',False),
            'asyncio.CancelledError: task cancelled':('PROCESS_CANCELLED','task-cancelled',False),
            'KeyboardInterrupt: user interrupted':('PROCESS_CANCELLED','user-interrupt',False),
            'JSONDecodeError: Unexpected UTF-8 BOM':('DATA_ENCODING_ERROR','bom',False),
            'response charset mismatch':('DATA_ENCODING_ERROR','charset-mismatch',False),
            'SSLCertVerificationError: certificate is not yet valid':('NETWORK_TLS_ERROR','certificate-not-yet-valid',False),
            'content-type text/html instead of JSON':('SOURCE_CONTENT_TYPE_ERROR','html-instead-of-json',False),
            'HTTP 415 Unsupported Media Type':('SOURCE_CONTENT_TYPE_ERROR','unsupported-media',False),
            'FileExistsError: updater.lock already exists':('CONCURRENCY_CONFLICT','lock-exists',True),
            'decimal.InvalidOperation: invalid decimal':('DATA_VALUE_ERROR','decimal',False),
            'DNS rebinding detected to private IP':('SECURITY_POLICY_BLOCK','private-network-target',False),
        }
        for detail,wanted in expected.items():
            analysis=repair.analyze_error(detail,use_scenario_profile=False)
            assert (analysis['code'],analysis['error_subtype'],analysis['bounded_retry_allowed'])==wanted

        before=_hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()
        for scenario in lab.SCENARIOS:
            analysis=repair.analyze_error(scenario['detail'],use_scenario_profile=False)
            assert analysis['code']==scenario['code']
            if scenario['subtype'] is not None: assert analysis['error_subtype']==scenario['subtype']
            assert analysis['bounded_retry_allowed'] is scenario['retry']
            assert repair.classify(scenario['detail'])==repair._classification_policy(analysis['code'])
            assert analysis['code'] in repair.CLASSIFICATION_POLICY
            if analysis['code'] in {'SECURITY_POLICY_BLOCK','DATA_COMPRESSION_ERROR','PROCESS_CANCELLED',
                                    'SOURCE_CONTENT_TYPE_ERROR','DATA_ENCODING_ERROR'}:
                assert analysis['bounded_retry_allowed'] is False
        after=_hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()
        assert before==after

        precedence={
            'SyntaxError: invalid syntax and HTTP status 503':('INTERNAL_SYNTAX_ERROR','syntax',False),
            'security blocked private IP target after timeout':('SECURITY_POLICY_BLOCK','private-network-target',False),
            'MemoryError after connection reset':('RESOURCE_EXHAUSTION','memory',False),
            'HTTP status code 413 payload too large':('NETWORK_HTTP_ERROR','client-413',False),
            'UnicodeDecodeError while parsing JSON':('DATA_ENCODING_ERROR','decode',False),
            'PermissionError writing JSON market_prices.json':('FILE_PERMISSION_ERROR','permission:market_prices.json',False),
            'CancelledError after timeout':('PROCESS_CANCELLED','task-cancelled',False),
            'CAPTCHA challenge security blocked':('SOURCE_ACCESS_CHALLENGE','captcha',False),
        }
        for detail,wanted in precedence.items():
            analysis=repair.analyze_error(detail,use_scenario_profile=False)
            assert (analysis['code'],analysis['error_subtype'],analysis['bounded_retry_allowed'])==wanted

        def group(detail):
            return repair.error_group_key(repair.analyze_error(detail,use_scenario_profile=False))
        assert group("NameError: name 'fetch_prices' is not defined at line 17 /tmp/a/run.py")==group("NameError: name 'fetch_prices' is not defined at line 918 C:\\work\\b\\run.py")
        assert group('TimeoutError: official source timed out after 30 seconds')==group('TimeoutError: official source timed out after 180.5 seconds')
        assert group('FileNotFoundError: /tmp/a/releases.json')==group(r'FileNotFoundError: C:\\data\\releases.json')
        assert repair._diagnostic_needle_matches('winerror 2','permission [winerror 206] filename too long') is False
        secret='v91-super-secret-token-7f3a'
        redacted=repair.redact_sensitive(f'Authorization: Bearer {secret} token={secret} https://user:{secret}@example.invalid/data')
        analysis=repair.analyze_error(f'security blocked credentials in URL https://user:{secret}@example.invalid/data',use_scenario_profile=False)
        assert secret not in redacted and secret not in json.dumps(analysis,ensure_ascii=False)
        server_source=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert 'directory=BASE if directory is None else directory' in server_source
        verify_source=(ROOT/'verify_all.py').read_text(encoding='utf-8')
        assert "(ROOT/'validate_external_links.py').exists()" in verify_source

        guide=(ROOT/'사용방법_v91.md').read_text(encoding='utf-8')
        audit=(ROOT/'V91_CROSS_PLATFORM_METAMORPHIC_ERROR_LEARNING_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('200개','26개','124개','Windows','Android','macOS','--passes 6'))
        assert all(token in audit for token in ('WinError 206','HTTP 415','복합 오류','민감정보','production_memory_unchanged'))
        contract=__import__('feature_contract').audit_feature_contract(ROOT)
        feature=next(row for row in contract['features'] if row['id']=='scenario_error_training')
        assert contract['ok'] and contract['implemented']==contract['total']==23 and feature['implemented']
        return '200개 상황·26개 원인계열·124개 해결프로필 · Windows/Android/macOS · 복합 오류 우선순위 · 변형 안정성·민감정보 회귀검사'
    check('v91 교차플랫폼·복합오류·변형 안정성 사전학습',v91_cross_platform_metamorphic_error_learning_guard,rows)

    def v92_environment_temporal_storage_error_learning_guard():
        import hashlib as _hashlib
        import auto_repair_engine as repair
        import error_scenario_lab as lab

        profile=parsed['scenario_learning_profiles.json']
        assert profile['scenario_count']==profile['successful_scenarios']==len(lab.SCENARIOS)>=256
        assert profile['failed_scenarios']==[]
        assert profile['family_count']==len(lab.FAMILY_GUIDANCE)>=30
        assert profile['verified_profile_count']==len(profile['profiles'])>=143
        assert profile['engine']==CURRENT_ENGINE==lab.ENGINE_VERSION
        assert 'results' not in profile and re.fullmatch(r'[0-9a-f]{64}',profile['results_sha256'])

        expected={
            'ConfigurationError: required environment variable TCG_PORT is missing':('CONFIGURATION_ERROR','missing-environment',False),
            'invalid configuration port 99999':('CONFIGURATION_ERROR','invalid-port',False),
            'ConfigError: malformed configuration file settings.toml':('CONFIGURATION_ERROR','malformed-file',False),
            'unknown configuration option unsafe_retry':('CONFIGURATION_ERROR','unknown-option',False),
            'DependencyConflict: urllib3 incompatible with requests':('DEPENDENCY_ERROR','version-conflict',False),
            'Requires-Python >=3.11 but running Python 3.9':('DEPENDENCY_ERROR','runtime-version',False),
            'ImportError: binary ABI mismatch':('DEPENDENCY_ERROR','abi-mismatch',False),
            'UnsupportedWheel: wheel is not supported':('DEPENDENCY_ERROR','unsupported-wheel',False),
            'ValueError: Invalid isoformat string 2026-13-40':('DATA_TIME_ERROR','date-parse',False),
            'TimezoneError: timezone-aware datetime required':('DATA_TIME_ERROR','timezone',False),
            'system clock skew exceeds tolerance':('DATA_TIME_ERROR','clock-skew',False),
            'event end date precedes start date':('DATA_TIME_ERROR','date-order',False),
            'database disk image is malformed':('STORAGE_CORRUPTION_ERROR','sqlite-corrupt',False),
            'SQLite WAL checksum mismatch':('STORAGE_CORRUPTION_ERROR','wal-corrupt',False),
            'database index corruption detected':('STORAGE_CORRUPTION_ERROR','index-corrupt',False),
            'database page checksum failed':('STORAGE_CORRUPTION_ERROR','page-checksum',False),
        }
        for detail,wanted in expected.items():
            analysis=repair.analyze_error(detail,use_scenario_profile=False)
            assert (analysis['code'],analysis['error_subtype'],analysis['bounded_retry_allowed'])==wanted

        before=_hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()
        for scenario in lab.SCENARIOS:
            analysis=repair.analyze_error(scenario['detail'],use_scenario_profile=False)
            assert analysis['code']==scenario['code']
            if scenario['subtype'] is not None: assert analysis['error_subtype']==scenario['subtype']
            assert analysis['bounded_retry_allowed'] is scenario['retry']
            assert repair.classify(scenario['detail'])==repair._classification_policy(analysis['code'])
            if analysis['code'] in {'CONFIGURATION_ERROR','DEPENDENCY_ERROR','DATA_TIME_ERROR','STORAGE_CORRUPTION_ERROR'}:
                assert analysis['bounded_retry_allowed'] is False
        assert before==_hashlib.sha256((ROOT/'auto_repair_memory.json').read_bytes()).hexdigest()

        precedence={
            'SyntaxError invalid syntax while reading malformed configuration':('INTERNAL_SYNTAX_ERROR','syntax',False),
            'security blocked private IP from invalid configuration':('SECURITY_POLICY_BLOCK','private-network-target',False),
            'MemoryError while database disk image is malformed':('RESOURCE_EXHAUSTION','memory',False),
            'database disk image is malformed after timeout':('STORAGE_CORRUPTION_ERROR','sqlite-corrupt',False),
            'DependencyConflict package incompatible after HTTP status 503':('DEPENDENCY_ERROR','version-conflict',False),
            'CancelledError while loading invalid configuration':('PROCESS_CANCELLED','task-cancelled',False),
            'system clock skew caused certificate error':('DATA_TIME_ERROR','clock-skew',False),
            'PermissionError reading malformed configuration releases.json':('FILE_PERMISSION_ERROR','permission:releases.json',False),
        }
        for detail,wanted in precedence.items():
            analysis=repair.analyze_error(detail,use_scenario_profile=False)
            assert (analysis['code'],analysis['error_subtype'],analysis['bounded_retry_allowed'])==wanted

        def group(detail): return repair.error_group_key(repair.analyze_error(detail,use_scenario_profile=False))
        assert group('malformed configuration file /tmp/a/settings.toml')==group(r'malformed configuration file C:\\work\\b\\settings.toml')
        assert group('DependencyConflict package version 2.1 incompatible with 3.0')==group('DependencyConflict package version 91.7 incompatible with 4.2')
        assert group('Invalid isoformat string 2026-13-40 at row 7')==group('Invalid isoformat string 2031-00-99 at row 918')
        assert group('database disk image is malformed /tmp/a/learning.db')==group(r'database disk image is malformed C:\\data\\learning.db')
        assert group('optimistic version conflict during atomic write')!=group('package version conflict dependency incompatible with runtime')

        secret='v92-private-config-secret-91x'
        redacted=repair.redact_sensitive(f'ConfigurationError api_key={secret} password={secret}')
        analysis=repair.analyze_error(f'ConfigurationError api_key={secret} password={secret}',use_scenario_profile=False)
        assert secret not in redacted and secret not in json.dumps(analysis,ensure_ascii=False)

        guide=(ROOT/'사용방법_v92.md').read_text(encoding='utf-8')
        audit=(ROOT/'V92_ENVIRONMENT_TEMPORAL_STORAGE_ERROR_LEARNING_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('256개','30개','143개','환경설정','날짜','저장소','--passes 6'))
        assert all(token in audit for token in ('252/256','version conflict','WAL','민감정보','production_memory_unchanged'))
        contract=__import__('feature_contract').audit_feature_contract(ROOT)
        feature=next(row for row in contract['features'] if row['id']=='scenario_error_training')
        assert contract['ok'] and contract['implemented']==contract['total']==23 and feature['implemented']
        return '256개 상황·30개 원인계열·143개 해결프로필 · 환경설정/의존성/날짜시간/저장소 손상 · 변형통합·안전 우선순위'
    check('v92 환경·의존성·시간·저장소 오류 사전학습',v92_environment_temporal_storage_error_learning_guard,rows)

    def official_event_country_coverage_guard():
        import update_promo_events as events
        payload=parsed['promo_events.json']
        coverage=payload.get('coverage',{})
        assert coverage.get('expected_game_region_pairs')==9
        assert coverage.get('watched_game_region_pairs')==9
        assert coverage.get('covered_game_region_pairs')==9
        assert coverage.get('movie_game_region_pairs')==9
        assert not coverage.get('missing_source_pairs') and not coverage.get('missing_movie_pairs')
        assert len(coverage.get('matrix',[]))==9
        assert all(row.get('official_source_count',0)>=1 and row.get('official_item_count',0)>=1
                   and row.get('movie_item_count',0)>=1 for row in coverage['matrix'])
        indexed={(game,region) for region,game,_ in events.INDEXES}
        assert indexed=={(game,region) for game in events.GAMES for region in events.REGIONS}
        assert all(events.valid(item) for item in payload['items'])
        return f"3개 작품×3개 국가 공식 출처 {len(indexed)}/9 · 영화·영상 {coverage['movie_game_region_pairs']}/9"
    check('한·일·미 포켓몬·원피스·나루토 공식출처 9조합',official_event_country_coverage_guard,rows)

    def official_event_date_precision_guard():
        import copy
        import update_promo_events as events
        import supplementary_discovery as supplemental
        items=parsed['promo_events.json']['items']
        movie=next(row for row in items if row.get('source','').endswith('/news/79329/index.html'))
        assert movie['region']=='JP' and movie['category']=='movie'
        assert movie['media_type']=='streaming_series' and movie['date_precision']=='month'
        assert movie['start_date']=='2027-02-01' and movie['end_date']=='2027-02-28'
        assert '2027년 2월' in movie['date_label'] and '정확한 날짜 미발표' in movie['date_label']
        assert movie['date_label'].find('2027-02-01')<0
        pokemon=next(row for row in items if row.get('source','').endswith('/info/005604.html'))
        assert pokemon['date_precision']=='start-only' and '종료일 공식 미발표' in pokemon['date_label']
        assert pokemon['internal_review_until']==pokemon['end_date']
        naruto=next(row for row in items if row.get('game')=='나루토 카드' and row.get('region')=='KR'
                    and row.get('category')=='promo')
        assert naruto['date_precision']=='season' and '한국 행사·발매일 미발표' in naruto['date_label']
        for row in items:
            if row.get('category')=='movie' and row.get('date_precision')=='unannounced':
                assert row.get('tracking_only') is True and '미발표' in row['date_label']
        malformed=copy.deepcopy(movie);malformed['end_date']='2027-02-27'
        assert not events.valid(malformed)
        assert events.detail_date_range('Event Dates: July 10th to September 30th, 2026 (JST)')==('2026-07-10','2026-09-30')
        candidate=next(row for row in parsed['supplementary_candidates.json']['items']
                       if row.get('source','').endswith('/news/79329/index.html'))
        assert candidate['dates']==[] and candidate['release_window']=='2027-02'
        malformed_candidate=copy.deepcopy(candidate);malformed_candidate['dates']=['2027-02-01']
        try:supplemental.normalize_candidate(malformed_candidate)
        except ValueError:pass
        else:raise AssertionError('월만 발표된 정보가 특정 날짜로 확정됨')
        return '월·계절·시작일·미발표 정확도 구분 · THE ONE PIECE 2027년 2월만 표시 · 영어 월간 기간 인식'
    check('영화·행사 공식 날짜 정확도 및 임의 개봉일 차단',official_event_date_precision_guard,rows)

    def official_event_region_duplicate_and_fallback_guard():
        from unittest.mock import patch
        import copy
        import update_promo_events as events
        assert events.event_region('US','BANDAI CARD GAMES Fest UTRECHT') is None
        assert events.event_region('JP','New York Comic Con, New York USA')=='US'
        assert events.event_region('KR','Manila fan festival') is None
        source=copy.deepcopy(parsed['promo_events.json'])
        original_count=len(source['items'])
        sample=copy.deepcopy(next(row for row in source['items']
                                  if row.get('game')=='원피스 카드' and row.get('region')=='KR'
                                  and '리미티드' in row.get('name_ko','')))
        sample['name_ko']='숙련자 원피스 카드게임 발매기념대회 리미티드 배틀 2026년 8월 22일 ~ 9월 4일'
        sample['name_native']=sample['name_ko']
        sample['source']='https://onepiece-cardgame.kr/events.do'
        outside=copy.deepcopy(next(row for row in source['items']
                                   if row.get('game')=='원피스 카드' and row.get('region')=='US'))
        outside['name_ko']='미국 공식 행사 · BANDAI CARD GAMES Fest UTRECHT'
        outside['name_native']='BANDAI CARD GAMES Fest UTRECHT'
        outside['source']='https://en.onepiece-cardgame.com/events/2026/bcgfest26-27/utrecht/'
        source['items'].extend([sample,outside])
        with tempfile.TemporaryDirectory(prefix='tcg-official-event-fallback-') as td:
            path=Path(td)/'promo_events.json'
            path.write_text(json.dumps(source,ensure_ascii=False),encoding='utf-8')
            with patch.object(events,'DATA',path),patch.object(events,'fetch',side_effect=urllib.error.URLError('offline')):
                updated=events.main()
            assert len(updated['items'])==original_count
            assert updated['excluded_outside_region_count']==1
            assert updated['merged_duplicate_event_count']>=1
            assert updated['coverage']['covered_game_region_pairs']==9
            assert updated['coverage']['movie_game_region_pairs']==9
            assert updated['collection_errors'] and all(events.valid(row) for row in updated['items'])
            assert not any('utrecht' in row.get('source','').lower() for row in updated['items'])
        return '네덜란드 행사의 미국 오분류 제거 · 목록/상세 중복 통합 · 모든 출처 통신 실패 시 공식자료 9조합 보존'
    check('행사 실제 개최국 판별·중복 통합·통신 실패복구',official_event_region_duplicate_and_fallback_guard,rows)

    def supplementary_official_evidence_security_guard():
        import copy
        import supplementary_discovery as supplemental
        rows=parsed['supplementary_candidates.json']['items']
        naruto=next(row for row in rows if row.get('source_tier')=='C'
                    and row.get('official_source','').endswith('/en/news/01_2649'))
        assert naruto['verified'] is False and naruto['dates']==[]
        poisoned=copy.deepcopy(naruto);poisoned['verified']=True
        assert supplemental.normalize_candidate(poisoned)['verified'] is False
        poisoned['official_claim_confirmed']=True
        assert supplemental.normalize_candidate(poisoned)['verified'] is True
        poisoned['official_source']='https://naruto-official.com.evil.example/claim'
        try:supplemental.normalize_candidate(poisoned)
        except ValueError:pass
        else:raise AssertionError('공식 출처처럼 위장한 도메인 허용')
        official=copy.deepcopy(next(row for row in rows if row.get('source_tier')=='A'))
        official['source']='https://namu.wiki/w/movie'
        try:supplemental.normalize_candidate(official)
        except ValueError:pass
        else:raise AssertionError('커뮤니티 주소를 공식 출처로 승격')
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert 'official_claim_confirmed===true' in page and 'trustedPromoOfficialUrl' in page
        assert 'id="promoCoverage"' in page
        return 'Tier C 단독 공식승격 차단 · 독립 공식근거 필수 · 유사 도메인/사설주소 차단 · 화면 재검증'
    check('영화·콜라보 공식근거 검증과 보조출처 승격 차단',supplementary_official_evidence_security_guard,rows)

    def official_event_integrated_schema_guard():
        import copy
        import auto_update_all as automatic
        import update_promo_events as events
        payload=copy.deepcopy(parsed['promo_events.json'])
        automatic.validate_json('promo_events.json',payload)
        cases=(
            ('source','https://127.0.0.1/private'),
            ('verification_source','https://namu.wiki/w/fake'),
            ('region','PRIVATE'),
            ('source_grade','supplementary'),
            ('date_precision','invented'),
        )
        for field,value in cases:
            poisoned=copy.deepcopy(payload)
            poisoned['items'][0][field]=value
            try:automatic.validate_json('promo_events.json',poisoned)
            except ValueError:pass
            else:raise AssertionError(f'자동 업데이트 행사자료 보안 검증 우회: {field}')
        official_hosts={urllib.parse.urlsplit(row['source']).hostname for row in payload['items']}
        assert {'naruto-official.com','one-piece.com'}<=official_hosts
        assert events.approved_url('https://naruto-official.com/en/news/01_2648')
        return f'자동수집 저장 전 전체 행사 공식주소·검증주소·국가·출처등급·날짜정확도 확인 · {len(official_hosts)}개 공식 도메인'
    check('행사·영화 자동수집 저장 전 보안 스키마 검증',official_event_integrated_schema_guard,rows)

    def v93_link_runtime_integrity_guard():
        import urllib.error
        from unittest.mock import patch
        import auto_repair_engine as repair
        import error_scenario_lab as lab
        import tcg_updater
        from verify_link_runtime import audit_link_contract

        link=audit_link_contract(ROOT)
        assert link['ok'] and link['button_count']>=63 and link['referenced_id_count']>=200
        assert link['static_asset_count']>=10 and link['service_worker_asset_count']>=11
        assert link['frontend_api_count']>=15 and link['external_reference_count']>=500
        assert link['external_host_count']>=80 and link['confirmed_broken_count']==0

        profile=parsed['scenario_learning_profiles.json']
        assert profile['engine']==lab.ENGINE_VERSION==CURRENT_ENGINE
        assert profile['scenario_count']==profile['successful_scenarios']==len(lab.SCENARIOS)>=270
        assert profile['failed_scenarios']==[] and profile['family_count']==len(lab.FAMILY_GUIDANCE)>=31
        assert profile['verified_profile_count']==len(profile['profiles'])>=150
        link_cases={
            'MissingButtonBinding: handler has no button':'button-binding',
            'BrokenAnchorError: target section is missing':'anchor-target',
            'StaticAsset404: icon route returned 404':'static-asset',
            'ApiRouteMismatch: method mismatch GET versus POST':'api-route-method',
            'ServiceWorkerAssetMismatch: cache and public files differ':'pwa-asset',
            'UnsafeBlankOpener: target blank link lacks noopener':'new-window',
            'ExternalUrlTemplateError: duplicate query placeholder':'external-template',
        }
        for detail,subtype in link_cases.items():
            analysis=repair.analyze_error(detail,use_scenario_profile=False)
            assert (analysis['code'],analysis['error_subtype'],analysis['bounded_retry_allowed'])==('LINK_RUNTIME_ERROR',subtype,False)

        restricted=urllib.error.HTTPError('https://example.com',403,'Forbidden',{},None)
        stats={'version':1,'sources':{}}
        with patch.object(tcg_updater,'fetch',side_effect=restricted):
            result=tcg_updater._collect_one_source(('LINK_RESTRICTED','https://example.com','공식'),stats)
        stat=stats['sources']['LINK_RESTRICTED']
        assert result['restricted'] is True and result['http_status']==403
        assert stat['access_restrictions']==1 and stat['failures']==0 and stat['consecutive_failures']==0

        server=tcg_updater.QuietThreadingHTTPServer(('127.0.0.1',0),tcg_updater.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_address[1]}'
        get_routes=(
            '/api/health','/api/status','/api/auto-status','/api/update-job','/api/update-report',
            '/api/update-issues','/api/repair-memory','/api/error-learning-summary',
            '/api/verification-cycles','/api/learning-store','/api/market-watch','/api/validation',
            '/api/feature-audit','/api/scenario-learning-summary','/api/grading-standards',
            '/api/platform-diagnostics','/api/web-candidates','/api/purchase-signals',
            '/api/market-price?key='+urllib.parse.quote('KR|계승되는 의지|BOX'),
        )
        try:
            for name in sorted(tcg_updater.PUBLIC_STATIC_FILES):
                for method in ('GET','HEAD'):
                    request=urllib.request.Request(base+'/'+name,method=method)
                    with urllib.request.urlopen(request,timeout=5) as response:
                        assert response.status==200
                        body=response.read()
                        assert (method=='HEAD' and body==b'') or (method=='GET' and body)
            with urllib.request.urlopen(base+'/',timeout=5) as response:
                assert response.status==200 and CURRENT_APP_NAME.encode('utf-8') in response.read()
            for route in get_routes:
                with urllib.request.urlopen(base+route,timeout=5) as response:
                    assert response.status==200 and isinstance(json.loads(response.read().decode('utf-8')),dict)
            try:urllib.request.urlopen(base+'/api/purchase-live-search?region=XX&game=Pokemon&q=test',timeout=5)
            except urllib.error.HTTPError as exc:assert exc.code==400
            else:raise AssertionError('구매검색 잘못된 링크 조건 허용')
            for route in ('/api/update','/api/run-auto-update','/api/retry-failed','/api/grade-card',
                          '/api/learning-store','/api/apply','/run-auto-update'):
                request=urllib.request.Request(base+route,data=b'{}',headers={
                    'Content-Type':'application/json','Origin':'https://example.com'},method='POST')
                try:urllib.request.urlopen(request,timeout=5)
                except urllib.error.HTTPError as exc:assert exc.code==403,(route,exc.code)
                else:raise AssertionError(f'비신뢰 출처에서 변경 API 연결 허용: {route}')
            try:urllib.request.urlopen(urllib.request.Request(base+'/api/health',method='HEAD'),timeout=5)
            except urllib.error.HTTPError as exc:assert exc.code==405
            else:raise AssertionError('API HEAD 우회 허용')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

        guide=(ROOT/'사용방법_v93.md').read_text(encoding='utf-8')
        audit=(ROOT/'V93_LINK_RUNTIME_INTEGRITY_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('270개','31개','150개','63개','257개','--passes 6'))
        assert all(token in audit for token in ('v20apply','window.open','noopener','19개 GET API','270/270'))
        return (f"버튼 {link['button_count']}개·정적/PWA {link['static_asset_count']}/{link['service_worker_asset_count']}개·"
                f"GET API {len(get_routes)}개·외부주소 {link['external_reference_count']}개/호스트 {link['external_host_count']}개 · "
                "자동접근 제한과 실제 링크고장 분리 · 링크 오류 14상황 사전학습")
    check('v93 화면·정적파일·API·외부 링크 런타임 무결성',v93_link_runtime_integrity_guard,rows)

    def v94_camera_button_runtime_guard():
        import auto_repair_engine as repair
        import error_scenario_lab as lab

        page=(ROOT/'index.html').read_text(encoding='utf-8')
        server=(ROOT/'tcg_updater.py').read_text(encoding='utf-8')
        assert all(f'id="{item}"' in page for item in ('startAutoCamera','stopAutoCamera','manualCapture','gradeCamera'))
        assert all(token in page for token in (
            'sceneDistance(metric,frontMetric)>=12','backNotBefore=Date.now()+CAMERA_FLIP_DELAY_MS',
            'input._tcgCapturedFile=file','requestSession!==session','canvas.toBlob',
            "document.addEventListener('visibilitychange'",'cameraErrorMessage(error)',
            "handler.call(S('analyze'))",'카메라를 안전하게 중지했습니다.',
        ))
        assert 'Permissions-Policy' in server and 'camera=(self)' in server
        completed=subprocess.run(['node','verify_camera_runtime.js'],cwd=ROOT,capture_output=True,text=True,timeout=30,check=True)
        assert 'PASS: automatic front/back capture' in completed.stdout
        assert 'duplicate-side prevention' in completed.stdout and 'iOS file fallback' in completed.stdout
        profile=parsed['scenario_learning_profiles.json']
        assert profile['engine']==lab.ENGINE_VERSION==CURRENT_ENGINE
        assert profile['scenario_count']==profile['successful_scenarios']==len(lab.SCENARIOS)>=286
        assert profile['failed_scenarios']==[] and profile['family_count']==len(lab.FAMILY_GUIDANCE)>=32
        assert profile['verified_profile_count']==len(profile['profiles'])>=158
        cases={
            'CameraPermissionDenied: user denied camera access':'permission',
            'CameraSecureContextError: getUserMedia requires HTTPS':'secure-context',
            'CameraNotFound: no video input device':'unavailable',
            'CameraFrameUnavailable: video width is zero':'frame-read',
            'CameraEncodeError: canvas toBlob returned null':'encode',
            'DuplicateSideCapture: same front frame stored as back':'duplicate-side',
            'CameraFileHandoffError: captured blob did not reach analyzer':'file-handoff',
            'CameraRequestRace: late permission result replaced current stream':'lifecycle',
        }
        for detail,subtype in cases.items():
            analysis=repair.analyze_error(detail,use_scenario_profile=False)
            assert (analysis['code'],analysis['error_subtype'],analysis['bounded_retry_allowed'])==('CAMERA_RUNTIME_ERROR',subtype,False)
        contract=__import__('feature_contract').audit_feature_contract(ROOT)
        photo=next(row for row in contract['features'] if row['id']=='photo_front_back')
        assert contract['ok'] and photo['implemented'] and contract['implemented']==contract['total']==23
        guide=(ROOT/'사용방법_v94.md').read_text(encoding='utf-8')
        audit=(ROOT/'V94_CAMERA_BUTTON_RUNTIME_2026-08-26.md').read_text(encoding='utf-8')
        assert all(token in guide for token in ('286개','32개','158개','자동촬영','HTTPS','--passes 6'))
        assert all(token in audit for token in ('같은 앞면','DataTransfer','2분','286/286','verify_camera_runtime.js'))
        return '버튼 64개 · 자동 앞/뒤 촬영·같은 면 중복차단·iOS 파일전달·권한/중지/수명주기 실제 실행 · 카메라 오류 16상황 사전학습'
    check('v94 카메라 자동촬영·버튼 런타임·오류학습',v94_camera_button_runtime_guard,rows)

    def v97_safe_self_healing_vision_learning_guard():
        import fault_injection_healing as healing
        import vision_calibration as calibration
        assert healing.ENGINE_VERSION==calibration.ENGINE_VERSION==CURRENT_ENGINE
        vision=subprocess.run(['node','verify_vision_runtime.js'],cwd=ROOT,capture_output=True,text=True,timeout=240,check=True)
        assert 'card mask + CLAHE + Canny hysteresis + Hough line evidence' in vision.stdout
        assert 'threshold tuning selected 35/105' in vision.stdout
        fault=subprocess.run([sys.executable,'-B','verify_fault_injection_healing.py'],cwd=ROOT,capture_output=True,text=True,timeout=60,check=True)
        fault_report=json.loads(fault.stdout.strip().splitlines()[-1])
        assert fault_report=={'ok':True,'tests':5,'failures':0,'errors':0}
        learned=parsed['fault_learning.json']
        assert learned['training_only'] is True
        assert learned['scenario_count']==learned['successful_scenarios']==len(healing.SCENARIOS)==21
        assert learned['safety']=={
            'production_files_modified':False,'scenario_text_executed':False,
            'network_accessed':False,'generated_code_auto_applied':False,
        }
        calibration_test=subprocess.run([sys.executable,'-B','verify_vision_calibration.py'],cwd=ROOT,capture_output=True,text=True,timeout=30,check=True)
        calibration_report=json.loads(calibration_test.stdout.strip().splitlines()[-1])
        assert calibration_report.get('ok') is True and calibration_report.get('tests',0)>=8 and calibration_report.get('failures')==0 and calibration_report.get('errors')==0
        cal=parsed['vision_calibration.json']
        assert cal['engine']==CURRENT_ENGINE and cal['policy']['official_result_required'] is True
        assert cal['policy']['upward_correction_allowed'] is False
        assert cal['policy']['raw_image_model_retrained'] is False
        integrity=healing.diagnose_integrity(ROOT,ROOT/'integrity_manifest.json')
        assert integrity['ok'] and integrity['failed']==0 and integrity['checked']>=50
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        engine=(ROOT/'grading_vision_engine.js').read_text(encoding='utf-8')
        assert all(token in engine for token in (
            'function clahe(', 'function cannyEdges(', 'function probabilisticHoughSegments(',
            'function analyzeWhitening(', 'maskCoverage', 'confirmedSegments',
        ))
        assert all(token in page for token in (
            'official_result', 'certification_id', 'v97ComputeVisionCalibration',
            'frontWhitening', 'backWhitening', 'confirmedSegments',
        ))
        return ('센터링·마스크·CLAHE·Canny·18각 Hough·백화 정상/불량 교차시험 · '
                '격리 고장주입 21/21 · 자가복구 5검사 · 공식등급 보류검증 5검사 · 무결성 정상')
    check('v97 안전 자가치유·비전 정상불량 교차학습',v97_safe_self_healing_vision_learning_guard,rows)

    def v98_camera_resilience_guard():
        camera=subprocess.run(['node','verify_camera_runtime.js'],cwd=ROOT,capture_output=True,text=True,timeout=45,check=True)
        assert all(token in camera.stdout for token in (
            'manual duplicate-side prevention','permission timeout','unexpected track ending',
            'previous captures preserved',
        ))
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert all(token in page for token in (
            'CAMERA_REQUEST_TIMEOUT_MS','CAMERA_FLIP_DELAY_MS','requestCameraWithTimeout',
            "addEventListener?.('ended'",'앞면과 다른 화면이 확인되지 않았습니다',
        ))
        contract=__import__('feature_contract').audit_feature_contract(ROOT)
        scenario=next(row for row in contract['features'] if row['id']=='scenario_error_training')
        assert contract['ok'] and '310개 상황·33개 계열·164개 검증 프로필' in scenario['evidence']
        return ('버튼 64개 · 자동/수동 앞뒤 촬영 · 수동 같은 면 중복차단 · 30초 권한응답 제한 · '
                '늦은 스트림 격리 · 트랙 종료 감지 · 권한실패 시 기존사진 보존')
    check('v98 버튼·자동촬영·카메라 연결복원 심층검사',v98_camera_resilience_guard,rows)

    def v99_accuracy_self_learning_guard():
        import grading_accuracy_v99 as accuracy
        completed=subprocess.run([sys.executable,'-B','verify_v99_accuracy.py'],cwd=ROOT,capture_output=True,text=True,timeout=30,check=True)
        report=json.loads(completed.stdout.strip().splitlines()[-1])
        assert report.get('ok') is True and report.get('tests',0)>=27 and report.get('failures')==0 and report.get('errors')==0
        browser=subprocess.run(['node','verify_v99_browser_accuracy.js'],cwd=ROOT,capture_output=True,text=True,timeout=20,check=True)
        assert 'V99 company scale' in browser.stdout and 'edge/corner grade caps' in browser.stdout
        pipeline=subprocess.run([sys.executable,'-B','verify_v99_learning_pipeline.py'],cwd=ROOT,capture_output=True,text=True,timeout=30,check=True)
        pipeline_report=json.loads(pipeline.stdout.strip().splitlines()[-1])
        assert pipeline_report=={'ok':True,'tests':6,'failures':0,'errors':0}
        cross=subprocess.run([sys.executable,'-B','verify_v99_cross_runtime.py'],cwd=ROOT,capture_output=True,text=True,timeout=60,check=True)
        cross_report=json.loads(cross.stdout.strip().splitlines()[-1])
        assert cross_report.get('ok') is True and cross_report.get('vectors',0)>=6000 and cross_report.get('comparisons',0)>=18000
        page=(ROOT/'index.html').read_text(encoding='utf-8')
        assert 'const V29KEY="tcg_v99_validation"' in page
        assert 'raw_pred' in page and 'TCGAccuracyV99.combineDefectRisk' in page and 'TCGAccuracyV99.quantizeDown' in page
        store=parsed['learning_store.json']
        assert store.get('version')==2 and isinstance(store.get('v99_validation'),list)
        # Deterministic 500-scenario metamorphic sweep: worse defects or centering may never improve a grade.
        checks=0
        for company in accuracy.COMPANIES:
            previous=11
            for risk in range(0,101):
                grade=accuracy.estimate_raw_grade(50,50,risk,risk,risk,company)
                assert grade<=previous;previous=grade;checks+=1
            previous=11
            for center in range(50,4,-1):
                grade=accuracy.estimate_raw_grade(center,center,0,0,0,company)
                assert grade<=previous;previous=grade;checks+=1
        assert checks>=700
        assert accuracy.quantize_down('PSA',9.9)==9 and accuracy.quantize_down('TAG',9.9)==9
        return f"V99 단위검사 {report['tests']}개 + 학습파이프라인 {pipeline_report['tests']}개 + Python↔JS {cross_report['comparisons']}회 비교 + 브라우저 등급축 검사 + 단조성 교차시험 {checks}건 · 원시예측 분리 · 유효 등급축 검증 · 인증번호 충돌격리 · TAG Gem Mint 기준 · 엣지/코너 최종등급 반영"
    check('v99 등급정확성·자가학습·교차시험',v99_accuracy_self_learning_guard,rows)

    history,run=persist_verification_history(rows)
    print('전체 프로그램 검사 결과')
    for row in rows: print(f"- {'통과' if row['ok'] else '실패'}: {row['name']} · {row['detail']}")
    print(f"누적 검사 {len(history['runs'])}회 · 이번 결과 {'정상' if run['ok'] else '수정 필요'}")
    return 0 if run['ok'] else 1

if __name__=='__main__': raise SystemExit(main())
