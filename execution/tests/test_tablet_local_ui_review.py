"""Local preview must never expose secrets, mutate runtime, or attest a device."""
import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import unittest

from execution.tablet_local_ui_review import make_server,snapshot


class LocalUIReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)/'repo';cls.root.mkdir()
        (cls.root/'execution').mkdir()
        source=Path(__file__).resolve().parents[1]/'tablet_local_ui_review.html'
        (cls.root/'execution/tablet_local_ui_review.html').write_bytes(source.read_bytes())
        (cls.root/'index.html').write_text('<h1>test</h1>')
        (cls.root/'asset.js').write_text('"use strict";')
        (cls.root/'private.env').write_text('not served')
        (cls.root/'untracked.json').write_text('{"private":true}')
        for args in [('init','-q'),('add','index.html','asset.js','execution/tablet_local_ui_review.html'),
                     ('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')]:
            subprocess.run(['git','-C',str(cls.root),*args],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.out=Path(self.tmp.name)/('out-'+self._testMethodName)
        self.server=make_server(self.root,self.out,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)
    def request(self,path,method='GET',body=None,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        c.request(method,path,body=body,headers=headers or {})
        r=c.getresponse();result=(r.status,r.read(),dict(r.getheaders()));c.close();return result
    def config(self):
        status,body,_=self.request('/__review');self.assertEqual(200,status)
        return json.loads(re.search(r'const config=(\{[^\n]+?\}),status',body.decode()).group(1))
    def payload(self):return {'head':snapshot(self.root)['head'],'widths':[360,1024],
                             'checks':[{'width':360,'name':'route:test','ok':True},{'width':1024,'name':'route:test','ok':True}]}
    def report(self,data,**changes):
        config=self.config();headers={'Origin':f'http://127.0.0.1:{self.server.server_port}',
            'Content-Type':'application/json','X-TCG-Review-Token':config['token']};headers.update(changes)
        return self.request('/__review/report','POST',json.dumps(data),headers)
    def test_static_assets_are_tracked_only_and_external_connections_are_blocked(self):
        status,body,headers=self.request('/')
        self.assertEqual((200,b'<h1>test</h1>'),(status,body))
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])
        self.assertIn("worker-src 'none'",headers['Content-Security-Policy'])
        for path in ['/private.env','/untracked.json','/.git/config','/%2e%2e/index.html','/execution/','//etc/passwd']:
            with self.subTest(path=path):self.assertNotEqual(200,self.request(path)[0])
    def test_host_rebinding_is_rejected(self):self.assertEqual(403,self.request('/',headers={'Host':'evil.test'})[0])
    def test_read_proxy_is_opt_in_and_mutating_api_never_runs(self):
        for path in ['/api/local-card-images','/api/local-card-images/catalog-links','/api/collect']:
            self.assertEqual(503,self.request(path)[0])
            self.assertEqual(403,self.request(path,'POST','{}')[0])
        self.assertFalse(self.out.exists())
    def test_report_pins_source_but_never_accepts_approval_claims_or_output_paths(self):
        payload={**self.payload(),'physical_tablet_verified':True,'deployment_allowed':True,'output':'/bad'}
        status,body,_=self.report(payload);self.assertEqual(200,status)
        report=json.loads(body)['report'];self.assertFalse(report['physical_tablet_verified'])
        self.assertFalse(report['deployment_allowed']);self.assertFalse(report['independently_verified'])
        files=list(self.out.glob('*.json'));self.assertEqual(1,len(files));self.assertEqual(report,json.loads(files[0].read_text()))
        self.assertNotIn('output',report);self.assertTrue(report['all_reported_checks_passed'])
    def test_wrong_origin_or_token_cannot_write_report(self):
        self.assertEqual(403,self.report(self.payload(),Origin='https://evil.test')[0])
        self.assertEqual(403,self.report(self.payload(),**{'X-TCG-Review-Token':'wrong'})[0])
        self.assertFalse(self.out.exists())
    def test_wrong_source_widths_malformed_checks_and_large_payload_are_rejected(self):
        for edit in [{'head':'0'*40},{'widths':[360]}, {'checks':[]},
                     {'checks':[{'width':360,'name':'../../x','ok':True}]},
                     {'checks':[{'width':360,'name':'test','ok':1}]}, {'padding':'x'*33000}]:
            with self.subTest(edit=str(edit)[:100]):self.assertEqual(400,self.report({**self.payload(),**edit})[0])
        self.assertFalse(self.out.exists())
    def test_changed_tracked_source_is_rejected_at_start_and_at_readback(self):
        payload=self.payload();config=self.config();index=self.root/'index.html';prior=index.read_bytes()
        try:
            index.write_bytes(prior+b'changed')
            with self.assertRaises(ValueError):snapshot(self.root)
            headers={'Origin':f'http://127.0.0.1:{self.server.server_port}','X-TCG-Review-Token':config['token']}
            self.assertEqual(400,self.request('/__review/report','POST',json.dumps(payload),headers)[0])
        finally:index.write_bytes(prior)
    def test_failed_browser_observation_remains_a_failure(self):
        data=self.payload();data['checks'][0]['ok']=False
        status,body,_=self.report(data);self.assertEqual(200,status)
        self.assertFalse(json.loads(body)['report']['all_reported_checks_passed'])
    def test_mutating_methods_are_blocked_even_for_report_route(self):
        for method in ['PUT','DELETE']:
            self.assertEqual(403,self.request('/__review/report',method,'{}')[0])

    @unittest.skipUnless(shutil.which('node'),'Node required')
    def test_browser_panel_gate_rejects_wrong_or_multiple_inner_panels(self):
        text=(self.root/'execution/tablet_local_ui_review.html').read_text()
        fn=text[text.index('function panelSelected('):text.index('button.onclick=')]
        script="""
const assert=require('node:assert/strict');
const panel=(id,hidden)=>({id,hidden,getClientRects(){return this.hidden?[]:[{}]}});
const tab=(id,on)=>({dataset:{topPanel:id},on,classList:{contains(){return this.owner.on}}});
const panels=[panel('releasePanel',false),panel('promoPanel',true)],tabs=[tab('releasePanel',true),tab('promoPanel',false)];
tabs.forEach(t=>t.classList.owner=t);
const d={querySelectorAll:s=>s==='.top-info-panel'?panels:tabs},w={getComputedStyle:()=>({visibility:'visible'})};
"""+fn+"""
assert.equal(panelSelected(d,w,'releasePanel'),true);
assert.equal(panelSelected(d,w,'promoPanel'),false);
tabs[0].on=false;tabs[1].on=true;
assert.equal(panelSelected(d,w,'releasePanel'),false,'same parent board does not prove correct inner panel');
panels[0].hidden=true;panels[1].hidden=false;
assert.equal(panelSelected(d,w,'promoPanel'),true);
panels[0].hidden=false;assert.equal(panelSelected(d,w,'promoPanel'),false);
panels[0].hidden=true;tabs[0].on=true;assert.equal(panelSelected(d,w,'promoPanel'),false);
assert.equal(panelSelected(d,w,'missing'),false);
"""
        run=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(0,run.returncode,run.stdout+run.stderr)


if __name__=='__main__':unittest.main()
