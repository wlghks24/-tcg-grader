"""V885 exact card-grouped calibration successor proof; fail closed on forged receipts."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import sync_v376_successor_test_support as sync


class CardHoldoutSuccessorTests(unittest.TestCase):
    def test_exact_reviewed_candidate_is_delegated(self):
        self.assertEqual([], sync.preserve_reviewed_v885_calibration_scope(
            ["vision_calibration.py"], sync.V885_CALIBRATION_BASE))

    def test_unrelated_and_unknown_source_remain_visible(self):
        unrelated = ".github/workflows/tablet-autonomy-patch-checks.yml"
        self.assertEqual([unrelated], sync.preserve_reviewed_v885_calibration_scope(
            [unrelated, "vision_calibration.py"], sync.V885_CALIBRATION_BASE))
        self.assertEqual(["vision_calibration.py"], sync.preserve_reviewed_v885_calibration_scope(
            ["vision_calibration.py"], "0" * 40))
        self.assertEqual(["vision_calibration.py"], sync.preserve_reviewed_v885_calibration_scope(
            ["vision_calibration.py"], sync.V885_CALIBRATION_CANDIDATE))
        self.assertEqual(["vision_calibration.py"], sync.preserve_reviewed_v885_calibration_scope(
            ["vision_calibration.py"], sync.V885_CALIBRATION_BASE,
            head=sync.V885_CALIBRATION_CANDIDATE))

    def test_missing_or_tampered_proof_cannot_hide_changes(self):
        with mock.patch.object(sync, "V885_CALIBRATION_PROOF",
                               ROOT / "execution/evidence/absent_v885_proof.json"):
            self.assertEqual(["vision_calibration.py"], sync.preserve_reviewed_v885_calibration_scope(
                ["vision_calibration.py"], sync.V885_CALIBRATION_BASE))
        tampered = dict(sync.V885_CALIBRATION_PINS["vision_calibration.py"])
        tampered["sha256"] = "0" * 64
        with mock.patch.object(sync, "V885_CALIBRATION_PINS",
                               {**sync.V885_CALIBRATION_PINS, "vision_calibration.py": tampered}):
            self.assertEqual(["vision_calibration.py"], sync.preserve_reviewed_v885_calibration_scope(
                ["vision_calibration.py"], sync.V885_CALIBRATION_BASE))

    def test_v426_historical_successor_still_strict(self):
        sync.assert_v426_successor(self)

    def test_proof_does_not_claim_main_merge_or_tablet(self):
        proof = json.loads(sync.V885_CALIBRATION_PROOF.read_text(encoding="utf-8"))
        self.assertEqual(["vision_calibration.py"], proof["reviewed_paths"])
        self.assertEqual(sync.V885_CALIBRATION_BASE_BLOBS, proof["baseline_git_blob_sha1"])
        for key in ("physical_tablet_verified", "full_historical_v1_current_verified",
                    "auto_main_merge_allowed"):
            self.assertIs(proof[key], False)


if __name__ == "__main__":
    unittest.main()
