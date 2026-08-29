#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, sys, re, hashlib, threading, webbrowser, time, socket, ipaddress, subprocess, platform, shutil, concurrent.futures, math, signal
from pathlib import Path
import urllib.error
import urllib.request
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen
from grading_accuracy_v99 import valid_actual_grade
from safe_runtime import (
    MAX_SAFE_FILE_BYTES,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_text,
    bounded_float as _safe_stat_float,
    bounded_int as _safe_stat_int,
    env_int,
    open_safe_binary,
    reject_nonstandard_json as _reject_nonstandard_json,
    require_public_https,
    safe_read_bytes,
    safe_read_text,
    unique_json_object as _unique_json_object,
)

BASE=os.path.dirname(os.path.abspath(__file__))
INTEGRATED_VERSION='v109-card-identity-ocr-learning'
SERVICE_NAME='TCG v109 Updater'
DB=os.path.join(BASE,'tcg_live_data.json')
MARKET_DB=os.path.join(BASE,'market_prices.json')
MARKET_WATCH=os.path.join(BASE,'market_watch.json')
AUTO_REPORT=os.path.join(BASE,'auto_update_report.json')
AUTO_ISSUES=os.path.join(BASE,'auto_update_issues.json')
AUTO_MEMORY=os.path.join(BASE,'auto_repair_memory.json')
LEARNING_STORE=os.path.join(BASE,'learning_store.json')
VISION_SELF_LEARNING_REPORT=os.path.join(BASE,'vision_self_learning_report.json')
EBAY_GRADER_CANDIDATES=os.path.join(BASE,'ebay_grader_candidates.json')
VERIFIED_CERTIFICATIONS=os.path.join(BASE,'verified_certifications.json')
CARD_IDENTITY_LEARNING=os.path.join(BASE,'card_identity_learning.json')
SOURCE_STATS=os.path.join(BASE,'source_collection_stats.json')
SOURCE_STATS_BAK=SOURCE_STATS+'.bak'
SOURCE_STATS_LOCK=threading.Lock()
AUTO_INTERVAL_SECONDS=6*60*60
PRECOLLECT_LEAD_SECONDS=30*60
PRECOLLECT_STAGE=os.path.join(BASE,'.precollect_stage')
PRECOLLECT_STATUS=os.path.join(BASE,'precollect_status.json')
UPDATE_LOCK=threading.Lock()
MANUAL_UPDATE_LOCK=threading.Lock()
DATA_WRITE_LOCK=threading.RLock()
DB_MUTATION_LOCK=threading.RLock()
LAST_MANUAL_UPDATE=0.0
MANUAL_UPDATE_COOLDOWN_SECONDS=10
UPDATE_JOB_LOCK=threading.Lock()
SEARCH_LIMIT_LOCK=threading.Lock()
SEARCH_LIMIT_BUCKETS={}
SEARCH_LIMIT_WINDOW_SECONDS=10.0
SEARCH_LIMIT_REQUESTS=12
UPDATE_JOB={
    'id':None,'state':'idle','trigger':None,'started_at':None,'finished_at':None,
    'current':0,'total':6,'label':'대기 중','file':None,'message':'대기 중',
    'error':None,'report':None,'retry_only':False,
}
PUBLIC_STATIC_FILES={
    'index.html','icon.svg','manifest.webmanifest','sw.js','grading_vision_engine.js','grading_accuracy_v99.js','card_identity_recognition.js',
    'vision_calibration.json',
    'releases.json','market_prices.json','market_watch.json',
    'promo_events.json','supplementary_candidates.json','social_event_candidates.json',
    'purchase_sources.json','purchase_signals.json','exchange_rates.json','inventory_lookup.js','inventory_lookup.css','grade_market_flow.js','grade_market_flow.css','grading_proxy_costs.js','grading_proxy_costs.css','grading_costs_live.js','grading_costs_live.css'
}
SOURCES=[
 ('포켓몬 한국 공식','https://pokemoncard.co.kr/card/category/info1','공식'),
 ('포켓몬 일본 공식','https://www.pokemon-card.com/products/index.html','공식'),
 ('포켓몬 30주년 공식','https://www.30th.pokemon-card.com/','공식'),
 ('원피스 한국 공식','https://onepiece-cardgame.kr/products.do','공식'),
 ('원피스 일본 공식','https://www.onepiece-cardgame.com/','공식'),
 ('원피스 미국 공식','https://en.onepiece-cardgame.com/products/','공식'),
 ('나루토 카드게임 글로벌 공식','https://www.naruto-cardgame.com/asia-en/','공식'),
 ('포켓몬 일본 프로모 행사 공식','https://www.pokemon-card.com/info/005397.html','행사'),
 ('PSA 공식 등급기준','https://www.psacard.com/gradingstandards','등급'),
 ('BGS 공식 등급','https://www.beckett.com/grading/scale','등급'),
 ('CGC 공식 등급','https://www.cgccards.com/card-grading/grading-scale/','등급'),
 ('TAG 공식 등급','https://taggrading.com/pages/scale','등급'),
 ('BRG 공식 등급','https://break.co.kr/','등급'),
 ('Collectory 공개 카드시세','https://collectory.cc/cards','시세'),
 ('KREAM 공개 TCG 시세','https://kream.co.kr/search?keyword=%ED%8F%AC%EC%BC%93%EB%AA%AC+TCG','시세'),
]

def free_port(start=8765, limit=30):
    for port in range(start,start+limit):
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                sock.bind(('0.0.0.0',port))
            return port
        except OSError:
            pass
    raise OSError('사용 가능한 로컬 포트를 찾지 못했습니다.')

PORT=8765
PLATFORM='Android 태블릿' if 'com.termux' in os.environ.get('PREFIX','') else ('Windows PC' if os.name=='nt' else platform.system())
TRUSTED_PAGES_ORIGIN='https://wlghks24.github.io'

def choose_lan_ip(candidates):
    """Prefer a real home LAN address over VPN/virtual-adapter addresses."""
    valid=[]
    for raw in candidates:
        try: ip=ipaddress.ip_address(str(raw).strip())
        except ValueError: continue
        if ip.version!=4 or ip.is_loopback or ip.is_link_local or not ip.is_private: continue
        text=str(ip)
        score=300 if text.startswith('192.168.') else 200 if ip in ipaddress.ip_network('172.16.0.0/12') else 100
        valid.append((score,text))
    return max(valid,default=(0,'127.0.0.1'))[1]

def lan_ipv4_candidates():
    found=[]
    try:
        probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        probe.connect(('8.8.8.8',80));found.append(probe.getsockname()[0]);probe.close()
    except OSError: pass
    try:
        found.extend(x[4][0] for x in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET))
    except OSError: pass
    if os.name=='nt':
        try:
            output=subprocess.check_output(['ipconfig'],stderr=subprocess.DEVNULL,timeout=8).decode('mbcs','ignore')
            found.extend(re.findall(r'IPv4[^:]*:\s*([0-9.]+)',output,re.I))
        except (OSError,subprocess.SubprocessError): pass
    return list(dict.fromkeys(found))

def default_db():
    return {'updated_at':None,'sources':{},'pending':[],'applied':[],
            'auto_update':{'enabled':True,'interval_hours':6,'precollect_lead_minutes':30,'last_run':None,'next_run':None,'next_precollect':None,'status':'대기 중'}}

def load_db():
    try:
        data=strict_json_loads(safe_read_text(DB,max_bytes=MAX_SAFE_FILE_BYTES),max_depth=32,max_nodes=200000)
        if not isinstance(data,dict):
            return default_db()
        base=default_db()
        for k,v in base.items():
            current=data.get(k)
            if isinstance(v,dict):
                data[k]={**v,**current} if isinstance(current,dict) else dict(v)
            elif isinstance(v,list):
                data[k]=current if isinstance(current,list) else list(v)
            else:
                data.setdefault(k,v)
        return data
    except (OSError,ValueError,TypeError):
        return default_db()

def save_db(data):
    # Serialize concurrent requests while rejecting symlinks and shared temporary paths.
    with DATA_WRITE_LOCK:
        atomic_write_json(DB,data,suffix='.db.tmp',trailing_newline=False)


def strict_json_loads(raw,max_depth=24,max_nodes=12000):
    """Reject ambiguous keys, non-finite numbers, and excessive nested input."""
    try:
        data=json.loads(raw,parse_constant=_reject_nonstandard_json,object_pairs_hook=_unique_json_object)
    except RecursionError as exc:
        raise ValueError('JSON 중첩 깊이 초과') from exc
    pending=[(data,0)]
    visited=0
    while pending:
        value,depth=pending.pop()
        visited+=1
        if depth>max_depth or visited>max_nodes:
            raise ValueError('JSON 구조 제한 초과')
        if isinstance(value,dict):
            if len(value)+len(pending)+visited>max_nodes:
                raise ValueError('JSON 구조 제한 초과')
            pending.extend((item,depth+1) for item in value.values())
        elif isinstance(value,list):
            if len(value)+len(pending)+visited>max_nodes:
                raise ValueError('JSON 구조 제한 초과')
            pending.extend((item,depth+1) for item in value)
        elif isinstance(value,float) and not math.isfinite(value):
            raise ValueError('표준 JSON 숫자만 허용됩니다.')
    return data

def load_market_db():
    fallback={'updated_at':None,'entries':{},'collection_status':'가격자료 없음'}
    data=load_json_file(MARKET_DB,fallback)
    return data if isinstance(data.get('entries'),dict) else fallback

