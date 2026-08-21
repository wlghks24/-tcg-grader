#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, re, hashlib, threading, webbrowser, time, socket
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,'tcg_live_data.json')
MARKET_DB=os.path.join(BASE,'market_prices.json')
MARKET_WATCH=os.path.join(BASE,'market_watch.json')
AUTO_REPORT=os.path.join(BASE,'auto_update_report.json')
AUTO_ISSUES=os.path.join(BASE,'auto_update_issues.json')
AUTO_MEMORY=os.path.join(BASE,'auto_repair_memory.json')
AUTO_INTERVAL_SECONDS=6*60*60
UPDATE_LOCK=threading.Lock()
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

PORT=free_port()

def default_db():
    return {'updated_at':None,'sources':{},'pending':[],'applied':[],
            'auto_update':{'enabled':True,'interval_hours':6,'last_run':None,'next_run':None,'status':'대기 중'}}

def load_db():
    try:
        with open(DB,'r',encoding='utf-8') as f: data=json.load(f)
        base=default_db()
        for k,v in base.items(): data.setdefault(k,v)
        return data
    except (OSError,ValueError,TypeError):
        return default_db()

def save_db(data):
    tmp=DB+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)
    os.replace(tmp,DB)

def load_market_db():
    try:
        with open(MARKET_DB,'r',encoding='utf-8') as f:return json.load(f)
    except (OSError,ValueError,TypeError):
        return {'updated_at':None,'entries':{},'collection_status':'가격자료 없음'}

def load_market_watch():
    return load_json_file(MARKET_WATCH,{'updated_at':None,'items':[],'collection_status':'추적자료 없음'})

def load_json_file(path, fallback):
    try:
        with open(path,'r',encoding='utf-8') as f:return json.load(f)
    except (OSError,ValueError,TypeError):return fallback

def fetch(url):
    req=Request(url,headers={'User-Agent':'TCG-Research-Updater/27'})
    with urlopen(req,timeout=15) as r:
        return r.read(500000).decode('utf-8','ignore')

def title(html):
    m=re.search(r'<title[^>]*>(.*?)</title>',html,re.I|re.S)
    return re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',m.group(1))).strip() if m else ''

def collect():
    data=load_db(); now=time.strftime('%Y-%m-%dT%H:%M:%S%z'); pending=[]
    for name,url,kind in SOURCES:
        try:
            html=fetch(url); fp=hashlib.sha256(html.encode()).hexdigest()
            old=data['sources'].get(name); changed=bool(old) and old.get('fingerprint')!=fp
            data['sources'][name]={'url':url,'kind':kind,'title':title(html),'fingerprint':fp,'checked_at':now}
            if changed or not old:
                pending.append({'source':name,'url':url,'kind':kind,'status':'변경 확인 필요' if changed else '최초 확인','checked_at':now})
        except Exception as exc:
            pending.append({'source':name,'url':url,'kind':kind,'status':'수집 오류','error':str(exc),'checked_at':now})
    data['updated_at']=now; data['pending']=pending; save_db(data); return data

def update_cycle(trigger='manual'):
    """Collect official source changes and refresh the verified release board safely."""
    with UPDATE_LOCK:
        started=time.time()
        data=collect()
        try:
            import auto_update_all
            report=auto_update_all.run_all(trigger)
            result_map={x['file']:x for x in report['results']}
            release_status=result_map['releases.json']['status']
            market_status=result_map['market_prices.json']['status']
            watch_status=result_map['market_watch.json']['status']
            promo_status=result_map['promo_events.json']['status']
            fx_status=result_map['exchange_rates.json']['status']
        except Exception as exc:
            message=f'통합 자동업데이트 오류: {type(exc).__name__}'
            release_status=market_status=watch_status=promo_status=fx_status=message
        data=load_db()
        data['auto_update']={
            'enabled':True,'interval_hours':6,'trigger':trigger,
            'last_run':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(started)),
            'next_run':time.strftime('%Y-%m-%dT%H:%M:%S%z',time.localtime(started+AUTO_INTERVAL_SECONDS)),
            'status':release_status,'market_status':market_status,'watch_status':watch_status,'promo_status':promo_status,'fx_status':fx_status,
        }
        save_db(data)
        return data

