"""Exact lineage/current bytes; tampering must remain visible through old watchers."""
import hashlib,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync
ROOT=Path(__file__).resolve().parents[2]
CP='TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V658.json'

class ContinuousSuccessorTests(unittest.TestCase):
    def test_root_budget_current_guide_and_relocated_regressions_are_preserved(self):
        original='README_v31.md'
        baseline=subprocess.check_output(['git','show','bec299218c6ae78c909c5461fe497dff16f3da56:'+original],cwd=ROOT)
        self.assertEqual('ff1dba5b0472104f84e8d8193f5705c0465aaf4700a7bbef3dd38438b5ac0de8',hashlib.sha256(baseline).hexdigest())
        self.assertEqual(baseline,(ROOT/original).read_bytes())
        moved='test_collection_coverage_completion_v143.py';target=ROOT/'execution/tests'/moved
        prior=subprocess.check_output(['git','show','bec299218c6ae78c909c5461fe497dff16f3da56:'+moved],cwd=ROOT)
        self.assertFalse((ROOT/moved).exists());self.assertFalse(target.is_symlink())
        self.assertEqual(prior,target.read_bytes())
        loader=(ROOT/'test_tablet_gpt_tcg_grader_sync_v658.py').read_text()
        self.assertIn('execution.tests.test_collection_coverage_completion_v143',loader)
        region='test_card_catalog_region_isolation_v317.py'
        self.assertFalse((ROOT/region).exists())
        self.assertEqual(subprocess.check_output(['git','show','7e73d62637a97681830689133ee97df8bae339fe:'+region],cwd=ROOT),(ROOT/'execution/tests'/region).read_bytes())
        def count(ref):
            return len([x for x in subprocess.check_output(['git','ls-tree','-z',ref],cwd=ROOT).split(b'\0') if x])
        self.assertLessEqual(count('HEAD'),count('328782f6b92835c4aab39224bb0c6c5c6b3e0067'))

    def test_exact_source_and_historical_delegation(self):
        for check in (sync.assert_v644_learning_successor,sync.assert_v645_feature_successor,
                      sync.assert_v646_feature_successor,sync.assert_v648_update_successor,
                      sync.assert_v649_update_successor,sync.assert_v650_update_successor,
                      sync.assert_v651_update_successor,sync.assert_v658_successor):check(self)

    def test_immutable_history_is_reused_without_caching_live_validation(self):
        checks=(sync.assert_v644_learning_successor,sync.assert_v646_feature_successor,sync.assert_v648_update_successor,
                sync.assert_v649_update_successor,sync.assert_v650_update_successor,
                sync.assert_v651_update_successor,sync.assert_v652_successor,
                sync.assert_v653_successor,sync.assert_v654_successor,sync.assert_v658_successor)
        for check in checks:check(self)
        before=sync._v646_immutable_commit_evidence.cache_info()
        for check in checks:check(self)
        after=sync._v646_immutable_commit_evidence.cache_info()
        self.assertEqual(before.misses,after.misses)
        self.assertGreater(after.hits,before.hits)
        original=Path.read_bytes
        target=ROOT/'execution/tests/test_info_filters_v655.py'
        with patch.object(Path,'read_bytes',lambda p:original(p)+b' unreviewed' if p==target else original(p)):
            with self.assertRaises(AssertionError):sync.assert_v658_successor(self)

    def test_capsule_keeps_rules_watches_digest_and_exact_candidate(self):
        c=json.loads((ROOT/CP).read_text());d=json.loads((ROOT/c['delta_snapshot']).read_text())
        r=json.loads((ROOT/c['receiver_receipt']).read_text());prior=json.loads((ROOT/c['prior_contract']).read_text())
        pd=json.loads((ROOT/c['prior_delta_snapshot']).read_text());candidate=c['candidate_sync']
        self.assertEqual(sync.V658_PROOF['base_commit'],candidate['base_main_sha'])
        self.assertEqual(sync.V658_PROOF['candidate_commit'],candidate['candidate_commit'])
        def watched(a,b):
            names=subprocess.check_output(['git','diff','--name-only',a,b],cwd=ROOT,text=True).splitlines()
            w=c['freshness_watch'];return sorted(n for n in names if n not in w['exclude_paths'] and (n in w['exact_paths'] or n.startswith(tuple(w['path_prefixes']))))
        self.assertEqual(candidate['watched_paths'],watched(candidate['base_main_sha'],candidate['candidate_commit']))
        self.assertEqual([],sync.preserve_reviewed_v658_scope(watched(candidate['candidate_commit'],'HEAD'),candidate['candidate_commit']))
        self.assertEqual({CP,c['delta_snapshot'],c['receiver_receipt'],c['verification_test']},set(candidate['generation_files']))
        self.assertLessEqual(set(candidate['generation_files']),set(c['freshness_watch']['exclude_paths']))
        self.assertTrue(candidate['requires_exact_watched_path_match']);self.assertTrue(candidate['post_merge_coverage_allowed'])
        self.assertEqual(prior['rules'],c['rules'])
        for key in ('exact_paths','path_prefixes','exclude_paths'):
            self.assertLessEqual(set(prior['freshness_watch'][key]),set(c['freshness_watch'][key]))
        digest=hashlib.sha256(json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,d['lesson_digest_sha256']);self.assertEqual(digest,r['delta_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'],d['prior_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'],r['prior_lesson_digest_sha256'])
        self.assertEqual([x['lesson_id'] for x in d['lessons']],r['accepted_lesson_ids'])
        self.assertEqual(prior['current_required_lesson_count']+len(d['lessons']),c['current_required_lesson_count'])
        self.assertEqual(candidate['base_main_sha'],d['source_main_sha']);self.assertEqual(d['source_main_sha'],r['source_main_sha'])
        self.assertFalse(r['verification']['physical_tablet_runtime_verified']);self.assertFalse(r['verification']['physical_drive_readback_verified'])
        self.assertFalse(d['share_policy']['cloud_upload_enabled']);self.assertFalse(d['share_policy']['device_local_runtime_memory_overwritten'])

    def test_each_pin_and_public_watch_rejects_modified_bytes_after_cache_warmup(self):
        sync.assert_v658_successor(self);original=Path.read_bytes
        for name,digest in sync.V658_PROOF['reviewed_sha256'].items():
            if name in sync.V658_PROOF['reviewed_sha256'] and sync.V658_PROOF['reviewed_sha256'][name] is None:
                original_exists=Path.exists
                with patch.object(Path,'exists',lambda p:True if p==ROOT/name else original_exists(p)):
                    with self.assertRaises(AssertionError):sync.assert_v658_successor(self)
                continue
            def changed(path):return original(path)+b'\n# unreviewed' if path==ROOT/name else original(path)
            with self.subTest(path=name),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(AssertionError):sync.assert_v658_successor(self)
                self.assertEqual([name],sync.preserve_reviewed_v658_scope([name],sync.V658_PROOF['base_commit']))
                self.assertEqual([name],sync.preserve_reviewed_v525_grade_scope([name],sync.V658_PROOF['base_commit']))

    def test_forged_flags_and_non_head_scope_fail_closed(self):
        original=sync._read
        def forged(path):
            data=original(path)
            if str(path).endswith('verification_repair_successor_v658.json'):data['physical_tablet_runtime_verified']=True
            return data
        with patch.object(sync,'_read',side_effect=forged):
            with self.assertRaises(AssertionError):sync.assert_v658_successor(self)
        name=next(iter(sync.V658_PROOF['reviewed_sha256']))
        self.assertEqual([name],sync.preserve_reviewed_v658_scope([name],sync.V658_PROOF['base_commit'],head=sync.V658_PROOF['base_commit']))
        self.assertEqual(['unknown.py'],sync.preserve_reviewed_v658_scope(['unknown.py'],sync.V658_PROOF['base_commit']))