def load_market_watch():
    return load_json_file(MARKET_WATCH,{'updated_at':None,'items':[],'collection_status':'추적자료 없음'})

def load_json_file(path, fallback):
    try:
        data=strict_json_loads(safe_read_text(path,max_bytes=MAX_SAFE_FILE_BYTES),max_depth=32,max_nodes=200000)
        if isinstance(fallback,dict) and not isinstance(data,dict):return fallback
        if isinstance(fallback,list) and not isinstance(data,list):return fallback
        return data
    except (OSError,ValueError,TypeError):return fallback

def save_json_atomic(path,data):
    # v75: serialize same-process atomic writes and update .bak only when the
    # current file is valid JSON. Copying a corrupted current file over a good
    # backup would destroy the last recovery point just before the new save.
    with DATA_WRITE_LOCK:
        path=os.fspath(path)
        if Path(path).is_symlink() or Path(path+'.bak').is_symlink():
            raise ValueError('심볼릭 링크 JSON 저장 경로는 허용되지 않습니다.')
        encoded=json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)
        if os.path.exists(path):
            try:
                old=strict_json_loads(safe_read_text(path,max_bytes=MAX_SAFE_FILE_BYTES),max_nodes=100000)
                atomic_write_text(path+'.bak',json.dumps(old,ensure_ascii=False,indent=2,allow_nan=False))
            except (OSError,ValueError,TypeError):
                # Preserve the previous known-good backup when current is damaged.
                pass
        atomic_write_text(path,encoded)

def ebay_grader_learning_status():
    candidates=load_json_file(EBAY_GRADER_CANDIDATES,{'version':1,'items':[],'counts':{'total':0}})
    verified=load_json_file(VERIFIED_CERTIFICATIONS,{'version':1,'certifications':[]})
    items=candidates.get('items',[]) if isinstance(candidates,dict) else []
    certs=verified.get('certifications',[]) if isinstance(verified,dict) else []
    by_company={company:0 for company in ('PSA','BGS','CGC','TAG','BRG')}
    by_game={game:0 for game in ('pokemon','onepiece','naruto','unknown')}
    for row in items if isinstance(items,list) else []:
        if not isinstance(row,dict):continue
        company=str(row.get('company','')).upper();game=str(row.get('game','')).lower()
        if company in by_company:by_company[company]+=1
        if game in by_game:by_game[game]+=1
        else:by_game['unknown']+=1
    verified_count=sum(1 for row in certs if isinstance(row,dict) and row.get('verified') is True) if isinstance(certs,list) else 0
    return {'ok':True,'engine':'v102-ebay-provider-photo-learning','api':'eBay Browse API',
            'oauth_configured':bool(os.environ.get('EBAY_OAUTH_TOKEN','').strip()),
            'candidate_count':len(items) if isinstance(items,list) else 0,'verified_certifications':verified_count,
            'by_company':by_company,'by_game':by_game,
            'policy':{'seller_label_is_official':False,'cert_verification_required':True,'slab_raw_isolated':True,'bot_bypass':False}}

def learning_store():
    data=load_json_file(LEARNING_STORE,{'version':2,'updated_at':None,'v99_validation':[],'v30_validation':[],'v11_validation':[]})
    updated=data.get('updated_at')
    clean={'version':2,'updated_at':updated[:120] if isinstance(updated,str) else None}
    for name in ('v99_validation','v30_validation','v11_validation'):
        rows=data.get(name,[])
        clean[name]=valid_learning_rows(rows) if isinstance(rows,list) else []
    # V99 safely imports legacy V30 once without deleting legacy history.
    if not clean['v99_validation'] and clean['v30_validation']:
        clean['v99_validation']=list(clean['v30_validation'])
    return clean

def valid_learning_rows(rows):
    if not isinstance(rows,list):
        raise ValueError('학습자료는 배열이어야 합니다.')
    dedup={};conflicts=set()
    for row in rows[-1000:]:
        if not isinstance(row,dict):continue
        company=str(row.get('company') or row.get('grader') or '').upper()
        if company not in ('PSA','BGS','CGC','TAG','BRG'):continue
        try:
            actual=float(row.get('actual'));pred=float(row.get('pred'));raw_pred=float(row.get('raw_pred',pred))
        except (TypeError,ValueError,OverflowError):continue
        if not (math.isfinite(actual) and math.isfinite(pred) and math.isfinite(raw_pred) and valid_actual_grade(company,actual) and 1<=pred<=10 and 1<=raw_pred<=10):continue
        item={'company':company,'grader':company,'actual':actual,'pred':pred,'raw_pred':raw_pred,'match':actual==pred}
        if isinstance(row.get('time'),str):item['time']=row['time'][:120]
        if isinstance(row.get('mode'),str) and row['mode'] in ('raw','slab'):item['mode']=row['mode']
        if isinstance(row.get('game'),str) and row['game'] in ('pokemon','onepiece','naruto'):item['game']=row['game']
        if isinstance(row.get('card_key'),str) and row['card_key'].strip():item['card_key']=row['card_key'].strip()[:180]
        certification=str(row.get('certification_id') or row.get('cert_no') or '').strip()
        if row.get('official_result') is True and re.fullmatch(r'[A-Za-z0-9._/-]{4,120}',certification):
            item['official_result']=True;item['certification_id']=certification;item['card_id']=str(row.get('card_id') or item.get('card_key') or certification)[:120]
        vision=row.get('vision')
        if isinstance(vision,dict):
            clean_vision={};valid_vision=True
            for key,low,high in (
                ('analysisConfidence',0,100),('frontCenter',0,50),('backCenter',0,50),
                ('surfaceRisk',0,100),('edgeRisk',0,100),('cornerRisk',0,100),('surfaceConfidence',0,100),
            ):
                raw=vision.get(key,0 if key in ('edgeRisk','cornerRisk') else None)
                try:value=float(raw)
                except (TypeError,ValueError,OverflowError):valid_vision=False;break
                if not math.isfinite(value) or not low<=value<=high:valid_vision=False;break
                clean_vision[key]=round(value,2)
            engine=vision.get('engine')
            if valid_vision:
                clean_vision['multiAngle']=vision.get('multiAngle') is True
                if isinstance(engine,str) and re.fullmatch(r'v\d{1,3}-[a-z0-9-]{1,80}',engine,re.I):clean_vision['engine']=engine
                item['vision']=clean_vision
        key=(company,item.get('certification_id')) if item.get('official_result') else (str(item.get('time',''))[:120],company,actual,raw_pred,item.get('card_key',''))
        if key in conflicts:continue
        previous=dedup.get(key)
        if item.get('official_result') and previous is not None and abs(float(previous['actual'])-actual)>1e-9:
            dedup.pop(key,None);conflicts.add(key);continue
        dedup[key]=item
    return list(dedup.values())[-500:]

def merge_learning_rows(existing,incoming):
    """Keep validated history from every device without letting cert conflicts train."""
    merged={};conflicts=set()
    for row in valid_learning_rows(existing)+valid_learning_rows(incoming):
        key=(row['company'],row.get('certification_id')) if row.get('official_result') else (str(row.get('time',''))[:120],row['company'],row['actual'],row.get('raw_pred',row['pred']),row.get('card_key',''))
        if key in conflicts:continue
        previous=merged.get(key)
        if row.get('official_result') and previous is not None and abs(float(previous['actual'])-float(row['actual']))>1e-9:
            merged.pop(key,None);conflicts.add(key);continue
        merged[key]=row
    return list(merged.values())[-500:]

def _sanitize_source_stats(data):
    out={'version':1,'sources':{},'updated_at':data.get('updated_at') if isinstance(data,dict) else None}
    rows=data.get('sources',{}) if isinstance(data,dict) else {}
    if not isinstance(rows,dict): rows={}
    for name,row in rows.items():
        if not isinstance(name,str) or not isinstance(row,dict): continue
        clean=dict(row)
        for k in ('runs','successes','failures','recovered_successes','clean_success_streak','consecutive_failures'):
            clean[k]=_safe_stat_int(row.get(k),0)
        for k in ('success_ewma_seconds','last_seconds','next_timeout_seconds'):
            if k in row: clean[k]=_safe_stat_float(row.get(k),0.0)
        pats=clean.get('error_patterns',{}) if isinstance(clean.get('error_patterns',{}),dict) else {}
        clean_pats={}
        for sig, rec in pats.items():
            if not isinstance(sig,str) or not isinstance(rec,dict): continue
            item=dict(rec); item['count']=_safe_stat_int(item.get('count'),0)
            clean_pats[sig]=item
        clean['error_patterns']=clean_pats
        out['sources'][name]=clean
    return out

def _valid_source_stats(data):
    return isinstance(data,dict) and isinstance(data.get('sources',{}),dict)

def _load_source_stats():
    # v67: 공식출처 timeout 학습값도 직전 정상본으로 복구한다.
    for candidate in (SOURCE_STATS,SOURCE_STATS_BAK):
        try:
            data=strict_json_loads(safe_read_text(candidate,max_bytes=MAX_SAFE_FILE_BYTES),max_depth=32,max_nodes=200000)
            if _valid_source_stats(data): return _sanitize_source_stats(data)
        except (OSError,ValueError,TypeError):
            continue
    return {'version':1,'sources':{}}

