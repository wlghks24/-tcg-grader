"""V975 exact V974 native-pidfd successor: no device signal or install."""
from __future__ import annotations
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync


class SyncChainRecoveryV975Tests(unittest.TestCase):
    def test_exact_candidate_and_historical_delegation(self):
        c = sync.assert_v975_successor(self)
        self.assertEqual(sorted(sync.V975_WATCHED), c['candidate_sync']['watched_paths'])
        sync.assert_v651_update_successor(self)
        sync.assert_v884_successor(self)
        path = 'execution/tablet_runtime_handoff.py'
        self.assertEqual([], sync.preserve_reviewed_v975_scope([path], sync.V975_BASE))
        self.assertEqual([], sync.preserve_reviewed_v884_scope([path], sync.V884_CANDIDATE))
        self.assertEqual([], sync.preserve_reviewed_v651_update_scope(
            [path], sync.V651_UPDATE_PROOF['base_commit']))

    def test_live_source_tamper_is_never_delegated(self):
        sync.assert_v975_successor(self)
        original = Path.read_bytes
        for name in sync.V975_WATCHED:
            def changed(path, target=sync.ROOT/name):
                value = original(path)
                return value + b'\n# unreviewed V975' if path == target else value
            with self.subTest(path=name), patch.object(Path, 'read_bytes', changed):
                with self.assertRaises(AssertionError):
                    sync.assert_v975_successor(self)
                self.assertEqual([name], sync.preserve_reviewed_v975_scope([name], sync.V975_BASE))

    def test_support_and_verifier_tamper_are_never_delegated(self):
        original = Path.read_bytes
        for name in ('sync_v376_successor_test_support.py', 'execution/tablet_sync_successor_v975.py'):
            target = sync.ROOT/name
            with self.subTest(path=name), patch.object(
                    Path, 'read_bytes', lambda path: original(path)+b'\n# unreviewed' if path == target else original(path)):
                with self.assertRaises(AssertionError):
                    sync.assert_v975_successor(self)
                self.assertEqual([sync.V975_WATCHED[1]],
                                 sync.preserve_reviewed_v975_scope([sync.V975_WATCHED[1]], sync.V975_BASE))

    def test_forged_receipt_and_scope_are_rejected(self):
        original = sync._read
        for forged in ('receipt', 'scope', 'candidate', 'lesson'):
            def read(path):
                data = original(path)
                name = str(path)
                if forged == 'receipt' and name.endswith('tablet_gpt_learning_receipt_v975.json'):
                    data['verification']['physical_tablet_runtime_verified'] = True
                if name.endswith('TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V975.json'):
                    if forged == 'scope':
                        data['freshness_watch']['exclude_paths'].append('execution/tablet_runtime_handoff.py')
                    elif forged == 'candidate':
                        data['candidate_sync']['candidate_commit'] = sync.V975_BASE
                if forged == 'lesson' and name.endswith('learning_snapshot_v975_delta.json'):
                    data['lessons'][0]['prevention_rule'] = 'forged'
                return data
            with self.subTest(forged=forged), patch.object(sync, '_read', read):
                with self.assertRaises(AssertionError):
                    sync.assert_v975_successor(self)
                self.assertEqual([sync.V975_WATCHED[1]],
                                 sync.preserve_reviewed_v975_scope([sync.V975_WATCHED[1]], sync.V975_BASE))

    def test_older_unknown_and_nonhead_edits_remain_visible(self):
        path = 'execution/tablet_runtime_handoff.py'
        self.assertEqual(['unknown.py'], sync.preserve_reviewed_v975_scope(['unknown.py'], sync.V975_BASE))
        self.assertEqual([path], sync.preserve_reviewed_v975_scope([path], sync.V975_BASE, sync.V975_CANDIDATE))
        self.assertEqual([path], sync.preserve_reviewed_v975_scope([path], sync.V975_CANDIDATE))
        self.assertEqual([path], sync.preserve_reviewed_v975_scope([path], sync.V651_UPDATE_PROOF['base_commit']))

    def test_archived_v104_report_and_root_budget(self):
        name = 'V104_FINAL_VERIFICATION_REPORT.json'
        original = subprocess.check_output(
            ['git', 'show', sync.V884_BASE + ':' + name], cwd=sync.ROOT, timeout=30)
        archived = sync.ROOT / 'docs/archive' / name
        self.assertTrue(archived.is_file())
        self.assertFalse(archived.is_symlink())
        self.assertEqual(original, archived.read_bytes())
        self.assertFalse((sync.ROOT / name).exists())
        def count(ref):
            return len([row for row in subprocess.check_output(
                ['git', 'ls-tree', '-z', ref], cwd=sync.ROOT, timeout=30).split(b'\0') if row])
        self.assertLessEqual(count('HEAD'), count(sync.V884_BASE))


if __name__ == '__main__':
    unittest.main()
