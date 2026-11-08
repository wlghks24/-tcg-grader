"""V975 exact immutable V974 PIDFD handoff successor; no device signals."""
from __future__ import annotations
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parent

class V975HandoffSuccessorTests(unittest.TestCase):
    def test_exact_v974_candidate_and_v975_generation(self):
        c = sync.assert_v975_handoff_successor(self)
        self.assertEqual([sync.V975_HANDOFF_PATH], c['candidate_sync']['watched_paths'])
        self.assertFalse(c['share_policy']['physical_tablet_runtime_verified'])

    def test_v31_report_archived_bytewise_and_root_budget_unchanged(self):
        old = subprocess.check_output(
            ['git', 'show', sync.V975_HANDOFF_CANDIDATE+':v31_최종검증보고서.json'],
            cwd=ROOT, timeout=30)
        archived = ROOT / 'docs/archive/reports/v31_최종검증보고서.json'
        self.assertTrue(archived.is_file())
        self.assertFalse(archived.is_symlink())
        self.assertEqual(old, archived.read_bytes())
        self.assertFalse((ROOT/'v31_최종검증보고서.json').exists())
        def root_count(ref):
            return len([row for row in subprocess.check_output(
                ['git', 'ls-tree', '-z', ref], cwd=ROOT, timeout=30).split(b'\0') if row])
        self.assertLessEqual(root_count('HEAD'), root_count(sync.V884_BASE))

    def test_historical_v651_v880_v884_delegation_is_exact_and_fail_closed(self):
        name = sync.V975_HANDOFF_PATH
        source = sync.V651_UPDATE_PROOF['candidate_commit']
        self.assertEqual([], sync.preserve_reviewed_v975_handoff_scope([name], source))
        self.assertEqual([], sync.preserve_reviewed_v881_scope(
            [name], sync.V880_PROOF['base_commit']))
        self.assertEqual([], sync.preserve_reviewed_v884_scope(
            [name], sync.V884_BASE))
        self.assertEqual([name], sync.preserve_reviewed_v975_handoff_scope(
            [name], sync.V651_UPDATE_PROOF['base_commit']))
        self.assertEqual([name], sync.preserve_reviewed_v975_handoff_scope(
            [name], sync.V975_HANDOFF_CANDIDATE))
        self.assertEqual([name], sync.preserve_reviewed_v975_handoff_scope(
            [name], source, head=sync.V975_HANDOFF_BASE))
        self.assertEqual(['unreviewed.py'], sync.preserve_reviewed_v975_handoff_scope(
            ['unreviewed.py'], source))
        original = Path.read_bytes
        target = ROOT/name
        def changed(path):
            raw = original(path)
            return raw + b'\n# unreviewed' if path == target else raw
        with patch.object(Path, 'read_bytes', changed):
            self.assertEqual([name], sync.preserve_reviewed_v975_handoff_scope(
                [name], source))
            self.assertEqual([name], sync.preserve_reviewed_v881_scope(
                [name], sync.V880_PROOF['base_commit']))
            self.assertEqual([name], sync.preserve_reviewed_v884_scope(
                [name], sync.V884_BASE))

    def test_live_handoff_tamper_fails_closed(self):
        original = Path.read_bytes
        target = ROOT / sync.V975_HANDOFF_PATH
        def tampered(path):
            raw = original(path)
            return raw + b'\n# unexpected handoff edit' if path == target else raw
        with patch.object(Path, 'read_bytes', tampered):
            with self.assertRaises(AssertionError):
                sync.assert_v975_handoff_successor(self)

    def test_proof_and_contract_scope_tamper_fails_closed(self):
        original = sync._read
        for kind in ('proof', 'watched', 'device'):
            def tampered(path):
                value = original(path)
                if kind == 'proof' and str(path).endswith('pidfd_handoff_successor_v975.json'):
                    value['candidate_commit'] = sync.V975_HANDOFF_BASE
                if kind == 'watched' and str(path).endswith('SYNC_CONTRACT_V975.json'):
                    value['freshness_watch']['exclude_paths'].append('index.html')
                if kind == 'device' and str(path).endswith('tablet_gpt_learning_receipt_v975.json'):
                    value['verification']['physical_tablet_runtime_verified'] = True
                return value
            with self.subTest(kind=kind), patch.object(sync, '_read', tampered):
                with self.assertRaises(AssertionError):
                    sync.assert_v975_handoff_successor(self)

if __name__ == '__main__':
    unittest.main()
