"""Exact current source and append-only evidence for Chinese module recovery."""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parents[2]


class ChinaSuccessorTests(unittest.TestCase):
    def test_exact_current_source_and_candidate_capsule(self):
        sync.assert_v645_feature_successor(self)
        sync.assert_v646_feature_successor(self)
        sync.assert_v648_update_successor(self)
        sync.assert_v649_update_successor(self)
        sync.assert_v650_update_successor(self)
        path = 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V650.json'
        c = json.loads((ROOT / path).read_text())
        d = json.loads((ROOT / c['delta_snapshot']).read_text())
        r = json.loads((ROOT / c['receiver_receipt']).read_text())
        prior = json.loads((ROOT / c['prior_contract']).read_text())
        pd = json.loads((ROOT / c['prior_delta_snapshot']).read_text())
        candidate = c['candidate_sync']
        self.assertEqual(sync.V650_UPDATE_PROOF['base_commit'], candidate['base_main_sha'])
        self.assertEqual(sync.V650_UPDATE_PROOF['candidate_commit'], candidate['candidate_commit'])
        exact = set(c['freshness_watch']['exact_paths'])
        excluded = set(c['freshness_watch']['exclude_paths'])
        def watched(a, b):
            names = subprocess.check_output(['git', 'diff', '--name-only', a, b], cwd=ROOT, text=True).splitlines()
            return sorted(name for name in names if name in exact and name not in excluded)
        self.assertEqual(candidate['watched_paths'], watched(candidate['base_main_sha'], candidate['candidate_commit']))
        self.assertEqual([], watched(candidate['candidate_commit'], 'HEAD'))
        self.assertEqual({path, c['delta_snapshot'], c['receiver_receipt'], c['verification_test']}, set(candidate['generation_files']))
        self.assertTrue(set(candidate['generation_files']) <= excluded)
        self.assertTrue(candidate['requires_exact_watched_path_match'])
        self.assertTrue(candidate['post_merge_coverage_allowed'])
        digest = hashlib.sha256(json.dumps(d['lessons'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(digest, d['lesson_digest_sha256'])
        self.assertEqual(digest, r['delta_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'], d['prior_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'], r['prior_lesson_digest_sha256'])
        self.assertEqual([row['lesson_id'] for row in d['lessons']], r['accepted_lesson_ids'])
        self.assertEqual(prior['current_required_lesson_count'] + len(d['lessons']), c['current_required_lesson_count'])
        self.assertEqual(candidate['base_main_sha'], d['source_main_sha'])
        self.assertEqual(candidate['base_main_sha'], r['source_main_sha'])
        self.assertFalse(r['verification']['physical_tablet_runtime_verified'])
        self.assertFalse(r['verification']['physical_drive_readback_verified'])
        self.assertFalse(d['share_policy']['cloud_upload_enabled'])

    def test_live_tampering_is_rejected_after_immutable_cache_warmup(self):
        sync.assert_v650_update_successor(self)
        original = Path.read_bytes
        for name in ('execution/tablet_preserved_update.py', 'execution/tests/test_china_preserved_update_v650.py'):
            def changed(path):
                return original(path) + b'\n# unreviewed' if path == ROOT / name else original(path)
            with self.subTest(path=name), patch.object(Path, 'read_bytes', changed):
                for check in (sync.assert_v645_feature_successor, sync.assert_v646_feature_successor,
                              sync.assert_v648_update_successor, sync.assert_v649_update_successor,
                              sync.assert_v650_update_successor):
                    with self.assertRaises(AssertionError):
                        check(self)
                self.assertEqual([name], sync.preserve_reviewed_v650_update_scope([name], sync.V650_UPDATE_PROOF['base_commit']))

    def test_forged_device_flag_and_older_changes_remain_blocked(self):
        original = sync._read
        def forged(path):
            data = original(path)
            if str(path).endswith('preserved_update_successor_v650.json'):
                data['physical_tablet_runtime_verified'] = True
            return data
        with patch.object(sync, '_read', side_effect=forged):
            with self.assertRaises(AssertionError):
                sync.assert_v650_update_successor(self)
        name = 'execution/tablet_preserved_update.py'
        self.assertEqual([name], sync.preserve_reviewed_v650_update_scope([name], sync.V649_UPDATE_PROOF['base_commit']))
        self.assertEqual([name], sync.preserve_reviewed_v650_update_scope([name], sync.V650_UPDATE_PROOF['base_commit'], head=sync.V650_UPDATE_PROOF['base_commit']))
        self.assertEqual(['unknown.py'], sync.preserve_reviewed_v650_update_scope(['unknown.py'], sync.V650_UPDATE_PROOF['base_commit']))

    def test_relocated_parser_suite_is_byte_identical(self):
        name = 'test_update_market_prices_packmagik_v353.py'
        original = subprocess.check_output(['git', 'show', sync.V650_UPDATE_PROOF['base_commit'] + ':' + name], cwd=ROOT)
        self.assertEqual(original, (ROOT / 'execution/tests' / name).read_bytes())
        self.assertFalse((ROOT / name).exists())
