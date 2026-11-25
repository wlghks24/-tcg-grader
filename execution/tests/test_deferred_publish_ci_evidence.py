"""Offline authenticated-API fixtures for exact main-target CI evidence."""
import copy
import unittest
from execution import deferred_publish_ci_evidence as c


class CIEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.repo='example/cards'; self.number=55; self.repo_id=42
        self.base='a'*40; self.head='b'*40; self.branch='review/candidate'
        self.path='repos/'+self.repo; self.calls=[]; self.reads=0
        self.pr={'id':100,'number':55,'state':'open','merged':False,
                 'base':{'ref':'main','sha':self.base,'repo':{'id':42}},
                 'head':{'ref':self.branch,'sha':self.head,'repo':{'id':42}}}
        self.rows=[]; self.jobs={}; self.total_delta=0; self.job_total_delta=0
        self.ref_drift=False; self.rerun=False
        for i,name in enumerate(sorted(c.MAIN_WORKFLOWS),1):
            self.rows.append({'id':i,'workflow_id':i+100,'run_number':1,'run_attempt':1,'path':name,
                              'event':'pull_request','pull_requests':[copy.deepcopy(self.pr)],
                              'head_sha':self.head,'head_branch':self.branch,
                              'repository':{'id':42},'head_repository':{'id':42},
                              'status':'completed','conclusion':'success'})
            self.jobs[i]=[dict(id=i*1000+j,run_id=i,run_attempt=1,head_sha=self.head,
                               head_branch=self.branch,name=n,status='completed',conclusion='success')
                          for j,n in enumerate(c.REQUIRED_JOBS.get(name,()),1)]

    def get(self,endpoint,*,pages=False):
        self.calls.append(endpoint)
        if endpoint==self.path: return {'id':42,'full_name':self.repo}
        if '/pulls/' in endpoint: return copy.deepcopy(self.pr)
        if '/git/ref/heads/' in endpoint:
            ref=endpoint.split('/git/ref/heads/',1)[1]
            sha=self.base if ref=='main' else self.head
            if self.ref_drift and self.reads>=2 and ref=='main': sha='c'*40
            return {'ref':'refs/heads/'+ref,'object':{'type':'commit','sha':sha}}
        if '/actions/runs?' in endpoint:
            assert pages
            self.reads+=1
            rows=copy.deepcopy(self.rows)
            if self.rerun and self.reads>=2: rows[0]['run_attempt']=2
            total=len(rows)+self.total_delta
            return [{'total_count':total,'workflow_runs':rows[:16]},
                    {'total_count':total,'workflow_runs':rows[16:]}]
        if '/attempts/' in endpoint:
            assert pages
            run=int(endpoint.split('/actions/runs/')[1].split('/')[0])
            jobs=copy.deepcopy(self.jobs[run]); total=len(jobs)+self.job_total_delta
            return [{'total_count':total,'jobs':jobs}]
        raise AssertionError(endpoint)

    def review(self):
        return c.review(self.repo,self.number,self.base,self.head,self.branch,get=self.get)

    def core(self):
        return next(row for row in self.rows if row['path'] in c.REQUIRED_JOBS)

    def test_complete(self):
        r=self.review(); self.assertEqual((32,72),(r['workflows'],r['core_jobs']))
        self.assertEqual('CI_EVIDENCE_PASS',r['verdict'])
        self.assertFalse(r['merge_authorized']); self.assertFalse(r['deployment_authorized'])
        self.assertFalse(r['physical_tablet_verified'])
        self.assertFalse(any('/merge' in x or '/dispatches' in x for x in self.calls))

    def test_missing_workflow(self):
        self.rows.pop(); self.assertRaises(ValueError,self.review)

    def test_wrong_pr(self):
        self.rows[0]['pull_requests'][0]['number']=56; self.assertRaises(ValueError,self.review)

    def test_wrong_base(self):
        self.rows[0]['pull_requests'][0]['base']['ref']='review/stack'; self.assertRaises(ValueError,self.review)

    def test_dispatch_not_pr(self):
        self.rows[0]['event']='workflow_dispatch'; self.assertRaises(ValueError,self.review)

    def test_wrong_head_repository(self):
        self.rows[0]['head_repository']['id']=99; self.assertRaises(ValueError,self.review)

    def test_old_head(self):
        self.rows[0]['head_sha']='c'*40; self.assertRaises(ValueError,self.review)

    def test_duplicate_workflow(self):
        row=copy.deepcopy(self.rows[0]); row['id']=99; self.rows.append(row)
        self.assertRaises(ValueError,self.review)

    def test_truncated_runs(self):
        self.total_delta=1; self.assertRaises(ValueError,self.review)

    def test_failed_aggregate(self):
        self.rows[0]['conclusion']='failure'; self.assertRaises(ValueError,self.review)

    def test_failed_job(self):
        self.jobs[self.core()['id']][0]['conclusion']='failure'; self.assertRaises(ValueError,self.review)

    def test_wrong_attempt(self):
        self.jobs[self.core()['id']][0]['run_attempt']=2; self.assertRaises(ValueError,self.review)

    def test_wrong_job_head(self):
        self.jobs[self.core()['id']][0]['head_sha']='c'*40; self.assertRaises(ValueError,self.review)

    def test_wrong_job_id(self):
        self.jobs[self.core()['id']][0]['run_id']=999; self.assertRaises(ValueError,self.review)

    def test_truncated_jobs(self):
        self.job_total_delta=1; self.assertRaises(ValueError,self.review)

    def test_rerun_race(self):
        self.rerun=True; self.assertRaises(ValueError,self.review)

    def test_main_race(self):
        self.ref_drift=True; self.assertRaises(ValueError,self.review)

    def test_wrong_shard(self):
        row=next(r for r in self.rows if 'v1025-full' in r['path'])
        self.jobs[row['id']][0]['name']='Complete root tests (99)'
        self.assertRaises(ValueError,self.review)

    def test_unrelated_dispatch_ignored(self):
        row=copy.deepcopy(self.rows[0]); row['id']=99; row['event']='workflow_dispatch'; self.rows.append(row)
        self.assertEqual(32,self.review()['workflows'])

    def test_bad_pr(self):
        self.pr['merged']=True; self.assertRaises(ValueError,self.review)


if __name__=='__main__': unittest.main()
