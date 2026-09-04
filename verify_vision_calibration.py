#!/usr/bin/env python3
"""공식등급 교차검증 보정학습 회귀검사."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import vision_calibration as calibration


def row(index: int, *, company: str = "PSA", actual: float = 9, pred: float = 10,
        official: bool = True, certification: str | None = None) -> dict:
    return {
        "company": company, "actual": actual, "pred": pred,
        "official_result": official,
        "certification_id": certification or f"CERT-{company}-{index:04d}",
        "card_id": f"CARD-{company}-{index:04d}",
        "vision": {
            "frontCenter": 48, "backCenter": 48, "surfaceRisk": 8,
            "surfaceConfidence": 88, "analysisConfidence": 90, "multiAngle": True,
            "quadrantWorstRisk": 8, "quadrantSurfaceWorstRisk": 8,
            "quadrantEdgeWorstRisk": 4, "quadrantCornerWorstRisk": 3,
            "quadrantMeanRisk": 5, "quadrantImbalance": 6, "quadrantConfidence": 86,
            "eightZoneWorstRisk": 7, "eightZoneSurfaceWorstRisk": 7,
            "eightZoneEdgeWorstRisk": 3, "eightZoneCornerWorstRisk": 2,
            "eightZoneMeanRisk": 4, "eightZoneImbalance": 5, "eightZoneConfidence": 82,
            "hierarchyDefectRisk": 8, "hierarchyConfidence": 82,
            "engine": calibration.ENGINE_VERSION,
        },
    }


class CalibrationTests(unittest.TestCase):
    def test_four_quadrant_bucket_preserves_local_defect_signal(self):
        vision = row(1)["vision"]
        vision.update({"quadrantWorstRisk": 62, "quadrantSurfaceWorstRisk": 48, "quadrantImbalance": 54})
        self.assertEqual(calibration.vision_bucket(vision), "centered|surface-high|q-local-defect|multi")

    def test_eight_zone_bucket_preserves_micro_local_defect_signal(self):
        vision = row(1)["vision"]
        vision.update({
            "quadrantWorstRisk": 8,
            "quadrantSurfaceWorstRisk": 8,
            "quadrantImbalance": 6,
            "eightZoneWorstRisk": 63,
            "eightZoneSurfaceWorstRisk": 47,
            "eightZoneImbalance": 58,
            "hierarchyDefectRisk": 63,
        })
        self.assertEqual(
            calibration.vision_bucket(vision),
            "centered|surface-high|q-local-defect|multi",
        )

    def test_legacy_four_quadrant_row_keeps_compatible_bucket(self):
        vision = row(1)["vision"]
        for key in list(vision):
            if key.startswith("eightZone") or key.startswith("hierarchy"):
                vision.pop(key)
        self.assertEqual(
            calibration.vision_bucket(vision),
            "centered|surface-low|q-balanced|multi",
        )

    def test_consistent_overgrade_enables_downward_holdout_correction(self):
        rows = [row(index) for index in range(20)]
        clean = calibration.sanitize_rows({"v30_validation": rows})
        trained = calibration.train_calibration(clean)
        profile = trained["profiles"]["PSA|centered|surface-low|q-balanced|multi"]
        self.assertTrue(profile["enabled"])
        self.assertEqual(profile["correction"], -1)
        self.assertLess(profile["corrected_mae"], profile["baseline_mae"])
        self.assertGreaterEqual(profile["unique_cards"], calibration.MIN_UNIQUE_CARDS)
        self.assertFalse(trained["policy"]["upward_correction_allowed"])
        self.assertFalse(trained["policy"]["raw_image_model_retrained"])

    def test_undergrade_never_creates_upward_correction(self):
        rows = [row(index, company="BGS", actual=9, pred=8) for index in range(20)]
        trained = calibration.train_calibration(calibration.sanitize_rows({"v30_validation": rows}))
        profile = trained["profiles"]["BGS|centered|surface-low|q-balanced|multi"]
        self.assertFalse(profile["enabled"])
        self.assertEqual(profile["correction"], 0)

    def test_unverified_or_unidentified_labels_are_rejected(self):
        payload = {"v30_validation": [
            row(1, official=False),
            row(2, certification="x"),
            row(3, certification="bad secret token with spaces"),
            row(4),
        ]}
        clean = calibration.sanitize_rows(payload)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]["certification_id"], "CERT-PSA-0004")

    def test_too_few_cards_stays_disabled(self):
        rows = [row(index) for index in range(5)]
        trained = calibration.train_calibration(calibration.sanitize_rows({"v30_validation": rows}))
        profile = trained["profiles"]["PSA|centered|surface-low|q-balanced|multi"]
        self.assertFalse(profile["enabled"])
        self.assertEqual(profile["reason"], "insufficient-official-labels")


    def test_invalid_company_grade_step_is_rejected(self):
        rows = [row(1, company="BGS", actual=9.3, pred=10)]
        self.assertEqual(calibration.sanitize_rows({"v99_validation": rows}), [])

    def test_conflicting_certification_is_quarantined(self):
        first = row(1, actual=9, pred=10, certification="CERT-CONFLICT")
        second = row(2, actual=8, pred=10, certification="CERT-CONFLICT")
        self.assertEqual(calibration.sanitize_rows({"v99_validation": [first, second]}), [])

    def test_vision_learns_only_residual_after_global(self):
        from grading_accuracy_v99 import sanitize_rows as global_rows, train_company_calibration
        rows = [row(index) for index in range(30)]
        payload = {"v99_validation": rows}
        global_models = train_company_calibration(global_rows(payload))
        self.assertTrue(global_models["PSA"]["enabled"])
        trained = calibration.train_calibration(calibration.sanitize_rows(payload), global_models)
        profile = trained["profiles"]["PSA|centered|surface-low|q-balanced|multi"]
        self.assertEqual(profile["baseline_global_correction"], global_models["PSA"]["correction"])
        self.assertFalse(profile["enabled"])
        self.assertEqual(profile["correction"], 0)
        self.assertTrue(trained["policy"]["vision_learns_residual_after_global"])
    def test_corrupt_input_produces_safe_empty_calibration(self):
        with tempfile.TemporaryDirectory(prefix="tcg-calibration-") as directory:
            source = Path(directory) / "learning.json"
            target = Path(directory) / "calibration.json"
            source.write_text("{broken", encoding="utf-8")
            result = calibration.train_file(source, target)
            persisted = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(result["training_rows"], 0)
        self.assertEqual(persisted["profiles"], {})


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CalibrationTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"ok": result.wasSuccessful(), "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors)}, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
