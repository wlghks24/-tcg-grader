"""V882 P0 learning-store successor: exact pins, negative tamper guards."""
from pathlib import Path
import hashlib
import json
import unittest
from unittest import mock

import sync_v376_successor_test_support as sync

ROOT = Path(__file__).resolve().parents[2]

class LearningStoreSuccessorV882Tests(unittest.TestCase):
    def test_exact_persisted_contract_pins(self):
        payload=json.loads(sync.V882_LEARNING_PROOF.read_text(encoding='utf-8'))
        self.assertEqual(payload['reviewed_path'],'tcg_updater.py')
        self.assertEqual(payload['baseline_sha256'],sync.V882_LEARNING_BASE_SHA256)
        self.assertIs(payload['auto_main_merge_allowed'],False)
        self.assertIs(payload['physical_tablet_verified'],False)
        for path,digest in ((sync.V882_LEARNING_PATH,sync.V882_LEARNING_SHA256),
                            (sync.V882_LEARNING_TEST,sync.V882_LEARNING_TEST_SHA256)):
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)

    def test_missing_proof_or_unexpected_hash_fails_closed(self):
        with mock.patch.object(sync,'V882_LEARNING_PROOF',ROOT/'missing_v882.json'):
            self.assertFalse(sync.reviewed_v882_learning_store_successor())
        with mock.patch.object(sync,'V882_LEARNING_SHA256','0'*64):
            self.assertFalse(sync.reviewed_v882_learning_store_successor())

    def test_historical_non_head_cannot_reuse_current_successor(self):
        self.assertFalse(sync.reviewed_v882_learning_store_successor(head=sync.V882_LEARNING_CANDIDATE))

if __name__=='__main__':unittest.main()
