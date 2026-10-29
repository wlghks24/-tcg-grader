"""Fail-closed checks for exact V880 verified-calibration historical successor."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import sync_v376_successor_test_support as sync


class V880VerifiedLearningSuccessorTests(unittest.TestCase):
    def test_exact_pinned_candidate_is_narrowly_delegated(self):
        path = sync.V880_VERIFIED_PATH
        original = [".github/workflows/tablet-autonomy-patch-checks.yml", path]
        result = sync.preserve_reviewed_v880_verified_learning_scope(
            original, sync.V880_VERIFIED_BASE)
        self.assertEqual([original[0]], result)

    def test_historical_non_head_reads_are_not_waived(self):
        path = sync.V880_VERIFIED_PATH
        self.assertEqual(
            [path], sync.preserve_reviewed_v880_verified_learning_scope(
                [path], sync.V880_VERIFIED_BASE, head=sync.V880_VERIFIED_CANDIDATE))

    def test_missing_or_modified_proof_is_not_waived(self):
        path = sync.V880_VERIFIED_PATH
        with mock.patch.object(sync, "V880_VERIFIED_PROOF",
                               ROOT / "execution" / "evidence" / "absent_v880_receipt.json"):
            self.assertEqual(
                [path], sync.preserve_reviewed_v880_verified_learning_scope(
                    [path], sync.V880_VERIFIED_BASE))
        with mock.patch.object(sync, "V880_VERIFIED_SHA256", "0" * 64):
            self.assertEqual(
                [path], sync.preserve_reviewed_v880_verified_learning_scope(
                    [path], sync.V880_VERIFIED_BASE))

    def test_wrong_test_hash_cannot_approve_history(self):
        path = sync.V880_VERIFIED_PATH
        with mock.patch.object(sync, "V880_VERIFIED_TEST_SHA256", "0" * 64):
            self.assertEqual(
                [path], sync.preserve_reviewed_v880_verified_learning_scope(
                    [path], sync.V880_VERIFIED_BASE))


if __name__ == "__main__":
    unittest.main()
