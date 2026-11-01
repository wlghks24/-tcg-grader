"""Exact successor lineage and uncached tamper resistance for PR #954."""
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync


class CatalogImageSuccessorTests(unittest.TestCase):
    def test_exact_candidate_and_historical_live_pins(self):
        sync.assert_v880_successor(self)
        sync.assert_v653_successor(self)
        sync.assert_v652_successor(self)

    def test_every_live_pin_remains_visible_after_warmup(self):
        sync.assert_v880_successor(self)
        original = Path.read_bytes
        for name, digest in sync.V880_PROOF['reviewed_sha256'].items():
            if digest is None:
                exists = Path.exists
                with self.subTest(restored=name), patch.object(Path, 'exists', lambda p: True if p == sync.ROOT/name else exists(p)):
                    with self.assertRaises(AssertionError):
                        sync.assert_v880_successor(self)
                continue
            with self.subTest(path=name), patch.object(Path, 'read_bytes', lambda p: original(p)+b' unreviewed' if p == sync.ROOT/name else original(p)):
                with self.assertRaises(AssertionError):
                    sync.assert_v880_successor(self)
                self.assertEqual([name], sync.preserve_reviewed_v880_scope([name], sync.V880_PROOF['base_commit']))
                self.assertEqual([name], sync.preserve_reviewed_v525_grade_scope([name], sync.V880_PROOF['base_commit']))

    def test_old_v653_pin_is_preserved_and_js_delegation_rejects_tamper(self):
        name = 'tablet_image_library_v1.js'
        self.assertEqual(sync.V653_PROOF['reviewed_sha256'][name], sync.V880_PROOF['baseline_sha256'][name])
        original = Path.read_bytes
        for name in ('tablet_image_library_v1.js', 'tablet_image_library_v1.py', 'execution/tablet_catalog_bridge.py'):
            with self.subTest(path=name), patch.object(Path, 'read_bytes', lambda p: original(p)+b' unreviewed' if p == sync.ROOT/name else original(p)):
                with self.assertRaises(AssertionError):
                    sync.assert_v653_successor(self)

    def test_non_head_unknown_source_and_forged_receipt_fail_closed(self):
        proof = sync.V880_PROOF
        name = 'tablet_image_library_v1.js'
        for source, head in ((proof['base_commit'], proof['candidate_commit']), (proof['candidate_commit'], 'HEAD')):
            self.assertEqual([name], sync.preserve_reviewed_v880_scope([name], source, head))
        self.assertEqual(['unknown.js'], sync.preserve_reviewed_v880_scope(['unknown.js'], proof['base_commit']))
        original = sync._read
        def forged(path):
            data = original(path)
            if str(path).endswith('catalog_image_successor_v880.json'):
                data['deployment_allowed'] = True
            return data
        with patch.object(sync, '_read', forged):
            with self.assertRaises(AssertionError):
                sync.assert_v880_successor(self)
            self.assertEqual([name], sync.preserve_reviewed_v880_scope([name], proof['base_commit']))

    def test_contract_digest_watches_and_safe_transfer(self):
        root = sync.ROOT
        c = json.loads((root/'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V880.json').read_text())
        prior = json.loads((root/c['prior_contract']).read_text())
        d = json.loads((root/c['delta_snapshot']).read_text())
        r = json.loads((root/c['receiver_receipt']).read_text())
        pd = json.loads((root/c['prior_delta_snapshot']).read_text())
        self.assertEqual(prior['rules'], c['rules'])
        for key in ('exact_paths', 'path_prefixes', 'exclude_paths'):
            self.assertTrue(set(prior['freshness_watch'][key]) <= set(c['freshness_watch'][key]))
        dg = hashlib.sha256(json.dumps(d['lessons'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(dg, d['lesson_digest_sha256'])
        self.assertEqual(dg, r['delta_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'], d['prior_lesson_digest_sha256'])
        self.assertEqual(pd['lesson_digest_sha256'], r['prior_lesson_digest_sha256'])
        self.assertEqual([x['lesson_id'] for x in d['lessons']], r['accepted_lesson_ids'])
        self.assertEqual(prior['current_required_lesson_count']+len(d['lessons']), c['current_required_lesson_count'])
        candidate = c['candidate_sync']
        self.assertEqual(sync.V880_PROOF['base_commit'], candidate['base_main_sha'])
        self.assertEqual(sync.V880_PROOF['candidate_commit'], candidate['candidate_commit'])
        self.assertEqual(d['source_main_sha'], candidate['base_main_sha'])
        self.assertEqual(d['source_main_sha'], r['source_main_sha'])
        w = c['freshness_watch']
        def watched(ref):
            names = subprocess.check_output(['git','diff','--no-renames','--name-only',candidate['base_main_sha'],ref], cwd=root, text=True).splitlines()
            return sorted(p for p in names if p not in w['exclude_paths'] and (p in w['exact_paths'] or p.startswith(tuple(w['path_prefixes']))))
        self.assertEqual(candidate['watched_paths'], watched(candidate['candidate_commit']))
        # Keep the immutable V880 diff exact; only the independently pinned
        # V881/V882 successor can explain subsequent UI/server changes.
        self.assertEqual(candidate['watched_paths'], sync.preserve_reviewed_v881_scope(
            watched('HEAD'), candidate['base_main_sha']))
        self.assertTrue(set(candidate['generation_files']) <= set(w['exclude_paths']))
        self.assertFalse(r['verification']['physical_tablet_runtime_verified'])
        self.assertFalse(r['verification']['physical_drive_readback_verified'])
        self.assertFalse(d['share_policy']['cloud_upload_enabled'])

    def test_relocated_evidence_tests_and_root_budget_preserved(self):
        name = 'test_market_catalog_evidence_v547.py'
        before = subprocess.check_output(['git','show',sync.V880_PROOF['base_commit']+':'+name], cwd=sync.ROOT, text=True)
        after = (sync.ROOT/'execution/tests'/name).read_text()
        self.assertEqual(before.replace('ROOT = Path(__file__).resolve().parent', 'ROOT = Path(__file__).resolve().parents[2]'), after)
        self.assertFalse((sync.ROOT/name).exists())
        def count(ref):
            return len([x for x in subprocess.check_output(['git','ls-tree','-z',ref],cwd=sync.ROOT).split(b'\0') if x])
        self.assertLessEqual(count('HEAD'), count(sync.V880_PROOF['base_commit']))
