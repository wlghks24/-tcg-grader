import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from execution.tcg_pr_merge_queue import audit,evaluate,main,REQUIRED
A='a'*40
B='b'*40

def candidate(**overrides):
    pr={'number':885,'title':'test: guard','state':'open','draft':False,
        'head':{'sha':B},'base':{'ref':'main'},'mergeable':True,
        'mergeable_state':'clean','candidate_base_sha':A,
        'runs':[{'name':name,'head_sha':B,'status':'completed','conclusion':'success',
                 'event':'workflow_dispatch','id':i+1} for i,name in enumerate(REQUIRED)]}
    pr.update(overrides)
    return pr

class MergeQueueTests(unittest.TestCase):
    def reasons(self,**kwargs): return evaluate(candidate(**kwargs),A)['blockers']
    def test_even_green_is_only_candidate(self):
        row=evaluate(candidate(),A)
        self.assertEqual(['HUMAN_DIFF_AND_DEVICE_EVIDENCE_REVIEW'],row['blockers'])
        self.assertFalse(row['merge_permitted'])
    def test_bot_pr_approval_not_hidden_by_dispatch(self):
        pr=candidate(title='data: static')
        pr['runs'].append({'name':REQUIRED[0],'event':'pull_request','head_sha':B,
                           'status':'completed','conclusion':'action_required'})
        reasons=evaluate(pr,A)['blockers']
        self.assertIn('BOT_PR_APPROVAL_PENDING:'+REQUIRED[0],reasons)
        self.assertIn('SOURCE_FRESHNESS_REVIEW_REQUIRED',reasons)
    def test_actual_failure_blocks(self):
        p=candidate();p['runs'][0]['conclusion']='failure'
        self.assertIn('REQUIRED_CI_FAILED:'+REQUIRED[0],evaluate(p,A)['blockers'])
    def test_old_ci_sha_does_not_pass(self):
        p=candidate();p['runs'][0]['head_sha']='c'*40
        r=evaluate(p,A)['blockers']
        self.assertIn('STALE_CI_SHA',r)
        self.assertIn('MISSING_REQUIRED_CI:'+REQUIRED[0],r)
    def test_stale_baseline(self):
        self.assertIn('STALE_CANDIDATE_BASE',self.reasons(candidate_base_sha='c'*40))
    def test_dirty_nested(self):
        r=self.reasons(base={'ref':'review/v1'},mergeable_state='dirty')
        self.assertIn('STACKED_REVIEW_BRANCH',r)
        self.assertIn('MERGEABILITY_NOT_VERIFIED',r)
    def test_missing_checks_fail_closed(self):
        self.assertEqual(7,len([r for r in self.reasons(runs=[]) if r.startswith('MISSING_REQUIRED_CI:')]))
    def test_retry_does_not_preserve_old_failure(self):
        p=candidate();p['runs'][0]['conclusion']='failure'
        p['runs'].append({**p['runs'][0],'id':99,'run_attempt':2,'conclusion':'success'})
        self.assertNotIn('REQUIRED_CI_FAILED:'+REQUIRED[0],evaluate(p,A)['blockers'])
    def test_other_workflow_fails(self):
        p=candidate();p['runs'].append({'name':'CodeQL V438','head_sha':B,'conclusion':'failure'})
        self.assertIn('ADDITIONAL_CI_FAILED:CodeQL V438',evaluate(p,A)['blockers'])
    def test_cross_project_blocked(self):
        with self.assertRaises(ValueError): audit({'repository':'wlghks24/android-vehicle-aio','main_sha':A,'prs':[]})
    def test_duplicate_numbers_blocked(self):
        with self.assertRaises(ValueError): audit({'repository':'wlghks24/-tcg-grader','main_sha':A,'prs':[candidate(),candidate()]})
    def test_bool_id_not_accepted(self):
        with self.assertRaises(ValueError): evaluate(candidate(number=True),A)
    def test_cli_no_write(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'snapshot.json'
            p.write_text(json.dumps({'repository':'wlghks24/-tcg-grader','main_sha':A,'prs':[candidate()]}))
            buf=io.StringIO()
            with redirect_stdout(buf): self.assertEqual(main(['--snapshot',str(p)]),0)
            self.assertEqual(1,json.loads(buf.getvalue())['total'])
            self.assertEqual(['snapshot.json'],[x.name for x in Path(temp).iterdir()])

if __name__=='__main__': unittest.main()
