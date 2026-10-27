"""Exact dock successor: reject altered bytes, divergent ancestry and forged flags."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parents[2]


class DockSuccessorTests(unittest.TestCase):
    def test_exact_candidate_and_v652_delegation(self):
        sync.assert_v878_dock_successor(self)
        sync.assert_v652_successor(self)
        self.assertEqual([], sync.preserve_reviewed_v878_dock_scope(
            ['feature_category_nav.js'], sync.V878_DOCK_PROOF['base_commit']))

    def test_each_live_pin_is_rechecked_after_history_cache_warmup(self):
        sync.assert_v878_dock_successor(self)
        original = Path.read_bytes
        for name in (sync.V878_DOCK_PROOF['reviewed_sha256'] |
                     sync.V878_DOCK_PROOF['current_verification_sha256']):
            with self.subTest(path=name), patch.object(
                Path, 'read_bytes', lambda p: original(p) + b' unreviewed'
                if p == ROOT / name else original(p)
            ):
                with self.assertRaises(AssertionError):
                    sync.assert_v878_dock_successor(self)
                self.assertEqual(['feature_category_nav.js'],
                    sync.preserve_reviewed_v878_dock_scope(
                        ['feature_category_nav.js'], sync.V878_DOCK_PROOF['base_commit']))

    def test_forged_flags_fail_closed(self):
        original = sync._read
        for flag in ('deployment_allowed', 'physical_tablet_runtime_verified'):
            def forged(path):
                data = original(path)
                if path.name == 'dock_state_successor_v878.json':
                    data = copy.deepcopy(data); data[flag] = True
                return data
            with self.subTest(flag=flag), patch.object(sync, '_read', side_effect=forged):
                with self.assertRaises(AssertionError):
                    sync.assert_v878_dock_successor(self)

    def test_legacy_dock_suite_is_preserved_with_only_root_resolution_changed(self):
        name = 'test_tablet_app_dock_v275.py'
        before = subprocess.check_output([
            'git', 'show', sync.V878_DOCK_PROOF['candidate_commit'] + ':' + name], cwd=ROOT)
        expected = before.replace(b'ROOT = Path(__file__).resolve().parent\n',
                                  b'ROOT = Path(__file__).resolve().parents[2]\n')
        self.assertNotEqual(before, expected)
        self.assertFalse((ROOT / name).exists())
        self.assertEqual(expected, (ROOT / 'execution/tests' / name).read_bytes())
        self.assertIn('execution.tests.test_tablet_app_dock_v275',
                      (ROOT / 'test_tablet_gpt_tcg_grader_sync_v878.py').read_text())

    def test_divergent_head_fails_closed(self):
        original = subprocess.run
        candidate = sync.V878_DOCK_PROOF['candidate_commit']
        def divergent(args, *a, **kw):
            if args == ['git', 'merge-base', '--is-ancestor', candidate, 'HEAD']:
                return subprocess.CompletedProcess(args, 1)
            return original(args, *a, **kw)
        with patch.object(subprocess, 'run', side_effect=divergent):
            with self.assertRaises(AssertionError): sync.assert_v878_dock_successor(self)

    def test_symlinked_receipt_and_source_are_rejected(self):
        original = Path.is_symlink
        for name in ('feature_category_nav.js', '.github/tablet-autonomy/dock_state_successor_v878.json'):
            with self.subTest(path=name), patch.object(
                Path, 'is_symlink', lambda p: p == ROOT / name or original(p)
            ):
                with self.assertRaises(AssertionError): sync.assert_v878_dock_successor(self)

    def test_older_unknown_and_non_head_changes_remain_visible(self):
        name = 'feature_category_nav.js'
        self.assertEqual([name], sync.preserve_reviewed_v878_dock_scope(
            [name], sync.V652_PROOF['base_commit']))
        self.assertEqual(['main', 'unknown.py'], sync.preserve_reviewed_v878_dock_scope(
            ['main', 'unknown.py'], sync.V878_DOCK_PROOF['base_commit']))
        self.assertEqual([name], sync.preserve_reviewed_v878_dock_scope(
            [name], sync.V878_DOCK_PROOF['base_commit'], head=sync.V878_DOCK_PROOF['base_commit']))

    def test_generation_preserves_prior_rules_and_exact_watched_scope(self):
        read = lambda p: json.loads((ROOT / p).read_text())
        cp = 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V878.json'
        c = read(cp); prior = read(c['prior_contract'])
        d = read(c['delta_snapshot']); r = read(c['receiver_receipt'])
        pd = read(c['prior_delta_snapshot']); candidate = c['candidate_sync']
        self.assertEqual(prior['rules'], c['rules'])
        for key in ('exact_paths', 'path_prefixes', 'exclude_paths'):
            self.assertTrue(set(prior['freshness_watch'][key]) <= set(c['freshness_watch'][key]))
        watch = c['freshness_watch']
        def watched(a, b):
            paths = subprocess.check_output(['git','diff','--name-only',a,b],cwd=ROOT,text=True).splitlines()
            return sorted(p for p in paths if p not in watch['exclude_paths'] and
                          (p in watch['exact_paths'] or p.startswith(tuple(watch['path_prefixes']))))
        self.assertEqual(candidate['watched_paths'], watched(candidate['base_main_sha'],candidate['candidate_commit']))
        self.assertEqual([], watched(candidate['candidate_commit'],'HEAD'))
        self.assertEqual(sync.V878_DOCK_PROOF['base_commit'], candidate['base_main_sha'])
        self.assertEqual(sync.V878_DOCK_PROOF['candidate_commit'], candidate['candidate_commit'])
        self.assertEqual({cp,c['delta_snapshot'],c['receiver_receipt'],c['verification_test']},set(candidate['generation_files']))
        self.assertTrue(set(candidate['generation_files']) <= set(watch['exclude_paths']))
        self.assertIs(candidate['requires_exact_watched_path_match'],True)
        self.assertIs(candidate['post_merge_coverage_allowed'],True)
        digest = hashlib.sha256(json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,d['lesson_digest_sha256']); self.assertEqual(digest,r['delta_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'],d['prior_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'],r['prior_lesson_digest_sha256'])
        self.assertEqual([x['lesson_id'] for x in d['lessons']],r['accepted_lesson_ids'])
        self.assertEqual(prior['current_required_lesson_count']+len(d['lessons']),c['current_required_lesson_count'])
        self.assertEqual(candidate['base_main_sha'],d['source_main_sha']);self.assertEqual(d['source_main_sha'],r['source_main_sha'])
        self.assertIs(r['verification']['physical_tablet_runtime_verified'],False)
        self.assertIs(r['verification']['physical_drive_readback_verified'],False)
        self.assertIs(d['share_policy']['cloud_upload_enabled'],False)


if __name__ == '__main__': unittest.main()
