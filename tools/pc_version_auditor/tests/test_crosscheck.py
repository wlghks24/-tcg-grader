"""Adversarial regression: 3-pass audits must block progress and promotion."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc_auditor'))
import audit
import crosscheck


def git(repo, *args):
    return subprocess.run(['git', *args], cwd=repo, capture_output=True,
                          check=True).stdout.decode('utf-8').strip()


class SkepticalGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='tcg-crosscheck-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base/'source'
        self.repo.mkdir()
        git(self.repo,'init','-q')
        git(self.repo,'config','user.email','test@example.invalid')
        git(self.repo,'config','user.name','Cross Test')
        (self.repo/'V001_init.py').write_text(
            'def ok(row):\n    return bool(row.get("verified",False))\n',encoding='utf-8')
        (self.repo/'V101_helper.py').write_text('def x():\n    return 1\n',encoding='utf-8')
        (self.repo/'V201_guide.md').write_text('# V201 hint only\n',encoding='utf-8')
        e = self.repo/'execution'/'evidence'
        e.mkdir(parents=True)
        (e/'version_review_findings_v001_v205.json').write_text(json.dumps({
            'findings':[{'id':'W001-F015', 'first_observed_version':1,
                         'state':'OPEN_SUCCESSOR_REQUIRED','severity':'P0',
                         'summary':'unverified protection contract'}]
        }),encoding='utf-8')
        git(self.repo,'add','.')
        git(self.repo,'commit','-qm','V001 and V201 initial, not releases')
        self.out = self.base/'reports'

    def _report(self):
        return next(self.out.iterdir())

    def test_3_independent_passes_before_each_window_and_no_release_approval(self):
        result=audit.run_audit(self.repo,self.out,latest=205,auto_review=True)
        self.assertEqual(3,result['completed_windows'])
        self.assertTrue(result['all_completed_windows_rereviewed'])
        self.assertFalse(result['auto_release_or_merge_allowed'])
        self.assertFalse(result['source_review_complete'])
        self.assertEqual('THREE_PASS_FAIL_CLOSED_V4',result['mandatory_crosscheck_policy'])
        for start,end in ((1,100),(101,200),(201,205)):
            receipt=audit.read_checkpoint(self._report()/f'crosscheck_V{start:04d}_V{end:04d}.json')
            self.assertTrue(receipt['next_window_audit_allowed'])
            self.assertFalse(receipt['release_or_patch_approved'])
            self.assertEqual(3,len(receipt['gates']))
            self.assertTrue(all(v=='PASS' for v in receipt['gates'].values()))
            self.assertEqual('AUDIT_RECORD_CROSSCHECKED_NOT_VERSION_CERTIFIED',receipt['state'])
        packet=audit.read_checkpoint(self._report()/'approval_packet.json')
        self.assertEqual('NOT_APPROVED_HANDOFF_ONLY',packet['status'])
        self.assertEqual('STATIC_CHECKED_HUMAN_RE_REVIEW_MISSING',packet['mandatory_three_pass_gate'])
        review=audit.read_checkpoint(self._report()/'independent_patch_review.json')
        self.assertFalse(review['can_automerge_or_promote'])
        self.assertEqual('NOT_RUN',review['human_re_review'])
        self.assertEqual('',git(self.repo,'status','--porcelain'))

    def test_forged_checkpoint_and_recomputed_own_sha_still_blocked(self):
        audit.run_audit(self.repo,self.out,205,stop_after=1)
        path=self._report()/'V0001_V0100.json'
        data=audit.read_checkpoint(path)
        data['slots'][0]['status']='VERIFIED_BY_AI'
        data['checkpoint_sha256']=audit.digest({k:v for k,v in data.items()
                                                if k != 'checkpoint_sha256'})
        audit.atomic_json(path,data)
        with self.assertRaisesRegex(audit.AuditError,'window_first_pass_reconstruction_disagrees'):
            audit.run_audit(self.repo,self.out,205,resume=True)
        self.assertFalse((self._report()/'V0101_V0200.json').exists())

    def test_forged_code_map_and_updated_seal_independently_detected(self):
        audit.run_audit(self.repo,self.out,205,stop_after=1)
        root=self._report()
        data=audit.read_checkpoint(root/'code_map.json')
        data['risk_hints']=[]
        audit.atomic_json(root/'code_map.json',data)
        seal=audit.read_checkpoint(root/'code_map_hash.json')
        seal['sha256']=audit.digest(data)
        audit.atomic_json(root/'code_map_hash.json',seal)
        with self.assertRaisesRegex(audit.AuditError,'crosscheck_code_map_disagrees_with_git'):
            audit.run_audit(self.repo,self.out,205,resume=True)
        self.assertFalse((root/'V0101_V0200.json').exists())

    def test_window_review_receipt_forgery_blocks_resume(self):
        audit.run_audit(self.repo,self.out,205,stop_after=1)
        report=self._report()
        path=report/'crosscheck_V0001_V0100.json'
        row=audit.read_checkpoint(path)
        row['gates']['third_pass_adversarial_noncertification_review']='PASS_BY_FAKE_REVIEW'
        row['review_receipt_sha256']=audit.digest({k:v for k,v in row.items()
                                                  if k != 'review_receipt_sha256'})
        audit.atomic_json(path,row)
        with self.assertRaisesRegex(audit.AuditError,'window_crosscheck_receipt_changed_or_forged'):
            audit.run_audit(self.repo,self.out,205,resume=True)
        self.assertFalse((report/'V0101_V0200.json').exists())

    def test_independent_gate_fails_first_window_before_next_written(self):
        with mock.patch.object(crosscheck,'verify_window',side_effect=audit.AuditError('SECOND_REVIEW_HOLD')):
            with self.assertRaisesRegex(audit.AuditError,'SECOND_REVIEW_HOLD'):
                audit.run_audit(self.repo,self.out,205)
        report=self._report()
        self.assertFalse((report/'V0101_V0200.json').exists())
        self.assertFalse((report/'summary.json').exists())
        self.assertFalse((report/'approval_packet.json').exists())

    def test_resume_after_one_review_rechecks_and_works(self):
        first=audit.run_audit(self.repo,self.out,205,stop_after=1)
        self.assertEqual(1,first['completed_windows'])
        second=audit.run_audit(self.repo,self.out,205,resume=True,auto_review=True)
        self.assertEqual(3,second['completed_windows'])
        self.assertEqual(3,len(list(self._report().glob('crosscheck_V*.json'))))
        self.assertTrue(second['all_completed_windows_rereviewed'])

    def test_unrelated_code_edit_rejected_in_independent_ast_review(self):
        source=b'def sample(r):\n    return bool(r.get("verified"))\n'
        unrelated=b'def sample(r):\n    print("surprise")\n    return (r.get("verified") is True)\n'
        with self.assertRaisesRegex(audit.AuditError,'candidate_second_pass_unrelated_code_changed'):
            crosscheck.re_review_candidate(source,unrelated,number=1)

    def test_all_truthy_nonliteral_values_are_negative(self):
        source=b'def sample(r):\n    return bool(r.get("verified"))\n'
        patched=b'def sample(r):\n    return (r.get("verified") is True)\n'
        checked=crosscheck.re_review_candidate(source,patched,number=1)
        self.assertEqual(11,checked['negative_input_count'])
        self.assertEqual('PASS',checked['structural_ast_recheck'])
        self.assertFalse(checked['promote_allowed'])
        self.assertEqual('NOT_PERFORMED',checked['human_semantic_review'])

    def test_partial_100_slot_audit_blocks_candidate_stage_entirely(self):
        result=audit.run_audit(self.repo,self.out,205,stop_after=1,auto_review=True)
        self.assertEqual(1,result['completed_windows'])
        self.assertIsNone(result['candidate_validation'])
        self.assertTrue(result['candidate_stage_deferred_until_all_windows_pass'])
        report=self._report()
        self.assertFalse((report/'remediation_plan.json').exists())
        self.assertFalse((report/'approval_packet.json').exists())
        final=audit.run_audit(self.repo,self.out,205,resume=True,auto_review=True)
        self.assertEqual(3,final['completed_windows'])
        self.assertFalse(final['candidate_stage_deferred_until_all_windows_pass'])
        self.assertTrue((report/'approval_packet.json').exists())

    def test_tampered_remediation_plan_does_not_get_silently_overwritten(self):
        audit.run_audit(self.repo,self.out,205,auto_review=True)
        path=self._report()/'remediation_plan.json'
        row=audit.read_checkpoint(path)
        row['status']='APPROVED_BY_ATTACKER'
        audit.atomic_json(path,row)
        with self.assertRaisesRegex(audit.AuditError,'existing_remediation_plan_disagrees_with_git'):
            audit.run_audit(self.repo,self.out,205,resume=True,auto_review=True)
        self.assertEqual('APPROVED_BY_ATTACKER',audit.read_checkpoint(path)['status'])
        self.assertFalse(audit.read_checkpoint(self._report()/'approval_packet.json')['status'].startswith('APPROVED'))

    def test_forged_skill_selection_record_is_not_silently_replaced(self):
        audit.run_audit(self.repo,self.out,205,auto_review=True)
        path=self._report()/'skills_applied.json'
        skill=audit.read_checkpoint(path)
        skill['external_skill_installation']=True
        audit.atomic_json(path,skill)
        with self.assertRaisesRegex(audit.AuditError,'registered_skills_report_disagrees_with_git'):
            audit.run_audit(self.repo,self.out,205,resume=True,auto_review=True)
        self.assertEqual('NOT_APPROVED_HANDOFF_ONLY',
                         audit.read_checkpoint(self._report()/'approval_packet.json')['status'])

    def test_tampered_independent_review_blocks_packet_rewrite(self):
        audit.run_audit(self.repo,self.out,205,auto_review=True)
        path=self._report()/'independent_patch_review.json'
        review=audit.read_checkpoint(path)
        review['can_automerge_or_promote']=True
        audit.atomic_json(path,review)
        with self.assertRaisesRegex(audit.AuditError,'existing_review_or_approval_packet_disagrees'):
            audit.run_audit(self.repo,self.out,205,resume=True,auto_review=True)
        self.assertEqual('NOT_APPROVED_HANDOFF_ONLY',
                         audit.read_checkpoint(self._report()/'approval_packet.json')['status'])

    def test_tampered_approval_packet_not_silently_replaced(self):
        audit.run_audit(self.repo,self.out,205,auto_review=True)
        path=self._report()/'approval_packet.json'
        packet=audit.read_checkpoint(path)
        packet['status']='APPROVED_FAKE'
        audit.atomic_json(path,packet)
        with self.assertRaisesRegex(audit.AuditError,'existing_review_or_approval_packet_disagrees'):
            audit.run_audit(self.repo,self.out,205,resume=True,auto_review=True)

    def test_no_proposal_does_not_fake_a_release_pass(self):
        (self.repo/'V001_init.py').write_text('def ok(row):\n    return row.get("verified") is True\n')
        git(self.repo,'add','.')
        git(self.repo,'commit','-qm','strict, still unreviewed')
        output=audit.run_audit(self.repo,self.out,205,auto_review=True)
        self.assertEqual(0,output['candidate_validation']['validated_static_candidates'])
        self.assertEqual('HOLD_MANUAL_SEMANTIC_REVIEW_AND_CURRENT_HEAD_CI',output['next_stage_gate'])
        self.assertEqual([],audit.read_checkpoint(self._report()/'independent_patch_review.json')['reviewed_candidates'])

if __name__ == '__main__':
    unittest.main()
