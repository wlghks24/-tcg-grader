"""V884 recovery must explain real descendants and reject live/proof tampering."""
from __future__ import annotations

import hashlib
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parents[2]


class SyncChainRecoveryV884Tests(unittest.TestCase):
    def test_exact_candidate_and_historical_delegation(self):
        c = sync.assert_v884_successor(self)
        from execution.tests.test_video_ui_successor_v881 import validate_candidate
        self.assertIn('index.html', validate_candidate())
        for version in (653, 654, 655, 656, 657, 658):
            old = getattr(sync, f'V{version}_PROOF')
            bridge = getattr(sync, f'preserve_reviewed_v{version}_scope')
            self.assertEqual([], bridge(['tcg_updater.py'], old['candidate_commit']))
        later = ['execution/tests/test_video_ui_successor_v881.py']
        self.assertEqual([], sync.preserve_reviewed_v884_scope(
            later, '742751dce03c711f7a4ca7a882d2fec69fb3ac55'))
        self.assertIn(sync.V884_NEW_WATCH, c['candidate_sync']['watched_paths'])

    def test_current_source_and_support_tampering_stay_visible(self):
        c = sync.assert_v884_successor(self)
        original = Path.read_bytes
        for name in c['candidate_sync']['reviewed_sha256']:
            def changed(path, target=ROOT/name):
                data = original(path)
                return data+b'\n# unreviewed' if path == target else data
            with self.subTest(path=name), patch.object(Path, 'read_bytes', changed):
                with self.assertRaises(AssertionError):
                    sync.assert_v884_successor(self)
                self.assertEqual([name], sync.preserve_reviewed_v884_scope([name], sync.V884_BASE))

    def test_modified_receipt_and_widened_scope_fail_closed(self):
        sync.assert_v884_successor(self)
        original = sync._read
        for part in ('receipt', 'scope', 'candidate', 'lesson'):
            def forged(path):
                data = original(path)
                name = str(path)
                if part == 'receipt' and name.endswith('tablet_gpt_learning_receipt_v884.json'):
                    data['verification']['physical_tablet_runtime_verified'] = True
                if name.endswith('TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V884.json'):
                    if part == 'scope':
                        data['freshness_watch']['exclude_paths'].append('index.html')
                    elif part == 'candidate':
                        data['candidate_sync']['candidate_commit'] = sync.V884_BASE
                if part == 'lesson' and name.endswith('learning_snapshot_v884_delta.json'):
                    data['lessons'][0]['prevention_rule'] = 'forged lesson'
                return data
            with self.subTest(part=part), patch.object(sync, '_read', forged):
                with self.assertRaises(AssertionError):
                    sync.assert_v884_successor(self)
                self.assertEqual(['index.html'], sync.preserve_reviewed_v884_scope(['index.html'], sync.V884_BASE))

    def test_unknown_older_and_non_head_changes_are_never_hidden(self):
        for visible, source, head in ((['unknown.py'], sync.V884_BASE, 'HEAD'),
                                      (['index.html'], sync.V880_PROOF['base_commit'], 'HEAD'),
                                      (['index.html'], sync.V884_BASE, sync.V884_BASE)):
            self.assertEqual(visible, sync.preserve_reviewed_v884_scope(visible, source, head))

    def test_archived_report_is_identical_and_root_budget_is_preserved(self):
        name = 'V102_FINAL_VERIFICATION_REPORT.json'
        original = subprocess.check_output(['git', 'show', sync.V884_BASE+':'+name], cwd=ROOT)
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         hashlib.sha256((ROOT/'docs/archive'/name).read_bytes()).hexdigest())
        self.assertFalse((ROOT/name).exists())
        def count(ref):
            return len([row for row in subprocess.check_output(
                ['git', 'ls-tree', '-z', ref], cwd=ROOT).split(b'\0') if row])
        self.assertLessEqual(count('HEAD'), count(sync.V884_BASE))


if __name__ == '__main__':
    unittest.main()
