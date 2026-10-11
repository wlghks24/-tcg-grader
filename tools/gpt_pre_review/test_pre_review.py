import unittest
from pre_review import CRITICAL_CI, WEIGHTS, evaluate

SHA = 'a' * 40
BASE = 'b' * 40

def template():
    gates = {name: {'status':'pass','head_sha':SHA,'proof':'checked current SHA locally'} for name in WEIGHTS}
    return {
        'pr': {'number':999,'head_sha':SHA,'base_sha':BASE,'mergeable':True,
               'scope_verification':'diff_and_paths_checked','changed_paths':[]},
        'reviewed_head_sha':SHA, 'gates':gates,
        'unresolved_high_findings':[], 'unresolved_review_threads':0,
        'ci': {'head_sha':SHA,'runs':[
            {'name':x,'status':'completed','conclusion':'success','head_sha':SHA}
            for x in CRITICAL_CI
        ]}
    }

class OfflineReviewTest(unittest.TestCase):
    def test_score_total(self): self.assertEqual(sum(WEIGHTS.values()),100)
    def test_all_submitted_is_only_candidate(self):
        r=evaluate(template())
        self.assertEqual(r['verdict'],'GPT_PREAPPROVAL_CANDIDATE')
        self.assertEqual(r['formal_github_approval'],'NOT_ASSESSED')
    def test_old_head_blocked(self):
        d=template();d['reviewed_head_sha']=BASE
        self.assertEqual(evaluate(d)['verdict'],'BLOCKED_STALE_HEAD')
    def test_old_ci_is_block(self):
        d=template();d['ci']['runs'][0]['head_sha']=BASE
        self.assertEqual(evaluate(d)['verdict'],'BLOCKED')
    def test_failed_alignment_blocks_pr640(self):
        d=template();d['ci']['runs'].append({'name':'Tablet GPT TCG Grader Main Alignment','status':'completed','conclusion':'failure','head_sha':SHA})
        self.assertEqual(evaluate(d)['verdict'],'BLOCKED')
    def test_missing_codeql_holds(self):
        d=template();d['ci']['runs']=[x for x in d['ci']['runs'] if x['name']!='CodeQL V438']
        self.assertEqual(evaluate(d)['verdict'],'HOLD')
    def test_sync_path_needs_gate(self):
        d=template();d['pr']['changed_paths']=['card_identity_recognition.py']
        self.assertEqual(evaluate(d)['verdict'],'HOLD')
        d['gates']['tablet_alignment']={'status':'pass','head_sha':SHA,'proof':'tested'}
        self.assertEqual(evaluate(d)['verdict'],'GPT_PREAPPROVAL_CANDIDATE')
    def test_workflow_path_requires_permission_and_manifest(self):
        d=template();d['pr']['changed_paths']=['.github/workflows/guard.yml']
        self.assertEqual(evaluate(d)['verdict'],'HOLD')
        for x in ('integrity_manifest','workflow_permissions'):
            d['gates'][x]={'status':'pass','head_sha':SHA,'proof':'verified'}
        self.assertEqual(evaluate(d)['verdict'],'GPT_PREAPPROVAL_CANDIDATE')
    def test_manifest_mismatch_blocks(self):
        d=template();d['pr']['changed_paths']=['integrity_manifest.json']
        d['gates']['integrity_manifest']={'status':'pass','head_sha':BASE,'proof':'old'}
        self.assertEqual(evaluate(d)['verdict'],'BLOCKED')
    def test_unresolved_thread_blocks(self):
        d=template();d['unresolved_review_threads']=1
        self.assertEqual(evaluate(d)['verdict'],'BLOCKED')
    def test_review_not_approval(self):
        d=template();d['pr']['merged']=True
        self.assertFalse(evaluate(d)['reported_approved_review_at_head'])
    def test_false_claim_of_pass_no_proof(self):
        d=template();d['gates']['targeted_tests']['proof']=''
        self.assertEqual(evaluate(d)['verdict'],'HOLD')
    def test_unknown_base_holds(self):
        d=template();d['pr']['base_sha']=''
        self.assertEqual(evaluate(d)['verdict'],'HOLD')
    def test_high_findings_block(self):
        d=template();d['unresolved_high_findings']=['unresolved CodeQL']
        self.assertEqual(evaluate(d)['verdict'],'BLOCKED')
    def test_merge_conflict_blocks(self):
        d=template();d['pr']['mergeable']=False
        self.assertEqual(evaluate(d)['verdict'],'BLOCKED')
    def test_untrusted_empty_ci_holds(self):
        d=template();d['ci']={'head_sha':SHA,'runs':[]}
        self.assertEqual(evaluate(d)['verdict'],'HOLD')
    def test_invalid_sha_rejected(self):
        d=template();d['pr']['head_sha']='xyz'
        self.assertRaises(ValueError,evaluate,d)

if __name__=='__main__': unittest.main()
