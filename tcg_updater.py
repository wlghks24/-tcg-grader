#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, re, hashlib, threading, webbrowser, time, socket
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.request import Request, urlopen

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,'tcg_live_data.json')
SOURCES=[
 ('포켓몬 일본 공식','https://www.pokemon-card.com/products/index.html','공식'),
 ('포켓몬 30주년 공식','https://www.30th.pokemon-card.com/','공식'),
 ('원피스 한국 공식','https://onepiece-cardgame.kr/products.do','공식'),
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
    return {'updated_at':None,'sources':{},'pending':[],'applied':[]}

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

class Handler(SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass
    def json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode('utf-8')
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/api/health': return self.json({'ok':True,'service':'TCG v31'})
        if path=='/api/status': return self.json(load_db())
        if path=='/api/validation': return self.json({'ok':True,'mode':'pre-grade','probability_claim':False})
        if path=='/api/update':
            try: return self.json(collect())
            except Exception as exc: return self.json({'ok':False,'error':str(exc)},500)
        return super().do_GET()
    def do_POST(self):
        if self.path.split('?',1)[0]!='/api/apply': return self.json({'ok':False,'error':'없는 API'},404)
        data=load_db(); pending=data.get('pending',[]); now=time.strftime('%Y-%m-%dT%H:%M:%S%z')
        valid=[x for x in pending if x.get('status')!='수집 오류']
        errors=[x for x in pending if x.get('status')=='수집 오류']
        if not valid:
            return self.json({'ok':True,'applied_count':0,'error_count':len(errors),'updated_at':now,'message':'반영 가능한 정상 변경사항이 없습니다.'})
        if os.path.exists(DB):
            try:
                with open(DB,'rb') as src, open(DB+'.bak','wb') as dst: dst.write(src.read())
            except OSError: pass
        data['applied']=(data.get('applied',[])+[{**x,'applied_at':now} for x in valid])[-1000:]
        data['pending']=errors
        save_db(data)
        return self.json({'ok':True,'applied_count':len(valid),'error_count':len(errors),'updated_at':now})

if __name__=='__main__':
    os.chdir(BASE)
    server=ThreadingHTTPServer(('0.0.0.0',PORT),Handler)
    try:
        lan_ip=socket.gethostbyname(socket.gethostname())
    except OSError:
        lan_ip='127.0.0.1'
    url=f'http://127.0.0.1:{PORT}/index.html'
    print('TCG v31 PC 주소:',url,flush=True)
    print(f'아이폰 접속 주소(같은 Wi-Fi): http://{lan_ip}:{PORT}/index.html',flush=True)
    try: threading.Thread(target=lambda:webbrowser.open(url),daemon=True).start()
    except Exception: pass
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