def auto_update_loop():
    while True:
        try: update_cycle('automatic')
        except Exception: pass
        time.sleep(AUTO_INTERVAL_SECONDS)

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    def json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        parsed=urlparse(self.path);path=parsed.path
        if path=='/api/health': return self.json({'ok':True,'service':'TCG v31'})
        if path=='/api/status': return self.json(load_db())
        if path=='/api/auto-status': return self.json(load_db().get('auto_update',{}))
        if path=='/api/update-report': return self.json(load_json_file(AUTO_REPORT,{'ok':False,'results':[]}))
        if path=='/api/update-issues': return self.json(load_json_file(AUTO_ISSUES,{'issue_count':0,'issues':[]}))
        if path=='/api/repair-memory': return self.json(load_json_file(AUTO_MEMORY,{'total_runs':0,'patterns':{},'files':{}}))
        if path=='/api/market-watch': return self.json(load_market_watch())
        if path=='/api/validation': return self.json({'ok':True,'mode':'pre-grade','probability_claim':False})
        if path=='/api/market-price':
            qs=parse_qs(parsed.query); key=qs.get('key',[''])[0]
            if not key or len(key)>160:return self.json({'ok':False,'error':'가격 키 오류'},400)
            db=load_market_db(); entry=db.get('entries',{}).get(key)
            return self.json({'ok':True,'found':bool(entry),'key':key,'updated_at':db.get('updated_at'),'collection_status':db.get('collection_status'),'price':entry})
        if path=='/api/update':
            try: return self.json(update_cycle('manual'))
            except Exception as exc: return self.json({'ok':False,'error':str(exc)},500)
        return super().do_GET()
    def do_POST(self):
        if self.path.split('?',1)[0]!='/api/apply': return self.json({'ok':False,'error':'없는 API'},404)
        data=load_db(); pending=data.get('pending',[]); now=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        valid=[x for x in pending if x.get('status')!='수집 오류']
        errors=[x for x in pending if x.get('status')=='수집 오류']
        if not valid:
            return self.json({'ok':True,'approved_count':0,'error_count':len(errors),'updated_at':now,'catalog_changed':False,'message':'승인 기록으로 저장할 정상 변경사항이 없습니다.'})
        if os.path.exists(DB):
            try:
                with open(DB,'rb') as src, open(DB+'.bak','wb') as dst: dst.write(src.read())
            except OSError: pass
        data['applied']=(data.get('applied',[])+[{**x,'applied_at':now} for x in valid])[-1000:]
        data['pending']=errors
        save_db(data)
        return self.json({'ok':True,'approved_count':len(valid),'error_count':len(errors),'updated_at':now,'catalog_changed':False,'message':'검토 승인 기록을 저장했습니다. 정적 목록 파일은 자동 변경하지 않습니다.'})

if __name__=='__main__':
    os.chdir(BASE)
    server=ThreadingHTTPServer(('0.0.0.0',PORT),Handler)
    try:
        probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        probe.connect(('8.8.8.8',80))
        lan_ip=probe.getsockname()[0]
        probe.close()
    except OSError:
        try: lan_ip=socket.gethostbyname(socket.gethostname())
        except OSError: lan_ip='127.0.0.1'
    url=f'http://127.0.0.1:{PORT}/index.html'
    print('이 기기 접속 주소:',url,flush=True)
    print(f'다른 기기 접속 주소(같은 Wi-Fi): http://{lan_ip}:{PORT}/index.html',flush=True)
    try: threading.Thread(target=lambda:webbrowser.open(url),daemon=True).start()
    except Exception: pass
    threading.Thread(target=auto_update_loop,daemon=True).start()
    print('공식자료 자동 확인: 시작 직후 + 6시간마다',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
