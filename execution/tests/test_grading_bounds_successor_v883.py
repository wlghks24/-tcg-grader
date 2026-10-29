"""V883: exact Python/JS grading successor, fail closed on altered provenance."""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import sync_v376_successor_test_support as sync

class GradeBoundsSuccessorTests(unittest.TestCase):
    def test_exact_reviewed_pair_and_unrelated_watches(self):
        marker=".github/workflows/tablet-autonomy-patch-checks.yml"
        self.assertEqual([marker],sync.preserve_reviewed_v883_grading_bounds_scope(
            [marker,*sync.V883_GRADE_PATHS],sync.V426_CANDIDATE))

    def test_historical_explicit_head_and_unknown_source_refuse_waiver(self):
        values=list(sync.V883_GRADE_PATHS)
        self.assertEqual(values,sync.preserve_reviewed_v883_grading_bounds_scope(
            values,sync.V426_CANDIDATE,head=sync.V883_GRADE_CANDIDATE))
        self.assertEqual(values,sync.preserve_reviewed_v883_grading_bounds_scope(
            values,"0"*40))

    def test_untrusted_proof_or_hash_fails_closed(self):
        values=list(sync.V883_GRADE_PATHS)
        with mock.patch.object(sync,"V883_GRADE_PROOF",ROOT/"execution/evidence/no_such_v883_proof.json"):
            self.assertEqual(values,sync.preserve_reviewed_v883_grading_bounds_scope(
                values,sync.V426_CANDIDATE))
        for target in values:
            with self.subTest(target=target):
                pin=dict(sync.V883_GRADE_PINS[target]);pin["sha256"]="0"*64
                with mock.patch.object(sync,"V883_GRADE_PINS",{**sync.V883_GRADE_PINS,target:pin}):
                    self.assertEqual(values,sync.preserve_reviewed_v883_grading_bounds_scope(
                        values,sync.V426_CANDIDATE))

    def test_review_receipt_does_not_approve_main_or_device(self):
        receipt=json.loads(sync.V883_GRADE_PROOF.read_text(encoding="utf-8"))
        self.assertEqual(receipt["reviewed_paths"],sync.V883_GRADE_PATHS)
        for field in ("auto_main_merge_allowed","physical_tablet_verified",
                      "full_historical_v1_current_verified"):
            self.assertIs(receipt[field],False)

if __name__=="__main__":
    unittest.main()
