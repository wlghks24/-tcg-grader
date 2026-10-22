"""Exact source/sync proof and tamper rejection, independent of device evidence."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import sync_v376_successor_test_support as sync
ROOT=Path(__file__).resolve().parents[2]
CP='TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V646.json'
class SuccessorV646Tests(unittest.TestCase):
    def test_exact_source_lineage(self):
        sync.assert_v645_feature_successor(self)
        sync.assert_v646_feature_successor(self)

    def test_new_generation_has_exact_candidate_and_digest(self):
        c=json.loads((ROOT/CP).read_text())
        d=json.loads((ROOT/c['delta_snapshot']).read_text())
        r=json.loads((ROOT/c['receiver_receipt']).read_text())
        prior=json.loads((ROOT/c['prior_contract']).read_text())
        pd=json.loads((ROOT/c['prior_delta_snapshot']).read_text())
        candidate=c['candidate_sync'];base=candidate['base_main_sha'];head=candidate['candidate_commit']
        self.assertEqual(head,sync.V646_FEATURE_PROOF['candidate_commit'])
        self.assertEqual(base,sync.V645_FEATURE_PROOF['base_commit'])
        watch=c['freshness_watch'];exact=set(watch['exact_paths']);excluded=set(watch['exclude_paths'])
        def watched(a,b):
            names=subprocess.check_output(['git','diff','--name-only',a,b],cwd=ROOT,text=True).splitlines()
            return sorted(n for n in names if n not in excluded and n in exact)
        self.assertEqual(candidate['watched_paths'],watched(base,head))
        self.assertEqual([],watched(head,'HEAD'))
        files={CP,c['delta_snapshot'],c['receiver_receipt'],c['verification_test']}
        self.assertEqual(files,set(candidate['generation_files']))
        self.assertTrue(files<=excluded)
        self.assertTrue(candidate['requires_exact_watched_path_match'])
        self.assertTrue(candidate['post_merge_coverage_allowed'])
        digest=hashlib.sha256(json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,d['lesson_digest_sha256'])
        self.assertEqual(digest,r['delta_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'],d['prior_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'],r['prior_lesson_digest_sha256'])
        self.assertEqual([x['lesson_id'] for x in d['lessons']],r['accepted_lesson_ids'])
        self.assertEqual(prior['current_required_lesson_count']+len(d['lessons']),c['current_required_lesson_count'])
        self.assertEqual(d['source_main_sha'],base)
        self.assertEqual(r['source_main_sha'],base)
        self.assertEqual('SYNCED_VERIFIED',r['status'])
        self.assertFalse(r['verification']['physical_tablet_runtime_verified'])
        self.assertFalse(r['verification']['physical_drive_readback_verified'])
        self.assertFalse(d['share_policy']['cloud_upload_enabled'])
        self.assertFalse(d['share_policy']['non_core_grading_enabled'])

    def test_current_ui_tampering_cannot_delegate(self):
        original=Path.read_bytes
        name='index.html'
        def changed(p):return original(p)+b'\n# unreviewed' if p==ROOT/name else original(p)
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaises(AssertionError):sync.assert_v646_feature_successor(self)
            with self.assertRaises(AssertionError):sync.assert_v645_feature_successor(self)
            self.assertEqual([name],sync.preserve_reviewed_v645_feature_scope([name],sync.V645_FEATURE_PROOF['base_commit']))

    def test_forged_v646_proof_is_rejected(self):
        original=sync._read
        def forged(p):
            data=original(p)
            if str(p).endswith('feature_catalog_successor_v646.json'):data['deployment_allowed']=True
            return data
        with patch.object(sync,'_read',side_effect=forged):
            with self.assertRaises(AssertionError):sync.assert_v646_feature_successor(self)

    def test_historical_changes_and_non_head_checks_remain_visible(self):
        name='index.html'
        self.assertEqual([name],sync.preserve_reviewed_v645_feature_scope([name],'14a509e5e594711be8b851f1942f2270cb1b3d69'))
        self.assertEqual([name],sync.preserve_reviewed_v645_feature_scope([name],sync.V645_FEATURE_PROOF['base_commit'],head=sync.V645_FEATURE_PROOF['base_commit']))