def _save_source_stats(data):
    data['version']=1
    data['updated_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
    with SOURCE_STATS_LOCK:
        if Path(SOURCE_STATS).is_symlink() or Path(SOURCE_STATS_BAK).is_symlink():
            raise ValueError('심볼릭 링크 출처 학습기록은 허용되지 않습니다.')
        if os.path.exists(SOURCE_STATS):
            try:
                old=strict_json_loads(safe_read_text(SOURCE_STATS,max_bytes=MAX_SAFE_FILE_BYTES),max_depth=32,max_nodes=200000)
                if _valid_source_stats(old):
                    atomic_write_json(SOURCE_STATS_BAK,old,suffix='.stats.bak.tmp',trailing_newline=False)
            except (OSError,ValueError,TypeError):
                pass
        atomic_write_json(SOURCE_STATS,data,suffix='.stats.tmp',trailing_newline=False)

def _source_timeout(row):
    successes=_safe_stat_int(row.get('successes'),0)
    streak=_safe_stat_int(row.get('clean_success_streak'),0)
    ewma=_safe_stat_float(row.get('success_ewma_seconds'),0.0)
    failures=_safe_stat_int(row.get('consecutive_failures'),0)
    if successes < 2 or ewma <= 0:return 300
    if failures:return min(300,max(90,int(ewma*(4+failures)+30)))
    # v65: 공식출처도 clean-success 단계가 충분히 쌓이기 전에는
    # 다음 timeout 단계 아래로 내려가지 않는다. 기존 min(cap, learned)는
    # 빠른 EWMA 하나만으로 곧바로 30초가 될 수 있었다.
    if streak>=12:stage_floor=30
    elif streak>=9:stage_floor=45
    elif streak>=7:stage_floor=60
    elif streak>=5:stage_floor=90
    elif streak>=4:stage_floor=120
    elif streak>=3:stage_floor=180
    else:stage_floor=300
    return min(300,max(stage_floor,max(30,int(ewma*3+15))))

def _source_transient_error(exc):
    text=(type(exc).__name__+' '+str(exc)).lower()
    return any(x in text for x in ('timeout','timed out','urlerror','connection','temporary','name resolution','429','502','503','remote end closed','reset by peer'))

def _source_access_restricted(exc):
    """Separate browser-usable anti-bot responses from broken source links."""
    return isinstance(exc,urllib.error.HTTPError) and exc.code in {401,403,405,406,409}

def _record_source_restriction(stats,name,seconds,http_status):
    with SOURCE_STATS_LOCK:
        row=stats.setdefault('sources',{}).setdefault(name,{'runs':0,'successes':0,'failures':0})
        row['runs']=int(row.get('runs',0))+1
        row['access_restrictions']=int(row.get('access_restrictions',0))+1
        row['last_seconds']=round(seconds,3)
        row['last_run']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        row['last_http_status']=int(http_status)
        row['clean_success_streak']=0
        row['consecutive_failures']=0
        row['next_timeout_seconds']=_source_timeout(row)

def _record_source_stat(stats,name,seconds,clean_success,error='',recovered=False):
    with SOURCE_STATS_LOCK:
        row=stats.setdefault('sources',{}).setdefault(name,{'runs':0,'successes':0,'failures':0})
        row['runs']=int(row.get('runs',0))+1
        row['last_seconds']=round(seconds,3)
        row['last_run']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        if clean_success and not recovered:
            row['successes']=int(row.get('successes',0))+1
            row['clean_success_streak']=int(row.get('clean_success_streak',0))+1
            row['consecutive_failures']=0
            old=float(row.get('success_ewma_seconds') or seconds)
            row['success_ewma_seconds']=round(old*.7+seconds*.3,3)
        else:
            row['clean_success_streak']=0
            row['consecutive_failures']=int(row.get('consecutive_failures',0))+1
            if recovered:row['recovered_successes']=int(row.get('recovered_successes',0))+1
            else:row['failures']=int(row.get('failures',0))+1
            if error:
                key=hashlib.sha1(re.sub(r'\d+','<n>',error.lower()).encode('utf-8','ignore')).hexdigest()[:12]
                pats=row.setdefault('error_patterns',{})
                rec=pats.setdefault(key,{'count':0,'sample':'','last_seen':None})
                rec['count']=int(rec.get('count',0))+1;rec['sample']=error[-400:];rec['last_seen']=row['last_run']
        row['next_timeout_seconds']=_source_timeout(row)

class OfficialSourceRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # v73: source fingerprints are network fetches too. Re-check every redirect
        # so an official site cannot redirect this local server to private/loopback IPs.
        newurl=urllib.parse.urljoin(req.full_url,newurl)
        require_public_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def fetch(url,timeout=300):
    require_public_https(url)
    req=Request(url,headers={'User-Agent':'TCG-Research-Updater/93'})
    opener=urllib.request.build_opener(OfficialSourceRedirect)
    with opener.open(req,timeout=max(5,min(300,int(timeout)))) as r:
        require_public_https(r.geturl())
        return r.read(500000).decode('utf-8','ignore')

def title(html):
    m=re.search(r'<title[^>]*>(.*?)</title>',html,re.I|re.S)
    return re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',m.group(1))).strip() if m else ''

def _collect_one_source(source,stats):
    """공식 출처 1건을 학습형 timeout + 복구 재시도로 수집한다.

    v57: 학습 timeout이 30초까지 내려간 뒤 첫 시도가 일시 오류로 끝나더라도
    두 번째 시도에 남은 5초만 주는 문제를 수정했다. 첫 시도는 학습 timeout을
    사용하고, 복구 시도는 최소 90초(또는 2배)로 확대하되 전체 예산은 300초다.
    """
    name,url,kind=source
    row=stats.get('sources',{}).get(name,{})
    learned_timeout=_source_timeout(row)
    total_budget=300
    started=time.monotonic();last_exc=None;attempt_timeouts=[]
    for attempt in (1,2):
        elapsed=time.monotonic()-started
        remain=max(0,total_budget-elapsed)
        if remain < 5:break
        requested = learned_timeout if attempt == 1 else min(300, max(90, learned_timeout * 2))
        attempt_timeout=max(5,min(int(requested),int(remain)))
        attempt_timeouts.append(attempt_timeout)
        try:
            html=fetch(url,attempt_timeout)
            seconds=time.monotonic()-started
            recovered=attempt>1
            _record_source_stat(stats,name,seconds,not recovered,'',recovered)
            return {'ok':True,'name':name,'url':url,'kind':kind,'html':html,'seconds':seconds,
                    'recovered':recovered,'learned_timeout_seconds':learned_timeout,
                    'attempt_timeouts':attempt_timeouts}
        except Exception as exc:
            last_exc=exc
            if _source_access_restricted(exc):
                seconds=time.monotonic()-started
                _record_source_restriction(stats,name,seconds,exc.code)
                return {'ok':False,'restricted':True,'name':name,'url':url,'kind':kind,
                        'http_status':exc.code,'seconds':seconds,
                        'learned_timeout_seconds':learned_timeout,'attempt_timeouts':attempt_timeouts}
            if attempt==1 and _source_transient_error(exc):
                time.sleep(min(2,max(0.1,remain*.02)))
                continue
            break
    seconds=time.monotonic()-started
    error=f'{type(last_exc).__name__}: {last_exc}' if last_exc else 'TimeoutError: source budget exhausted'
    _record_source_stat(stats,name,seconds,False,error,False)
    return {'ok':False,'name':name,'url':url,'kind':kind,'error':error,'seconds':seconds,
            'learned_timeout_seconds':learned_timeout,'attempt_timeouts':attempt_timeouts}

def collect():
    data=load_db();now=time.strftime('%Y-%m-%dT%H:%M:%S%z');pending=[]
    stats=_load_source_stats()
    is_android='com.termux' in os.environ.get('PREFIX','') or 'ANDROID_ROOT' in os.environ
    workers=2 if is_android else 4
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers,len(SOURCES))) as pool:
        futures=[pool.submit(_collect_one_source,src,stats) for src in SOURCES]
        for fut in concurrent.futures.as_completed(futures):
            try:results.append(fut.result())
            except Exception as exc:results.append({'ok':False,'name':'unknown','url':'','kind':'','error':f'{type(exc).__name__}: {exc}'})
    for result in results:
        name=result['name'];url=result['url'];kind=result['kind']
        if result.get('restricted'):
            old=data['sources'].get(name,{})
            preserved=dict(old) if isinstance(old,dict) else {}
            preserved.update({'url':url,'kind':kind,'checked_at':now,
                              'automation_access':'restricted',
                              'http_status':int(result.get('http_status') or 403)})
            preserved.setdefault('title',name)
            data['sources'][name]=preserved
            pending.append({'source':name,'url':url,'kind':kind,
                            'status':f"자동접근 제한 · 브라우저 링크 사용 가능 (HTTP {result.get('http_status')})",
                            'checked_at':now})
        elif result.get('ok'):
            html=result['html'];fp=hashlib.sha256(html.encode()).hexdigest();old=data['sources'].get(name)
            changed=bool(old) and old.get('fingerprint')!=fp
            data['sources'][name]={'url':url,'kind':kind,'title':title(html),'fingerprint':fp,'checked_at':now,
                                   'last_seconds':round(float(result.get('seconds') or 0),3),'recovered':bool(result.get('recovered'))}
            if changed or not old:
                pending.append({'source':name,'url':url,'kind':kind,'status':'변경 확인 필요' if changed else '최초 확인','checked_at':now})
        else:
            pending.append({'source':name,'url':url,'kind':kind,'status':'수집 오류','error':result.get('error','unknown'),'checked_at':now})
    _save_source_stats(stats)
    data['updated_at']=now;data['pending']=pending;save_db(data);return data

