"""Exact lineage/current bytes; tampering must remain visible through old watchers."""
import hashlib,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync
ROOT=Path(__file__).resolve().parents[2]
CP='TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V653.json'

class ContinuousSuccessorTests(unittest.TestCase):
    def test_exact_source_and_historical_delegation(self):
        for check in (sync.assert_v644_learning_successor,sync.assert_v645_feature_successor,
                      sync.assert_v646_feature_successor,sync.assert_v648_update_successor,
                      sync.assert_v649_update_successor,sync.assert_v650_update_successor,
                      sync.assert_v651_update_successor,sync.assert_v653_successor):check(self)

    def test_capsule_keeps_rules_watches_digest_and_exact_candidate(self):
        c=json.loads((ROOT/CP).read_text());d=json.loads((ROOT/c['delta_snapshot']).read_text())
        r=json.loads((ROOT/c['receiver_receipt']).read_text());prior=json.loads((ROOT/c['prior_contract']).read_text())
        pd=json.loads((ROOT/c['prior_delta_snapshot']).read_text());candidate=c['candidate_sync']
        self.assertEqual(sync.V653_PROOF['base_commit'],candidate['base_main_sha'])
        self.assertEqual(sync.V653_PROOF['candidate_commit'],candidate['candidate_commit'])
        def watched(a,b):
            names=subprocess.check_output(['git','diff','--name-only',a,b],cwd=ROOT,text=True).splitlines()
            w=c['freshness_watch'];visible=sorted(n for n in names if n not in w['exclude_paths'] and (n in w['exact_paths'] or n.startswith(tuple(w['path_prefixes']))))
            return sync.preserve_reviewed_v654_scope(visible,a) if b=='HEAD' else visible
        self.assertEqual(candidate['watched_paths'],watched(candidate['base_main_sha'],candidate['candidate_commit']))
        self.assertEqual([],watched(candidate['candidate_commit'],'HEAD'))
        self.assertEqual({CP,c['delta_snapshot'],c['receiver_receipt'],c['verification_test']},set(candidate['generation_files']))
        self.assertTrue(set(candidate['generation_files'])<=set(c['freshness_watch']['exclude_paths']))
        self.assertTrue(candidate['requires_exact_watched_path_match']);self.assertTrue(candidate['post_merge_coverage_allowed'])
        self.assertEqual(prior['rules'],c['rules'])
        for key in ('exact_paths','path_prefixes','exclude_paths'):
            self.assertTrue(set(prior['freshness_watch'][key])<=set(c['freshness_watch'][key]))
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
        sync.assert_v653_successor(self);original=Path.read_bytes
        for name,digest in sync.V653_PROOF['reviewed_sha256'].items():
            if digest is None:continue
            if name in sync.V653_PROOF['reviewed_sha256'] and sync.V653_PROOF['reviewed_sha256'][name] is None:
                original_exists=Path.exists
                with patch.object(Path,'exists',lambda p:True if p==ROOT/name else original_exists(p)):
                    with self.assertRaises(AssertionError):sync.assert_v653_successor(self)
                continue
            def changed(path):return original(path)+b'\n# unreviewed' if path==ROOT/name else original(path)
            with self.subTest(path=name),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(AssertionError):sync.assert_v653_successor(self)
                self.assertEqual([name],sync.preserve_reviewed_v653_scope([name],sync.V653_PROOF['base_commit']))
                self.assertEqual([name],sync.preserve_reviewed_v525_grade_scope([name],sync.V653_PROOF['base_commit']))

    def test_relocated_learning_suite_is_byte_identical(self):
        """V653 relocation is immutable; only separately verified V666 may alter its live bytes."""
        name = 'test_tablet_learning_progress.py'
        relocated = 'execution/tests/' + name
        v653_origin = subprocess.check_output(
            ['git','show',sync.V653_PROOF['base_commit']+':'+name],cwd=ROOT)
        v653_moved = subprocess.check_output(
            ['git','show',sync.V653_PROOF['candidate_commit']+':'+relocated],cwd=ROOT)
        self.assertEqual(v653_origin,v653_moved, 'V653 original relocation must remain byte-identical')
        self.assertFalse((ROOT/name).exists())
        target = ROOT / relocated
        self.assertFalse(target.is_symlink())
        v666_start = subprocess.check_output(
            ['git','show',sync.V666_PROOF['base_commit']+':'+relocated],cwd=ROOT)
        self.assertEqual(v653_moved,v666_start, 'No intervening unreviewed edits')
        self.assertEqual(hashlib.sha256(v666_start).hexdigest(),
                         sync.V666_PROOF['baseline_sha256'][relocated])
        v666_reviewed = subprocess.check_output(
            ['git','show',sync.V666_PROOF['candidate_commit']+':'+relocated],cwd=ROOT)
        self.assertEqual(hashlib.sha256(v666_reviewed).hexdigest(),
                         sync.V666_PROOF['reviewed_sha256'][relocated])
        sync.assert_v666_successor(self)
        self.assertEqual(v666_reviewed,target.read_bytes(),
                         'Live fixture must equal exact V666 candidate, not an unreviewed edit')
        self.assertFalse(sync.V666_PROOF['physical_tablet_runtime_verified'])
        self.assertFalse(sync.V666_PROOF['deployment_allowed'])

    def test_relocated_learning_suite_rejects_live_tampering(self):
        target = ROOT / 'execution/tests/test_tablet_learning_progress.py'
        original = Path.read_bytes
        def tampered(path):
            data = original(path)
            return data + b' unreviewed' if path == target else data
        with patch.object(Path,'read_bytes',tampered):
            with self.assertRaises(AssertionError):
                self.test_relocated_learning_suite_is_byte_identical()

    def test_forged_flags_and_non_head_scope_fail_closed(self):
        original=sync._read
        def forged(path):
            data=original(path)
            if str(path).endswith('workspace_evidence_successor_v653.json'):data['physical_tablet_runtime_verified']=True
            return data
        with patch.object(sync,'_read',side_effect=forged):
            with self.assertRaises(AssertionError):sync.assert_v653_successor(self)
        name=next(iter(sync.V653_PROOF['reviewed_sha256']))
        self.assertEqual([name],sync.preserve_reviewed_v653_scope([name],sync.V653_PROOF['base_commit'],head=sync.V653_PROOF['base_commit']))
        self.assertEqual(['unknown.py'],sync.preserve_reviewed_v653_scope(['unknown.py'],sync.V653_PROOF['base_commit']))
