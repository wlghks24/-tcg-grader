"""Fail-closed exact V882 evidence-preservation successor regression checks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import sync_v376_successor_test_support as sync


class V882EvidenceSuccessorTests(unittest.TestCase):
    def test_exact_current_source_and_historical_successor(self):
        sync.assert_v882_updater_successor(self)
        sync.assert_v652_successor(self)

    def test_missing_evidence_file_is_rejected(self):
        with mock.patch.object(
            sync, "V882_UPDATER_PROOF", ROOT / "execution/evidence/missing_v882.json"
        ), self.assertRaises(AssertionError):
            sync.assert_v882_updater_successor(self)

    def test_mismatched_source_digest_is_rejected(self):
        with mock.patch.object(sync, "V882_UPDATER_SHA256", "0" * 64), self.assertRaises(AssertionError):
            sync.assert_v882_updater_successor(self)


if __name__ == "__main__":
    unittest.main()
