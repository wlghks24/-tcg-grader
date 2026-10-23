#!/usr/bin/env python3
"""Serve an isolated, read-only candidate preview on a user-owned local device.

No install, collection, training, remote browser, or merge is performed. Browser
observations remain unverified until reviewed; they never attest a physical run.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from urllib.parse import unquote, urlsplit

ROOT=Path(__file__).resolve().parents[1]
ASSET_SUFFIXES={'.html','.js','.css','.json','.webmanifest','.svg','.png','.jpg','.jpeg','.webp','.ico','.woff','.woff2'}


def snapshot(root:Path)->dict:
    def git(*args):
        return subprocess.check_output(['git','-C',str(root),*args],text=True,timeout=15).strip()
    if git('status','--porcelain','--untracked-files=no'):
        raise ValueError('review requires a clean tracked working tree')
    paths=git('ls-files','-z').split('\0')
    files={p for p in paths if p and not any(x.startswith('.') for x in Path(p).parts)
           and Path(p).suffix.lower() in ASSET_SUFFIXES}
    return {'head':git('rev-parse','HEAD'),'files':files,
            'index_sha256':hashlib.sha256((root/'index.html').read_bytes()).hexdigest()}


def make_server(root:Path,output:Path,*,port:int=0):
    root=root.resolve();state=snapshot(root);token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,body,kind='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; worker-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'")
            self.end_headers();self.wfile.write(body)
        def valid_host(self):
            return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def do_GET(self):
            if not self.valid_host():return self.send(403,b'{}')
            path=unquote(urlsplit(self.path).path)
            if path=='/__review':
                page=(root/'execution/tablet_local_ui_review.html').read_text()
                return self.send(200,page.replace('__CONFIG__',json.dumps({'token':token,'head':state['head']})).encode(),'text/html; charset=utf-8')
            if path.startswith('/api/'):
                return self.send(503,b'{"ok":false,"error":"read-only preview: runtime API disabled"}')
            name='index.html' if path=='/' else path.lstrip('/')
            target=root/name
            if name not in state['files'] or not target.is_file() or target.is_symlink():
                return self.send(404,b'{}')
            if root not in target.resolve().parents or any(p.is_symlink() for p in target.parents if p!=root):
                return self.send(403,b'{}')
            if target.stat().st_size>8*1024*1024:return self.send(413,b'{}')
            return self.send(200,target.read_bytes(),mimetypes.guess_type(name)[0] or 'application/octet-stream')
        def do_POST(self):
            if not self.valid_host() or self.path!='/__review/report':return self.send(403,b'{}')
            origin=f'http://127.0.0.1:{self.server.server_port}'
            if self.headers.get('Origin')!=origin or not secrets.compare_digest(self.headers.get('X-TCG-Review-Token',''),token):
                return self.send(403,b'{}')
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=32*1024:raise ValueError('size')
                data=json.loads(self.rfile.read(length))
                if data.get('head')!=state['head'] or data.get('widths')!=[360,1024]:raise ValueError('source/width')
                checks=data.get('checks')
                if not isinstance(checks,list) or not 1<=len(checks)<=300:raise ValueError('checks')
                clean=[]
                for row in checks:
                    if not isinstance(row,dict) or type(row.get('ok')) is not bool or row.get('width') not in (360,1024):raise ValueError('check')
                    if not isinstance(row.get('name'),str) or not re.fullmatch(r'[a-zA-Z0-9_:#.\-]{1,120}',row['name']):raise ValueError('name')
                    clean.append({k:row[k] for k in ('width','name','ok')})
                # Never accept browser-provided paths, platform claims or approval flags.
                current=snapshot(root)
                if current['head']!=state['head'] or current['index_sha256']!=state['index_sha256']:raise ValueError('source changed')
                report={'schema':'local-ui-browser-observations/v1','head':state['head'],
                    'index_sha256':state['index_sha256'],'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                    'scope':'LOCAL_BROWSER_NAVIGATION_OBSERVATIONS','widths':[360,1024],'checks':clean,
                    'all_reported_checks_passed':all(r['ok'] for r in clean),'independently_verified':False,
                    'physical_tablet_verified':False,'deployment_allowed':False,
                    'production_writes_allowed':False,'runtime_api_enabled':False}
                output.mkdir(parents=True,exist_ok=True)
                target=output/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+secrets.token_hex(4)+'.json')
                with target.open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
                return self.send(200,json.dumps({'ok':True,'file':target.name,'report':report}).encode())
            except (ValueError,TypeError,AttributeError,KeyError,OSError,subprocess.SubprocessError):return self.send(400,b'{"ok":false}')
        def do_PUT(self):return self.send(403,b'{}')
        do_DELETE=do_PUT
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=0,help='default: a temporary free local port')
    p.add_argument('--open-browser',action='store_true',help='open the native Termux browser when available')
    args=p.parse_args()
    server=make_server(ROOT,ROOT/'.tmp/local-ui-review',port=args.port)
    print(f'Local browser review: http://127.0.0.1:{server.server_port}/__review',flush=True)
    print('Source: '+snapshot(ROOT)['head']+'; reports: .tmp/local-ui-review; Ctrl+C stops preview',flush=True)
    if args.open_browser and (opener:=shutil.which('termux-open-url')):
        subprocess.Popen([opener,f'http://127.0.0.1:{server.server_port}/__review'])
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
