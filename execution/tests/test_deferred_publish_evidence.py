import copy
import unittest
from execution.deferred_publish_evidence import review_ci
from execution.deferred_publish_policy import REQUIRED_JOBS


class DeferredEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.base='a'*40; self.head='b'*40
        self.pr={'id':42,'number':7,'state':'open','merged':False,'base':{'ref':'main','sha':self.base,'repo':{'id':10}},'head':{'ref':'auto/fixture','sha':self.head,'repo':{'id':10}}}
        self.runs=[]; self.jobs={}; i=0
        for n,(path,names) in enumerate(REQUIRED_JOBS.items(),1):
            run={'id':100+n,'run_number':1,'run_attempt':1,'workflow_id':n,'path':path,'head_sha':self.head,'head_branch':'auto/fixture','event':'pull_request','repository':{'id':10},'head_repository':{'id':10},'pull_requests':[copy.deepcopy(self.pr)],'status':'completed','conclusion':'success'}
            self.runs.append(run); rows=[]
            for name in names:
                i+=1; rows.append({'id':1000+i,'run_id':run['id'],'run_attempt':1,'head_sha':self.head,'name':name,'status':'completed','conclusion':'success'})
            self.jobs[(run['id'],1)]={'total_count':len(rows),'jobs':rows}
    def verify(self): return review_ci(self.pr,self.base,self.runs,self.jobs)
    def first(self): return self.jobs[(self.runs[0]['id'],1)]
    def reject(self,pattern):
        with self.assertRaisesRegex(ValueError,pattern): self.verify()
    def test_all_72(self):
        r=self.verify(); self.assertEqual('CI_EVIDENCE_PASS',r['status']); self.assertEqual(72,sum(x['total_count'] for x in self.jobs.values())); self.assertFalse(r['merge_authorized']); self.assertFalse(r['deployment_authorized'])
    def test_missing_workflow(self):
        self.runs.pop(); self.assertEqual('PENDING_CI',self.verify()['status'])
    def test_failed_shard(self):
        self.first()['jobs'][0]['conclusion']='failure'; self.reject('job not successful')
    def test_wrong_sha(self):
        self.first()['jobs'][0]['head_sha']='c'*40; self.reject('attempt or head drift')
    def test_wrong_attempt(self):
        self.first()['jobs'][0]['run_attempt']=2; self.reject('attempt or head drift')
    def test_duplicate_job_id(self):
        self.first()['jobs'][1]['id']=self.first()['jobs'][0]['id']; self.reject('duplicate')
    def test_truncated_page(self):
        self.first()['total_count']+=1; self.reject('incomplete job pages')
    def test_missing_attempt(self):
        self.runs[0]['run_attempt']=2; self.reject('missing completed attempt')
    def test_newest_run_pending(self):
        row=copy.deepcopy(self.runs[0]); row.update(id=999,run_number=2,status='queued',conclusion=None); self.runs.append(row)
        self.assertEqual('PENDING_CI',self.verify()['status'])
    def test_newest_run_fails(self):
        row=copy.deepcopy(self.runs[0]); row.update(id=999,run_number=2,conclusion='failure'); self.runs.append(row); self.reject('workflow failed')
    def test_wrong_pr(self):
        self.runs[0]['pull_requests'][0]['id']=999; self.reject('not bound')
    def test_wrong_base(self):
        self.runs[0]['pull_requests'][0]['base']['sha']='c'*40; self.reject('PR ref drift')
    def test_wrong_branch(self):
        self.runs[0]['head_branch']='other'; self.reject('run head drift')
    def test_duplicate_run(self):
        self.runs.append(copy.deepcopy(self.runs[0])); self.reject('duplicate run')
    def test_manual_run_not_substitute(self):
        self.runs[0]['event']='workflow_dispatch'; self.reject('not PR CI')
    def test_main_advanced(self):
        self.base='c'*40; self.reject('main or head drift')
    def test_fork(self):
        self.pr['head']['repo']['id']=11; self.reject('repository drift')


if __name__=='__main__': unittest.main()
