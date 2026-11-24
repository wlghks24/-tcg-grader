import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from execution.deferred_publish_handoff import handoff, PREFIX

class HandoffTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        self.git('init','-q');self.git('config','user.name','CI');self.git('config','user.email','ci@example.invalid')
        self.data='grading_company_updates.json';self.write(1);self.base=self.commit();self.write(2);self.head=self.commit()
        self.route='grading';self.repo='example/cards';self.run='123';self.attempt='1';self.branch=PREFIX[self.route]+self.run+'-'+self.attempt
        self.id=42;self.number=55;self.rows=[];self.posts=0;self.calls=[];self.post_error=False;self.lost_response=False;self.drift=False;self.bad_number=False
    def git(self,*a):return subprocess.check_output(['git',*a],cwd=self.root,stderr=subprocess.PIPE).decode().strip()
    def commit(self):self.git('add','-A');self.git('commit','-qm','fixture');return self.git('rev-parse','HEAD')
    def write(self,n):
        d=json.dumps({'v':n}).encode();(self.root/self.data).write_bytes(d)
        m={'version':2,'engine':'test','generated_at':str(n),'files':{self.data:{'sha256':hashlib.sha256(d).hexdigest(),'bytes':len(d)}},'mutable_json':{},'policy':{}}
        (self.root/'integrity_manifest.json').write_text(json.dumps(m))
    def pr(self):return {'number':self.number,'state':'open','merged':False,'head':{'ref':self.branch,'sha':self.head,'repo':{'id':self.id}},'base':{'ref':'main','sha':self.base,'repo':{'id':self.id}}}
    def get(self,method,endpoint,*,fields=None,pages=False):
        self.calls.append((method,endpoint))
        prefix='repos/'+self.repo
        if endpoint==prefix:return {'id':self.id,'full_name':self.repo}
        if '/git/ref/heads/' in endpoint:
            ref=endpoint.split('/git/ref/heads/',1)[1];sha=self.base if ref=='main' else self.head
            if self.drift and ref=='main':sha='c'*40
            return {'ref':'refs/heads/'+ref,'object':{'type':'commit','sha':sha}}
        if '/compare/' in endpoint:return {'base_commit':{'sha':self.base},'merge_base_commit':{'sha':self.base},'status':'ahead','ahead_by':1,'behind_by':0,'total_commits':1,'commits':[{'sha':self.head,'parents':[{'sha':self.base}]}],'files':[{'filename':p,'status':'modified'} for p in (self.data,'integrity_manifest.json')]}
        if '/pulls?' in endpoint:
            assert pages
            return copy.deepcopy([self.rows])
        if endpoint==prefix+'/pulls' and method=='POST':
            self.posts+=1
            if self.post_error:raise subprocess.CalledProcessError(1,['gh'])
            self.rows.append(self.pr())
            if self.lost_response:raise subprocess.CalledProcessError(1,['gh'])
            return self.pr()
        if endpoint==prefix+'/pulls/'+str(self.number):
            p=self.pr()
            if self.bad_number:p['number']+=1
            return p
        raise AssertionError((method,endpoint))
    def verify(self):return handoff(self.root,self.route,self.repo,self.run,self.attempt,self.base,self.head,self.branch,get=self.get)
    def test_create(self):
        r=self.verify();self.assertEqual('PENDING_EXTERNAL_CI',r['status']);self.assertFalse(r['deployed']);self.assertEqual(1,self.posts)
        self.assertTrue(all(m in ('GET','POST') and '/merge' not in p and '/dispatches' not in p for m,p in self.calls))
    def test_reuse(self):self.rows=[self.pr()];self.assertEqual(55,self.verify()['pr_number']);self.assertEqual(0,self.posts)
    def test_lost_response(self):self.lost_response=True;self.assertEqual('PENDING_EXTERNAL_CI',self.verify()['status']);self.assertEqual(1,self.posts)
    def test_denied(self):self.post_error=True;self.assertEqual('PENDING_EXTERNAL_PR',self.verify()['status']);self.assertEqual(1,self.posts)
    def test_wrong_branch(self):self.branch='main';self.assertRaises(ValueError,self.verify);self.assertEqual(0,self.posts)
    def test_main_drift(self):self.drift=True;self.assertRaises(ValueError,self.verify);self.assertEqual(0,self.posts)
    def test_duplicate_pr(self):self.rows=[self.pr(),self.pr()];self.assertRaises(ValueError,self.verify);self.assertEqual(0,self.posts)
    def test_wrong_base_pr(self):self.rows=[self.pr()];self.rows[0]['base']['ref']='other';self.assertRaises(ValueError,self.verify)
    def test_wrong_repo_pr(self):self.rows=[self.pr()];self.rows[0]['head']['repo']['id']=99;self.assertRaises(ValueError,self.verify)
    def test_wrong_number(self):self.bad_number=True;self.assertRaises(ValueError,self.verify)
    def test_wrong_head(self):self.head='b'*40;self.assertRaises(ValueError,self.verify)
    def test_uncommitted_head_change(self):
        (self.root/'unexpected').write_text('x');self.commit();self.assertRaises(ValueError,self.verify)
    def test_code_route(self):
        self.route='code';self.branch=PREFIX[self.route]+self.run+'-'+self.attempt
        self.assertEqual('PENDING_EXTERNAL_CI',self.verify()['status']);self.assertFalse(any('/compare/' in p for m,p in self.calls))
    def test_invalid_attempt(self):self.attempt='0';self.assertRaises(ValueError,self.verify)
    def test_data_changed_mode(self):
        self.git('reset','--soft',self.base);(self.root/self.data).chmod(0o755);self.head=self.commit();self.assertRaises(ValueError,self.verify);self.assertEqual(0,self.posts)
    def test_api_page_shape(self):
        orig=self.get
        def malformed(m,e,**kw):return {} if '/pulls?' in e else orig(m,e,**kw)
        self.get=malformed;self.assertRaises(ValueError,self.verify);self.assertEqual(0,self.posts)
if __name__=='__main__':unittest.main()