def update_cycle(trigger='manual', progress_callback=None):
    """Collect official source changes and refresh the verified release board safely."""
    with UPDATE_LOCK:
        started=time.time()
        data=collect()
        try:
            import auto_update_all
            report=auto_update_all.run_all(trigger, progress_callback=progress_callback)
            result_map={x['file']:x for x in report['results']}
            release_status=result_map['releases.json']['status']
            market_status=result_map['market_prices.json']['status']
            watch_status=result_map['market_watch.json']['status']
            promo_status=result_map['promo_events.json']['status']
            purchase_status=result_map['purchase_sources.json']['status']
            fx_status=result_map['exchange_rates.json']['status']
        except Exception as exc:
            message=f'통합 자동업데이트 오류: {type(exc).__name__}'
            release_status=market_status=watch_status=promo_status=purchase_status=fx_status=message
        data=load_db()
        # 통합 업데이트가 끝나면 사용자가 출처별로 다시 체크/승인하지 않아도 된다.
        # 수집 오류 항목만 대기목록에 남기고, 정상 변경감지는 자동 검증 반영 기록으로 이동한다.
        now_text=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        pending=list(data.get('pending',[]))
        normal=[x for x in pending if x.get('status')!='수집 오류']
        errors=[x for x in pending if x.get('status')=='수집 오류']
        applied=list(data.get('applied',[]))
        if normal:
            applied.extend({**x,'approved':True,'apply_mode':'통합 자동검증','applied_at':now_text} for x in normal)
            # 기록 파일이 끝없이 커지지 않도록 최근 300건만 보관한다.
            applied=applied[-300:]
        data['applied']=applied
        data['pending']=errors
        data['auto_update']={
            'enabled':True,'interval_hours':6,'trigger':trigger,
            'last_run':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(started)),
            'next_run':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(started+AUTO_INTERVAL_SECONDS)),
            'status':release_status,'market_status':market_status,'watch_status':watch_status,
            'promo_status':promo_status,'purchase_status':purchase_status,'fx_status':fx_status,
            'source_checked_count':len(SOURCES),
            'source_auto_applied_count':len(normal),
            'source_error_count':len(errors),
            'full_update':True,
        }
        save_db(data)
        return data

def _job_snapshot():
    with UPDATE_JOB_LOCK:
        return json.loads(json.dumps(UPDATE_JOB, ensure_ascii=False))

def _job_set(**changes):
    with UPDATE_JOB_LOCK:
        UPDATE_JOB.update(changes)
        return json.loads(json.dumps(UPDATE_JOB, ensure_ascii=False))

def _progress_update(current,total,label,filename,state,result=None):
    if state=='deferred-running':
        msg=f"[{current}/{total}] {label} · 시간초과 자료만 별도 복구수집 중"
    elif state=='deferred-done':
        recovered=bool(result and result.get('ok') and not result.get('remaining_collection_errors') and not result.get('error'))
        msg=f"[{current}/{total}] {label} · 별도 복구수집 {'완료' if recovered else '다음 실행 대기'}"
    else:
        msg=f"[{current}/{total}] {label} " + ("완료" if state=="done" else "확인 중")
    changes={'current':current,'total':total,'label':label,'file':filename,'message':msg}
    if result is not None:
        changes['last_result']={k:result.get(k) for k in ('name','file','ok','status','error','collection_errors') if k in result}
    _job_set(**changes)

def _background_full_update(job_id):
    try:
        _job_set(state='running',message='공식자료 6단계 업데이트 시작',current=0,total=6,error=None)
        data=update_cycle('manual', progress_callback=_progress_update)
        report=load_json_file(AUTO_REPORT,{'ok':False,'results':[]})
        issues=load_json_file(AUTO_ISSUES,{'issue_count':0,'issues':[]})
        deferred=report.get('deferred_timeout_recovery',{}) if isinstance(report,dict) else {}
        deferred_message=(f" · 시간초과 별도수집 {deferred.get('recovered_count',0)}/{deferred.get('attempted_count',0)}건 복구"
                          if deferred.get('attempted_count') else "")
        _job_set(state='completed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),current=6,total=6,
                 label='완료',message='전체 업데이트 완료'+deferred_message,report=report,issues=issues,auto_update=data.get('auto_update',{}))
    except Exception as exc:
        _job_set(state='failed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                 error=f'{type(exc).__name__}: {exc}',message='전체 업데이트 실행 오류')

def _background_retry_failed(job_id):
    try:
        import auto_update_all
        issues=load_json_file(AUTO_ISSUES,{'issues':[]})
        files=[]
        for row in issues.get('issues',[]):
            name=row.get('file')
            if name and name not in files: files.append(name)
        valid={x[2] for x in auto_update_all.JOBS}
        files=[x for x in files if x in valid]
        if not files:
            _job_set(state='completed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),current=0,total=0,
                     label='완료',message='재수집할 실패 항목이 없습니다.',report=load_json_file(AUTO_REPORT,{'ok':True,'results':[]}))
            return
        _job_set(state='running',retry_only=True,current=0,total=len(files),label='실패 항목 재수집',
                 message=f'실패 항목 {len(files)}개만 재수집 시작',error=None)
        # v60: 실패 항목 재수집도 정규/자동 업데이트와 같은 전역 잠금을 사용한다.
        # 그렇지 않으면 6시간 자동반영이나 수동 전체업데이트와 동시에 같은 JSON을
        # 수정해 학습값/백업/보고서가 서로 덮어써질 수 있다.
        _job_set(message='다른 업데이트와 충돌하지 않도록 안전 잠금 대기 중')
        with UPDATE_LOCK:
            report=auto_update_all.run_all('retry-failed', selected_files=files, progress_callback=_progress_update)
        deferred=report.get('deferred_timeout_recovery',{}) if isinstance(report,dict) else {}
        deferred_message=(f" · 시간초과 별도수집 {deferred.get('recovered_count',0)}/{deferred.get('attempted_count',0)}건 복구"
                          if deferred.get('attempted_count') else "")
        _job_set(state='completed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),current=len(files),total=len(files),
                 label='완료',message='실패 항목 재수집 완료'+deferred_message,report=report,issues=load_json_file(AUTO_ISSUES,{'issue_count':0,'issues':[]}))
    except Exception as exc:
        _job_set(state='failed',finished_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),error=f'{type(exc).__name__}: {exc}',message='실패 항목 재수집 오류')

def _start_background_update(retry_only=False):
    global LAST_MANUAL_UPDATE
    now=time.monotonic()
    with MANUAL_UPDATE_LOCK:
        current=_job_snapshot()
        if current.get('state') in ('queued','running'):
            return None, {'ok':False,'error':'이미 업데이트가 진행 중입니다','job':current}, 409
        wait=MANUAL_UPDATE_COOLDOWN_SECONDS-(now-LAST_MANUAL_UPDATE)
        if wait>0:
            return None, {'ok':False,'error':'업데이트 요청이 너무 빠릅니다','retry_after_seconds':round(wait,1)}, 429
        LAST_MANUAL_UPDATE=now
        job_id=f"{int(time.time())}-{os.getpid()}"
        _job_set(id=job_id,state='queued',trigger='retry-failed' if retry_only else 'manual',
                 started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'),finished_at=None,current=0,total=0 if retry_only else 6,
                 label='대기 중',file=None,message='업데이트 작업 준비 중',error=None,report=None,retry_only=retry_only)
    target=_background_retry_failed if retry_only else _background_full_update
    threading.Thread(target=target,args=(job_id,),daemon=True).start()
    return job_id, {'ok':True,'accepted':True,'job_id':job_id,'job':_job_snapshot()}, 202

def _write_precollect_status(data):
    atomic_write_json(PRECOLLECT_STATUS,data,suffix='.precollect.tmp',trailing_newline=False)


def _safe_stage_copy(src, dst):
    source=Path(src);destination=Path(dst)
    if source.is_symlink() or destination.is_symlink():
        raise ValueError('심볼릭 링크 사전수집 작업폴더는 허용되지 않습니다.')
    def ignore(path,names):
        skip={'__pycache__','.precollect_stage','.precollect_stage.tmp','.git'}
        for name in names:
            if name not in skip and not name.endswith('.pyc') and (Path(path)/name).is_symlink():
                raise ValueError('심볼릭 링크 사전수집 자료는 허용되지 않습니다.')
        return [n for n in names if n in skip or n.endswith('.pyc')]
    if os.path.exists(dst): shutil.rmtree(dst,ignore_errors=True)
    shutil.copytree(src,dst,ignore=ignore,symlinks=True)



def _run_precollect_process(cmd, *, cwd, timeout):
    """Run precollection in an isolated process group so timeout cannot leave child collectors running."""
    kwargs={"cwd":cwd,"stdout":subprocess.PIPE,"stderr":subprocess.PIPE,"text":True}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    proc=subprocess.Popen(cmd,**kwargs)
    try:
        out,err=proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10,check=False)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except Exception:
            try: proc.kill()
            except Exception: pass
        try: out,err=proc.communicate(timeout=5)
        except Exception: out,err="",""
        exc.stdout=out; exc.stderr=err
        raise
    return subprocess.CompletedProcess(cmd,proc.returncode,out,err)

