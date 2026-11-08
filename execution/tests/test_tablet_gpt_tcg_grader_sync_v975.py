"""V975 exact immutable V974 PIDFD handoff successor; no device signals."""
from __future__ import annotations
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parents[2]

class V975HandoffSuccessorTests(unittest.TestCase):
    def test_exact_v974_candidate_and_v975_generation(self):
        c = sync.assert_v975_handoff_successor(self)
        self.assertEqual([sync.V975_HANDOFF_PATH], c['candidate_sync']['watched_paths'])
        self.assertFalse(c['share_policy']['physical_tablet_runtime_verified'])

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
