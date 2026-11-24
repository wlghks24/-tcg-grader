import copy
import unittest
from execution.deferred_publish_policy import REQUIRED_JOBS, check_jobs, check_data_compare

class DeferredPublishTests(unittest.TestCase):
    def setUp(self):
        self.path = '.github/workflows/v1025-full-coverage-successor.yml'
        self.jobs = [dict(name=n, status='completed', conclusion='success') for n in REQUIRED_JOBS[self.path]]
        self.base, self.head = 'a'*40, 'b'*40
        self.compare = dict(base_commit={'sha':self.base}, merge_base_commit={'sha':self.base}, status='ahead', ahead_by=1, behind_by=0, total_commits=1, commits=[{'sha':self.head,'parents':[{'sha':self.base}]}], files=[{'filename':'grading_company_updates.json','status':'modified'},{'filename':'integrity_manifest.json','status':'modified'}])
    def test_exact_all_eight(self):
        self.assertEqual(8,len(REQUIRED_JOBS))
        self.assertEqual(72,sum(map(len,REQUIRED_JOBS.values())))
        for path,names in REQUIRED_JOBS.items():
            self.assertTrue(check_jobs(path,[dict(name=n,status='completed',conclusion='success') for n in names],True))
    def test_wrong_shard_same_count(self):
        self.jobs[1]['name']='Complete root tests (16)'
        with self.assertRaises(ValueError): check_jobs(self.path,self.jobs,True)
    def test_duplicate_shard_same_count(self):
        self.jobs[1]=copy.deepcopy(self.jobs[2])
        with self.assertRaises(ValueError): check_jobs(self.path,self.jobs,True)
    def test_missing_completed(self):
        with self.assertRaises(ValueError): check_jobs(self.path,self.jobs[:-1],True)
    def test_partial_pending(self): self.assertFalse(check_jobs(self.path,self.jobs[:-1],False))
    def test_failed_pending(self):
        self.jobs[1]['conclusion']='cancelled'
        with self.assertRaises(ValueError): check_jobs(self.path,self.jobs,False)
    def test_completed_not_success(self):
        self.jobs[1].update(status='queued',conclusion=None)
        with self.assertRaises(ValueError): check_jobs(self.path,self.jobs,True)
    def test_unknown_job_pending(self):
        self.jobs[1]['name']='arbitrary'
        with self.assertRaises(ValueError): check_jobs(self.path,self.jobs,False)
    def verify(self): return check_data_compare('grading',self.base,self.head,self.compare)
    def test_valid_scope(self): self.assertEqual(('grading_company_updates.json','integrity_manifest.json'),self.verify())
    def test_code_mutation(self):
        self.compare['files'][0]['filename']='.github/workflows/v1025-full-coverage-successor.yml'
        with self.assertRaises(ValueError): self.verify()
    def test_wrong_data_route(self):
        self.compare['files'][0]['filename']='market_prices.json'
        with self.assertRaises(ValueError): self.verify()
        self.assertIn('market_prices.json',check_data_compare('static',self.base,self.head,self.compare))
    def test_rename(self):
        self.compare['files'][0].update(status='renamed',previous_filename='old.json')
        with self.assertRaises(ValueError): self.verify()
    def test_duplicate_path(self):
        self.compare['files'][0]=copy.deepcopy(self.compare['files'][1])
        with self.assertRaises(ValueError): self.verify()
    def test_no_manifest(self):
        self.compare['files'].pop()
        with self.assertRaises(ValueError): self.verify()
    def test_no_data(self):
        self.compare['files'].pop(0)
        with self.assertRaises(ValueError): self.verify()
    def test_base_drift(self):
        self.compare['merge_base_commit']['sha']='c'*40
        with self.assertRaises(ValueError): self.verify()
    def test_merge_parent(self):
        self.compare['commits'][0]['parents'].append({'sha':'c'*40})
        with self.assertRaises(ValueError): self.verify()
    def test_bool_count(self):
        self.compare['ahead_by']=True
        with self.assertRaises(ValueError): self.verify()
    def test_wrong_head(self):
        self.compare['commits'][0]['sha']='c'*40
        with self.assertRaises(ValueError): self.verify()

if __name__=='__main__': unittest.main()