def precollect_cycle(due_at):
    """6시간 반영 시점 30분 전에 별도 staging 폴더에서 자료를 미리 수집한다.

    실서비스 JSON은 이 단계에서 건드리지 않는다. 각 수집기는 v50 학습형 제한시간
    (최초 최대 5분, 안정 성공 시 30초까지 단축)을 그대로 사용한다.
    """
    tmp_stage=PRECOLLECT_STAGE+'.tmp'
    status={'state':'running','started_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'due_at':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(due_at)),
            'lead_minutes':30,'message':'6시간 반영 30분 전 사전 자료수집 시작'}
    _write_precollect_status(status)
    try:
        # v60: staging 스냅샷을 만드는 짧은 구간만 전역 업데이트 잠금으로 보호한다.
        # 수동/자동/실패항목 재수집 중간 상태를 복사하면 서로 다른 시점의 JSON과
        # 학습 메모리가 섞일 수 있으므로, 일관된 한 시점의 사본을 확보한 뒤 잠금을 해제한다.
        with UPDATE_LOCK:
            _safe_stage_copy(BASE,tmp_stage)
        # stage 내부에서 독립적으로 전체 수집. 개별 작업은 최대 5분이며 병렬 실행된다.
        proc=_run_precollect_process([os.sys.executable,'auto_update_all.py'],cwd=tmp_stage,timeout=25*60)
        report_path=os.path.join(tmp_stage,'auto_update_report.json')
        if proc.returncode!=0 or not os.path.exists(report_path):
            raise RuntimeError((proc.stderr or proc.stdout or '사전수집 결과 없음')[-1600:])
        report=load_json_file(report_path,{})
        if os.path.exists(PRECOLLECT_STAGE): shutil.rmtree(PRECOLLECT_STAGE,ignore_errors=True)
        os.replace(tmp_stage,PRECOLLECT_STAGE)
        status.update({'state':'ready','finished_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                       'ok':bool(report.get('ok')),'success_count':report.get('success_count',0),
                       'failure_count':report.get('failure_count',0),
                       'duration_seconds':report.get('duration_seconds'),
                       'message':'사전수집 완료 · 6시간 시점에 재확인 후 반영 예정'})
    except subprocess.TimeoutExpired:
        status.update({'state':'failed','finished_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                       'error':'사전수집 전체 제한시간 25분 초과','message':'사전수집 시간초과 · 정규 6시간 업데이트에서 보완'})
        shutil.rmtree(tmp_stage,ignore_errors=True)
    except Exception as exc:
        status.update({'state':'failed','finished_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                       'error':f'{type(exc).__name__}: {exc}','message':'사전수집 실패 · 정규 6시간 업데이트에서 보완'})
        shutil.rmtree(tmp_stage,ignore_errors=True)
    _write_precollect_status(status)
    return status


def _validated_stage_json(src,dst):
    """Confine a staged JSON file and validate its exact project-specific schema."""
    import auto_repair_engine
    import auto_update_all
    source=Path(src)
    destination=Path(dst)
    stage_root=Path(PRECOLLECT_STAGE)
    live_root=Path(BASE)
    if stage_root.is_symlink() or live_root.is_symlink() or source.is_symlink() or destination.is_symlink():
        raise ValueError('심볼릭 링크 사전수집 경로는 허용되지 않습니다.')
    if source.name!=destination.name or source.name not in auto_repair_engine.SAFE_JSON_FILES:
        raise ValueError('허용되지 않은 사전수집 JSON 파일입니다.')
    if source.resolve().parent!=stage_root.resolve() or destination.resolve().parent!=live_root.resolve():
        raise ValueError('사전수집 JSON 경로가 프로젝트 범위를 벗어났습니다.')
    data=strict_json_loads(safe_read_text(source,max_bytes=MAX_SAFE_FILE_BYTES),max_depth=32,max_nodes=200000)
    if not auto_repair_engine._valid_project_payload(source.name,data):
        raise ValueError('사전수집 JSON 구조 또는 필수값이 잘못되었습니다.')
    auto_update_all.validate_json(source.name,data)
    return data


def _atomic_copy_json(src,dst):
    data=_validated_stage_json(src,dst)
    atomic_write_json(dst,data,suffix='.stage.tmp')


def _changed_source_files(pending):
    files=set()
    for row in pending or []:
        if row.get('status')=='수집 오류':
            continue
        name=(row.get('source') or '')
        kind=(row.get('kind') or '')
        if kind=='행사' or '프로모' in name:
            files.add('promo_events.json')
        if any(k in name for k in ('포켓몬','원피스','나루토')):
            files.update(('releases.json','market_watch.json'))
    return files


def finalize_precollected_cycle(due_at):
    """정확한 6시간 시점에 사전수집 자료를 검증 반영하고 부족한 항목만 보완 수집한다."""
    with UPDATE_LOCK:
        started=time.time(); trigger='automatic-final'
        import auto_update_all
        staged_report={}; failed_files=set(); applied_files=[]
        stage_ready=False
        allowed_stage_files={job[2] for job in auto_update_all.JOBS}
        status=load_json_file(PRECOLLECT_STATUS,{})
        try:
            staged_report=load_json_file(os.path.join(PRECOLLECT_STAGE,'auto_update_report.json'),{})
            stage_rows=staged_report.get('results')
            stage_ready=status.get('state')=='ready' and isinstance(stage_rows,list) and bool(stage_rows)
            if stage_ready:
                names=[row.get('file') if isinstance(row,dict) else None for row in stage_rows]
                stage_ready=all(isinstance(name,str) and name in allowed_stage_files for name in names) and len(names)==len(set(names))
        except (OSError,TypeError,ValueError):
            stage_ready=False

        if stage_ready:
            good_root=os.path.join(BASE,'.tcg_last_good'); os.makedirs(good_root,exist_ok=True)
            for row in staged_report.get('results',[]):
                fn=row.get('file')
                partial=bool(row.get('collection_errors'))
                if row.get('ok') and not partial and fn:
                    src=os.path.join(PRECOLLECT_STAGE,fn); dst=os.path.join(BASE,fn)
                    if os.path.exists(src):
                        try:
                            _validated_stage_json(src,dst)
                            if os.path.exists(dst) and not os.path.islink(dst):
                                try:
                                    previous=strict_json_loads(safe_read_text(dst,max_bytes=MAX_SAFE_FILE_BYTES),max_depth=32,max_nodes=200000)
                                    valid_previous=auto_update_all.auto_repair_engine._valid_project_payload(fn,previous)
                                    if valid_previous:auto_update_all.validate_json(fn,previous)
                                except (TypeError,ValueError):
                                    valid_previous=False
                                if valid_previous:
                                    atomic_write_json(os.path.join(good_root,fn),previous)
                            _atomic_copy_json(src,dst); applied_files.append(fn)
                        except (OSError,TypeError,ValueError):
                            failed_files.add(fn)
                    else:
                        failed_files.add(fn)
                elif fn:
                    failed_files.add(fn)
            # 사전수집에서 학습한 성공시간/오류패턴도 다음 실행에 이어서 사용한다.
            for fn in ('adaptive_collection_stats.json','auto_repair_memory.json','supplementary_candidates.json','purchase_signals.json'):
                src=os.path.join(PRECOLLECT_STAGE,fn); dst=os.path.join(BASE,fn)
                if os.path.exists(src):
                    try:_atomic_copy_json(src,dst)
                    except Exception:pass
        else:
            failed_files.update(allowed_stage_files)

        # 6시간 시점의 공식 출처를 다시 확인하여 30분 사이에 바뀐 자료를 보완 대상으로 추가한다.
        data=collect()
        failed_files.update(_changed_source_files(data.get('pending',[])))

        supplement_report=None
        if failed_files:
            supplement_report=auto_update_all.run_all('automatic-supplement',selected_files=sorted(failed_files))
        else:
            # 사전수집 전체 성공이면 stage 보고서를 정규 보고서로 승격한다.
            report=dict(staged_report); report['trigger']='automatic-final-from-precollect'
            report['precollect_applied_files']=applied_files
            report['finished_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
            save_json_atomic(AUTO_REPORT,report)
            # stage issues도 반영
            src=os.path.join(PRECOLLECT_STAGE,'auto_update_issues.json')
            if os.path.exists(src):
                try:_atomic_copy_json(src,AUTO_ISSUES)
                except Exception:pass

        # 통합 결과를 live DB 상태에 기록
        final_report=supplement_report or load_json_file(AUTO_REPORT,{'results':[]})
        result_map={x.get('file'):x for x in final_report.get('results',[])}
        def st(fn): return result_map.get(fn,{}).get('status','사전수집 검증 반영')
        data=load_db(); now_text=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        pending=list(data.get('pending',[])); normal=[x for x in pending if x.get('status')!='수집 오류']; errors=[x for x in pending if x.get('status')=='수집 오류']
        applied=list(data.get('applied',[]))
        if normal:
            applied.extend({**x,'approved':True,'apply_mode':'30분 사전수집 + 6시간 최종검증','applied_at':now_text} for x in normal)
            applied=applied[-300:]
        next_due=due_at+AUTO_INTERVAL_SECONDS
        data['applied']=applied; data['pending']=errors
        data['auto_update']={'enabled':True,'interval_hours':6,'precollect_lead_minutes':30,'trigger':trigger,
            'last_run':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(started)),
            'next_run':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(next_due)),
            'next_precollect':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(next_due-PRECOLLECT_LEAD_SECONDS)),
            'status':st('releases.json'),'market_status':st('market_prices.json'),'watch_status':st('market_watch.json'),
            'promo_status':st('promo_events.json'),'purchase_status':st('purchase_sources.json'),'fx_status':st('exchange_rates.json'),
            'source_checked_count':len(SOURCES),'source_auto_applied_count':len(normal),'source_error_count':len(errors),
            'precollect_state':status.get('state'),'precollect_applied_count':len(applied_files),
            'supplement_file_count':len(failed_files),'full_update':True}
        save_db(data)
        return data


def auto_update_loop():
    # 시작 직후 한 번은 전체 검증을 수행해 기준시각을 만든다.
    try:
        first=update_cycle('automatic-startup')
        last_text=first.get('auto_update',{}).get('last_run')
    except Exception:
        last_text=None
    now=time.time()
    due=now+AUTO_INTERVAL_SECONDS
    while True:
        pre_at=due-PRECOLLECT_LEAD_SECONDS
        delay=max(0,pre_at-time.time())
        if delay: time.sleep(delay)
        try: precollect_cycle(due)
        except Exception: pass
        delay=max(0,due-time.time())
        if delay: time.sleep(delay)
        try: finalize_precollected_cycle(due)
        except Exception:
            # stage 반영에 실패하면 기존 정규 전체업데이트로 안전하게 폴백한다.
            try: update_cycle('automatic-fallback')
            except Exception: pass
        due += AUTO_INTERVAL_SECONDS

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        # Keep the public document root bound to this installation even when
        # imported or launched from a different current working directory.
        super().__init__(*args, directory=BASE if directory is None else directory, **kwargs)

    def setup(self):
        super().setup()
        # v74: bound slow/incomplete request bodies so remote clients cannot keep
        # unlimited handler threads blocked forever (slowloris-style exhaustion).
        self.connection.settimeout(env_int('TCG_HTTP_REQUEST_TIMEOUT',15,5,60))
    def log_message(self, fmt, *args):
        pass
    def end_headers(self):
        # Browser hardening without breaking the existing inline/offline UI.
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Cross-Origin-Opener-Policy','same-origin')
        self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Content-Security-Policy',
                         "default-src 'self' https: data: blob:; "
                         "script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' https: data: blob:; connect-src 'self' https:; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Permissions-Policy','camera=(self), microphone=(), geolocation=(self)')
        origin=self.headers.get('Origin','')
        if origin==TRUSTED_PAGES_ORIGIN:
            self.send_header('Access-Control-Allow-Origin',origin)
            self.send_header('Vary','Origin')
            if self.headers.get('Access-Control-Request-Private-Network','').lower()=='true':
                self.send_header('Access-Control-Allow-Private-Network','true')
        super().end_headers()
    def do_OPTIONS(self):
        if not self._request_host_allowed() or self.headers.get('Origin','')!=TRUSTED_PAGES_ORIGIN:
            self.send_response(403);self.end_headers();return
        self.send_response(204)
        self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers','Content-Type')
        self.end_headers()
    def json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        if self.command!='HEAD':self.wfile.write(body)
    def _request_host_allowed(self):
        """Reject DNS-rebinding/forged public Host values while keeping LAN access."""
        hosts=self.headers.get_all('Host') or []
        if len(hosts)!=1:
            return False
        raw=hosts[0]
        if not raw or raw.strip()!=raw or any(char in raw for char in ('/','\\','@',',','#','?')):
            return False
        try:
            parsed=urlparse('http://'+raw)
            hostname=(parsed.hostname or '').rstrip('.').lower()
            port=parsed.port
        except (TypeError,ValueError):
            return False
        if not hostname or (port is not None and port!=self.server.server_address[1]):
            return False
        if hostname=='localhost':
            return True
        try:
            address=ipaddress.ip_address(hostname)
        except ValueError:
            return False
        if address.is_loopback:
            return True
        if isinstance(address,ipaddress.IPv4Address):
            return any(address in network for network in (
                ipaddress.ip_network('10.0.0.0/8'),
                ipaddress.ip_network('172.16.0.0/12'),
                ipaddress.ip_network('192.168.0.0/16'),
            ))
        return address in ipaddress.ip_network('fc00::/7')
    def _require_request_host(self):
        if self._request_host_allowed():
            return True
        self.json({'ok':False,'error':'허용되지 않은 접속 주소'},421)
        return False
    def _origin_allowed(self):
        if not self._request_host_allowed():
            return False
        origin=self.headers.get('Origin','')
        if not origin:
            # Non-browser mutation requests are accepted only from this machine.
            return self.client_address[0] in ('127.0.0.1','::1')
        if origin==TRUSTED_PAGES_ORIGIN:
            return True
        try:
            parsed=urlparse(origin)
            host_header=self.headers.get('Host','')
            return parsed.scheme=='http' and not parsed.username and not parsed.password and parsed.netloc==host_header
        except (TypeError,ValueError):
            return False
    def _require_mutation_origin(self):
        if self._origin_allowed():
            return True
        self.json({'ok':False,'error':'허용되지 않은 요청 출처'},403)
        return False
    def _read_json_body(self,max_bytes=1000000):
        content_type=self.headers.get('Content-Type','').split(';',1)[0].strip().lower()
        if content_type!='application/json':
            raise ValueError('JSON Content-Type 필요')
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Transfer-Encoding 요청 차단')
        lengths=self.headers.get_all('Content-Length') or []
        if len(lengths)!=1:
            raise ValueError('Content-Length 형식 오류')
        raw_size=lengths[0]
        if not raw_size.isdecimal():
            raise ValueError('Content-Length 형식 오류')
        try:
            size=int(raw_size)
        except (TypeError,ValueError,OverflowError):
            raise ValueError('Content-Length 형식 오류')
        if size<=0 or size>max_bytes:
            raise ValueError('요청 크기 오류')
        raw=self.rfile.read(size)
        if len(raw)!=size:
            raise ValueError('요청 본문 길이 오류')
        payload=strict_json_loads(raw.decode('utf-8'))
        if not isinstance(payload,dict):
            raise ValueError('JSON 객체 형식 필요')
        return payload

    def _search_origin_allowed(self):
        origin=self.headers.get('Origin','')
        if origin and not self._origin_allowed():
            return False
        return self.headers.get('Sec-Fetch-Site','').strip().lower()!='cross-site'

    def _allow_live_search(self,region):
        now=time.monotonic()
        key=(self.client_address[0],region)
        with SEARCH_LIMIT_LOCK:
            if len(SEARCH_LIMIT_BUCKETS)>1024:
                stale=[item for item,times in SEARCH_LIMIT_BUCKETS.items()
                       if not times or now-times[-1]>=SEARCH_LIMIT_WINDOW_SECONDS]
                for item in stale:SEARCH_LIMIT_BUCKETS.pop(item,None)
                while len(SEARCH_LIMIT_BUCKETS)>1024:
                    SEARCH_LIMIT_BUCKETS.pop(next(iter(SEARCH_LIMIT_BUCKETS)))
            recent=[moment for moment in SEARCH_LIMIT_BUCKETS.get(key,[])
                    if now-moment<SEARCH_LIMIT_WINDOW_SECONDS]
            if len(recent)>=SEARCH_LIMIT_REQUESTS:
                SEARCH_LIMIT_BUCKETS[key]=recent
                return False,max(0.1,SEARCH_LIMIT_WINDOW_SECONDS-(now-recent[0]))
            recent.append(now)
            SEARCH_LIMIT_BUCKETS[key]=recent
            return True,0.0
    def _manual_update(self):
        global LAST_MANUAL_UPDATE
        if not self._require_mutation_origin():
            return
        now=time.monotonic()
        with MANUAL_UPDATE_LOCK:
            wait=MANUAL_UPDATE_COOLDOWN_SECONDS-(now-LAST_MANUAL_UPDATE)
            if wait>0:
                return self.json({'ok':False,'error':'업데이트 요청이 너무 빠릅니다','retry_after_seconds':round(wait,1)},429)
            LAST_MANUAL_UPDATE=now
        try:
            data=update_cycle('manual')
            report=load_json_file(AUTO_REPORT,{'ok':False,'results':[]})
            issues=load_json_file(AUTO_ISSUES,{'issue_count':0,'issues':[]})
            return self.json({
                'ok':bool(report.get('ok',True)),
                'auto_update':data.get('auto_update',{}),
                'updated_at':data.get('updated_at'),
                'report':report,
                'issues':issues,
                'message':'최신자료 확인 → 변경 비교 → 검증 → 정상자료 전체 반영을 한 번에 완료했습니다.'
            })
        except Exception:
            return self.json({'ok':False,'error':'통합 업데이트 실행 오류'},500)
    def _safe_static(self,path):
        name=path.lstrip('/') or 'index.html'
        if '/' in name or '\\' in name or name.startswith('.') or name not in PUBLIC_STATIC_FILES:
            return False
        target=Path(self.directory)/name
        try:
            return not target.is_symlink() and not target.parent.is_symlink() and target.is_file()
        except (OSError,ValueError):
            return False
    def send_head(self):
        """Serve only an opened regular-file descriptor; never follow asset symlinks."""
        path=urlparse(self.path).path
        if not self._safe_static(path):
            self.json({'ok':False,'error':'공개되지 않은 파일'},404)
            return None
        target=Path(self.directory)/(path.lstrip('/') or 'index.html')
        try:
            handle=open_safe_binary(target,max_bytes=MAX_SAFE_FILE_BYTES)
            metadata=os.fstat(handle.fileno())
        except (OSError,ValueError):
            self.json({'ok':False,'error':'공개 파일을 안전하게 열 수 없습니다.'},404)
            return None
        try:
            self.send_response(200)
            self.send_header('Content-type',self.guess_type(str(target)))
            self.send_header('Content-Length',str(metadata.st_size))
            self.send_header('Last-Modified',self.date_time_string(metadata.st_mtime))
            self.end_headers()
            return handle
        except BaseException:
            handle.close()
            raise
    def do_HEAD(self):
        # SimpleHTTPRequestHandler's inherited HEAD otherwise bypasses do_GET's
        # Host validation and public-file allowlist, leaking private file metadata.
        if not self._require_request_host():
            return
        path=urlparse(self.path).path
        if path.startswith('/api/'):
            return self.json({'ok':False,'error':'GET 요청만 허용'},405)
        if not self._safe_static(path):
            return self.json({'ok':False,'error':'공개되지 않은 파일'},404)
        return super().do_HEAD()
    def do_GET(self):
        if not self._require_request_host():
            return
        parsed=urlparse(self.path);path=parsed.path
        if path=='/api/health':
            return self.json({'ok':True,'service':SERVICE_NAME,'platform':PLATFORM,'port':PORT,'api_version':2,'integrated_version':INTEGRATED_VERSION,'learning_version':'v102-ebay-provider-photo-learning'})
        if path=='/api/status': return self.json(load_db())
        if path=='/api/auto-status': return self.json(load_db().get('auto_update',{}))
        if path=='/api/update-job': return self.json({'ok':True,'job':_job_snapshot()})
        if path=='/api/update-report': return self.json(load_json_file(AUTO_REPORT,{'ok':False,'results':[]}))
        if path=='/api/update-issues': return self.json(load_json_file(AUTO_ISSUES,{'issue_count':0,'issues':[]}))
        if path in {'/api/repair-memory','/api/error-learning-summary'}:
            try:
                import auto_repair_engine as repair
                return self.json(repair.public_error_learning_summary(repair.load_memory(Path(AUTO_MEMORY))))
            except (OSError,ValueError,TypeError):
                return self.json({'ok':False,'error':'오류학습 요약을 읽지 못했습니다.'},500)
        if path=='/api/verification-cycles': return self.json(load_json_file(os.path.join(BASE,'verification_cycles.json'),{'completed_passes':0,'successful_passes':0,'results':[]}))
        if path=='/api/learning-store': return self.json(learning_store())
        if path=='/api/vision-self-learning': return self.json(load_json_file(VISION_SELF_LEARNING_REPORT,{'version':1,'engine':'v101-isolated-self-learning-calibration','status':'not-run'}))
        if path=='/api/ebay-grader-learning': return self.json(ebay_grader_learning_status())
        if path=='/api/card-identity-learning':
            try:
                from card_identity_recognition import learning_payload
                data=learning_payload();rows=data.get('confirmed',[])
                return self.json({'ok':True,'confirmed':len(rows),'conflicts':len(data.get('conflicts',[])),
                                  'identities':len({(r.get('game'),r.get('card_name'),r.get('card_number')) for r in rows if isinstance(r,dict)}),
                                  'confirmed_only':True,'auto_prediction_learning':False})
            except ImportError:
                return self.json({'ok':False,'error':'카드 OCR 구성요소가 설치되지 않았습니다.','ocr_error':'dependency_not_installed'},503)
            except (OSError,ValueError,TypeError,json.JSONDecodeError):
                return self.json({'ok':False,'error':'카드 인식 학습상태 오류'},500)
        if path=='/api/market-watch': return self.json(load_market_watch())
        if path=='/api/validation':
            return self.json({'ok':True,'mode':'pre-grade','probability_claim':False,
                              'companies':['PSA','BGS','CGC','TAG','BRG'],
                              'verified_exact_grade_prices_only':True,'arbitrary_code_execution':False})
        if path=='/api/feature-audit':
            try:
                from feature_contract import audit_feature_contract
                return self.json(audit_feature_contract(BASE))
            except (OSError,ValueError,TypeError,json.JSONDecodeError,RecursionError):
                return self.json({'ok':False,'error':'기능 계약 검사를 완료하지 못했습니다.'},500)
        if path=='/api/scenario-learning-summary':
            try:
                import auto_repair_engine as repair
                return self.json(repair.scenario_learning_summary())
            except (OSError,ValueError,TypeError,json.JSONDecodeError,RecursionError):
                return self.json({'ok':False,'error':'시나리오 학습상태를 읽지 못했습니다.'},500)
        if path=='/api/grading-standards':
            from card_grading_valuation import COMPANIES,TAG_SCALE
            return self.json({'ok':True,'companies':list(COMPANIES),'official_grade':False,
                              'psa_10_centering':{'front':'55/45','back':'75/25'},
                              'tag_scale':[{'minimum_score':score,'grade':grade,'condition':condition}
                                           for score,grade,condition in TAG_SCALE],
                              'tag_grade_9_5_exists':False,'brg_unpublished_thresholds_invented':False})
        if path=='/api/platform-diagnostics':
            try:
                from cross_platform_agent import CrossPlatformSelfHealingEngine
                return self.json({'ok':True, **CrossPlatformSelfHealingEngine().diagnostics()})
            except Exception as exc:
                return self.json({'ok':False,'error':'플랫폼 진단 오류'},500)
        if path=='/api/web-candidates':
            return self.json(load_json_file(os.path.join(BASE,'web_discovery_candidates.json'),{'updated_at':None,'queries':[],'notice':'아직 수집 전'}))
        if path=='/api/purchase-signals':
            return self.json(load_json_file(os.path.join(BASE,'purchase_signals.json'),{'version':1,'updated_at':None,'items':[]}))
        if path=='/api/grading-proxy-costs':
            qs=parse_qs(parsed.query)
            force=qs.get('force',['0'])[0]=='1'
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처','providers':[]},403)
            try:
                from grading_proxy_costs import get_proxy_costs
                return self.json(get_proxy_costs(force=force))
            except Exception:
                return self.json({'ok':False,'error':'등급대행 비용 엔진 오류','providers':[]},500)
        if path=='/api/grading-costs':
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처'},403)
            try:
                from grading_costs_live import get_grading_costs
                return self.json(get_grading_costs())
            except Exception:
                return self.json({'ok':False,'error':'감정비 조회 엔진 오류'},500)
        if path=='/api/inventory-lookup':
            qs=parse_qs(parsed.query)
            q=qs.get('q',[''])[0].strip(); game=qs.get('game',[''])[0].strip()
            if len(q)>120 or len(game)>40:
                return self.json({'ok':False,'error':'재고조회 조건 오류','items':[]},400)
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처','items':[]},403)
            try:
                from inventory_lookup import get_inventory_options
                return self.json(get_inventory_options(q,game))
            except Exception:
                return self.json({'ok':False,'error':'공식 재고조회 엔진 오류','items':[]},500)
        if path=='/api/purchase-live-search':
            qs=parse_qs(parsed.query)
            q=qs.get('q',[''])[0].strip(); region=qs.get('region',['KR'])[0].upper(); game=qs.get('game',[''])[0]
            if not q or len(q)>120 or region not in ('KR','JP','US') or game not in ('Pokemon','ONE PIECE','NARUTO'):
                return self.json({'ok':False,'error':'구매 검색 조건 오류','items':[]},400)
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 구매검색 요청 출처','items':[]},403)
            allowed,retry_after=self._allow_live_search(region)
            if not allowed:
                return self.json({'ok':False,'error':'구매검색 요청이 너무 빠릅니다',
                                  'retry_after_seconds':round(retry_after,1),'items':[]},429)
            try:
                from purchase_intelligence import search_web_signals
                return self.json(search_web_signals(q,region,game))
            except Exception:
                return self.json({'ok':False,'error':'구매 신호 탐색 엔진 오류','items':[]},500)
        if path=='/api/market-price':
            qs=parse_qs(parsed.query); key=qs.get('key',[''])[0]
            if not key or len(key)>160:return self.json({'ok':False,'error':'가격 키 오류'},400)
            db=load_market_db(); entry=db.get('entries',{}).get(key)
            return self.json({'ok':True,'found':bool(entry),'key':key,'updated_at':db.get('updated_at'),'collection_status':db.get('collection_status'),'price':entry})
        # Mutating updates are POST-only. This prevents accidental/cross-site GET execution.
        if path in ('/api/update','/run-auto-update','/api/run-auto-update'):
            return self.json({'ok':False,'error':'POST 요청만 허용'},405)
        if not self._safe_static(path):
            return self.json({'ok':False,'error':'공개되지 않은 파일'},404)
        return super().do_GET()
    def do_POST(self):
        if not self._require_request_host():
            return
        post_path=self.path.split('?',1)[0]
        # v72: every state-changing endpoint must pass the same Origin/loopback guard.
        # Previously the background update endpoints bypassed this check, allowing a
        # cross-site POST to start expensive collection even though the response was
        # unreadable by the attacking page.
        if post_path in ('/run-auto-update','/api/run-auto-update','/api/retry-failed'):
            if not self._require_mutation_origin():
                return
            job_id,payload,status=_start_background_update(post_path=='/api/retry-failed')
            return self.json(payload,status)
        if post_path=='/api/update':
            return self._manual_update()
        if post_path=='/api/recognize-card':
            if not self._require_mutation_origin():
                return
            try:
                from card_identity_recognition import recognize
                return self.json(recognize(self._read_json_body(8500000)))
            except ImportError:
                return self.json({'ok':False,'error':'카드 OCR 구성요소가 설치되지 않았습니다.','ocr_error':'dependency_not_installed'},503)
            except (ValueError,TypeError,OverflowError,UnicodeError,RecursionError,OSError):
                return self.json({'ok':False,'error':'카드명·번호 인식 입력 오류'},400)
        if post_path=='/api/confirm-card-identity':
            if not self._require_mutation_origin():
                return
            try:
                from card_identity_recognition import save_confirmation
                with DATA_WRITE_LOCK:
                    result=save_confirmation(self._read_json_body(12000))
                return self.json(result,200 if result.get('ok') else 409)
            except ImportError:
                return self.json({'ok':False,'error':'카드 인식 학습 구성요소가 설치되지 않았습니다.','ocr_error':'dependency_not_installed'},503)
            except (ValueError,TypeError,OverflowError,UnicodeError,RecursionError,OSError):
                return self.json({'ok':False,'error':'카드 인식 확인자료 형식 오류'},400)
        if post_path=='/api/grade-card':
            if not self._require_mutation_origin():
                return
            try:
                from card_grading_valuation import MAX_CARD_NAME,verified_card_valuation
                incoming=self._read_json_body(24000)
                values=incoming.get('cv_data')
                if not isinstance(values,dict) or len(values)>24:
                    raise ValueError('카드 분석자료 형식 오류')
                market_key=incoming.get('market_key','')
                if not isinstance(market_key,str) or len(market_key)>160:
                    raise ValueError('카드 시세 키 형식 오류')
                database=load_market_db()
                profile=database.get('graded_prices',{}).get(market_key,{}) if market_key else {}
                if not isinstance(profile,dict):
                    raise ValueError('카드 등급별 가격자료 형식 오류')
                if market_key and not profile:
                    raise ValueError('확인된 카드 등급별 시세자료 없음')
                grade_prices=profile.get('grade_prices_krw',{}) if profile else incoming.get('grade_prices_krw',{})
                if not isinstance(grade_prices,dict) or len(grade_prices)>5 or any(
                    not isinstance(row,dict) or len(row)>24 for row in grade_prices.values()
                ):
                    raise ValueError('업체별 등급가격 형식 오류')
                entry=database.get('entries',{}).get(market_key,{}) if market_key else {}
                card_name=incoming.get('card_name') or entry.get('card_name') or market_key or '사진 분석 카드'
                if not isinstance(card_name,str) or len(card_name)>MAX_CARD_NAME:
                    raise ValueError('카드명 형식 오류')
                exchange=load_json_file(os.path.join(BASE,'exchange_rates.json'),{'rates':{}})
                exchange_rate=exchange.get('rates',{}).get('USD_KRW',1350.0)
                result=verified_card_valuation(
                    card_name,values,grade_prices,
                    raw_krw=profile.get('raw_krw',incoming.get('raw_krw',0)),
                    exchange_rate=exchange_rate,
                    price_source='exact_company_grade_observation' if profile else 'user_provided_exact_grade',
                )
                return self.json(result)
            except (ValueError,TypeError,OverflowError,UnicodeError,RecursionError):
                return self.json({'ok':False,'error':'카드 등급·시세 입력 형식 오류'},400)
        if post_path=='/api/learning-store':
            if not self._require_mutation_origin(): return
            try:
                incoming=self._read_json_body(1000000)
                with DATA_WRITE_LOCK:
                    previous=learning_store()
                    v99=merge_learning_rows(previous.get('v99_validation',[]),incoming.get('v99_validation',[]))
                    v30=merge_learning_rows(previous.get('v30_validation',[]),incoming.get('v30_validation',[]))
                    # Do not re-overlay legacy V30 on current V99. learning_store() imports
                    # V30 only when V99 is empty, so modern certified rows stay authoritative.
                    v11=merge_learning_rows(previous.get('v11_validation',[]),incoming.get('v11_validation',[]))
                    data={'version':2,'updated_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'v99_validation':v99,'v30_validation':v30,'v11_validation':v11}
                    save_json_atomic(LEARNING_STORE,data)
                    from vision_calibration import train_file
                    calibration=train_file(Path(LEARNING_STORE),Path(BASE)/'vision_calibration.json')
                    from grading_accuracy_v99 import sanitize_rows as v99_sanitize, train_company_calibration
                    global_models=train_company_calibration(v99_sanitize(data))
                enabled=sum(row.get('enabled') is True for row in calibration.get('profiles',{}).values())
                return self.json({'ok':True,'saved':len(v99)+len(v11),'updated_at':data['updated_at'],
                                  'v99_validation':len(v99),'calibration_profiles':len(calibration.get('profiles',{})),
                                  'enabled_calibration_profiles':enabled,'v99_models':global_models})
            except (ValueError,TypeError,json.JSONDecodeError,TimeoutError,OSError,RecursionError):return self.json({'ok':False,'error':'학습자료 형식 오류'},400)
        if post_path!='/api/apply': return self.json({'ok':False,'error':'없는 API'},404)
        if not self._require_mutation_origin(): return
        # v73: protect the complete read-modify-write transaction. Locking only
        # save_db() would still allow two /api/apply requests to both read the
        # same pending set and lose one request's update.
        with DB_MUTATION_LOCK:
            data=load_db(); pending=data.get('pending',[]); now=time.strftime('%Y-%m-%dT%H:%M:%S%z')
            valid=[x for x in pending if x.get('status')!='수집 오류']
            errors=[x for x in pending if x.get('status')=='수집 오류']
            if not valid:
                return self.json({'ok':True,'approved_count':0,'error_count':len(errors),'updated_at':now,'catalog_changed':False,'message':'승인 기록으로 저장할 정상 변경사항이 없습니다.'})
            if os.path.exists(DB):
                try:
                    previous=safe_read_bytes(DB,max_bytes=MAX_SAFE_FILE_BYTES)
                    atomic_write_bytes(DB+'.bak',previous,suffix='.apply.bak.tmp')
                except (OSError,ValueError): pass
            data['applied']=(data.get('applied',[])+[{**x,'applied_at':now} for x in valid])[-1000:]
            data['pending']=errors
            save_db(data)
            return self.json({'ok':True,'approved_count':len(valid),'error_count':len(errors),'updated_at':now,'catalog_changed':False,'message':'검토 승인 기록을 저장했습니다. 정적 목록 파일은 자동 변경하지 않습니다.'})



def local_startup_housekeeping():
    """Network-free startup repair before the HTTP server starts.

    Keeps stale promo/movie records from surviving across midnight when the
    device was offline at the scheduled cleanup time. This never fetches the
    network and only removes records whose effective expiry is strictly before
    today. A backup is written before any mutation.
    """
    promo_path=os.path.join(BASE,'promo_events.json')
    try:
        import update_promo_events as _promo
        if not os.path.exists(promo_path):
            return {'ok':True,'removed':0,'reason':'missing'}
        raw=load_json_file(promo_path, {'items':[]})
        items=raw.get('items',[]) if isinstance(raw,dict) else []
        repaired=[_promo.normalize_event_dates(x) for x in items if isinstance(x,dict)]
        kept,removed=_promo.purge_expired(repaired)
        changed=(len(kept)!=len(items) or repaired!=items)
        if changed:
            try:
                previous=safe_read_bytes(promo_path,max_bytes=MAX_SAFE_FILE_BYTES)
                atomic_write_bytes(promo_path+'.startup.bak',previous,suffix='.startup.bak.tmp')
            except (OSError,ValueError):
                pass
            raw['items']=kept
            raw['startup_cleanup_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
            raw['startup_expired_removed']=len(removed)
            raw['startup_expired_names']=[x.get('name_ko','이름 없음') for x in removed][:50]
            save_json_atomic(promo_path,raw)
        return {'ok':True,'removed':len(removed),'changed':changed}
    except Exception as exc:
        # Startup cleanup must never prevent the verified server from starting.
        return {'ok':False,'removed':0,'error':type(exc).__name__}

class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """브라우저가 응답 중 연결을 닫을 때 생기는 정상적인 reset/broken-pipe 로그를 억제한다."""
    def handle_error(self, request, client_address):
        exc=sys.exc_info()[1]
        if isinstance(exc,(BrokenPipeError,ConnectionResetError)):
            return
        return super().handle_error(request,client_address)

if __name__=='__main__':
    os.chdir(BASE)
    housekeeping=local_startup_housekeeping()
    if housekeeping.get('removed'):
        print(f"시작 전 만료정보 자동정리: {housekeeping['removed']}건",flush=True)
    elif not housekeeping.get('ok',True):
        print(f"시작 전 정리 경고: {housekeeping.get('error','unknown')} · 기존 자료 유지",flush=True)
    try:
        server=QuietThreadingHTTPServer(('0.0.0.0',PORT),Handler)
    except OSError as exc:
        raise SystemExit(f'[오류] {PORT}번 포트를 열 수 없습니다. 이미 실행 중인 TCG 서버가 있는지 확인하세요: {exc}')
    candidates=lan_ipv4_candidates();lan_ip=choose_lan_ip(candidates)
    url=f'http://127.0.0.1:{PORT}/index.html'
    print('이 기기 접속 주소:',url,flush=True)
    print(f'다른 기기 접속 주소(같은 Wi-Fi): http://{lan_ip}:{PORT}/index.html',flush=True)
    alternatives=[x for x in candidates if x!=lan_ip and x!='127.0.0.1']
    if alternatives: print('참고: 감지된 다른 주소:',', '.join(alternatives),flush=True)
    try: threading.Thread(target=lambda:webbrowser.open(url),daemon=True).start()
    except Exception: pass
    threading.Thread(target=auto_update_loop,daemon=True).start()
    print('공식자료 자동 확인: 시작 직후 전체검증 + 매 6시간 반영 · 30분 전 사전수집',flush=True)
    print('1 출시일 · 2 판매/재발매 · 3 거래시세 · 4 프로모/콜라보 · 5 구매처/링크 · 6 환율',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
