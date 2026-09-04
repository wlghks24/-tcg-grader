#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

import vision_calibration
import verified_grade_learning_v135 as verified

ROOT = Path(__file__).resolve().parent


class GradingHierarchyV17Tests(unittest.TestCase):
    def test_index_uses_hierarchy_for_grade_estimation(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('grading_vision_engine.js?v=160', source)
        self.assertIn('function gradingHierarchyAnalysis(base,oblique)', source)
        self.assertIn('frontHierarchy=gradingHierarchyAnalysis(F,FO)', source)
        self.assertIn('backHierarchy=gradingHierarchyAnalysis(B,BO)', source)
        self.assertIn('frontZones=frontHierarchy.stage3', source)
        self.assertIn('backZones=backHierarchy.stage3', source)
        self.assertIn('r=Math.max(frontHierarchy.surfaceRisk,backHierarchy.surfaceRisk)', source)
        self.assertIn('cornerRisk=Math.min(100,Math.max(frontHierarchy.cornerRisk,backHierarchy.cornerRisk', source)
        self.assertIn('1차 전체 → 2차 4분할 → 3차 8분할 정밀검사', source)

    def test_feature_contract_tracks_external_vision_engine(self):
        contract_source = (ROOT / "feature_contract.py").read_text(encoding="utf-8")
        self.assertIn('vision_engine = safe_read_text(base / "grading_vision_engine.js")', contract_source)
        for token in (
            '"analyzeWhitening"',
            '"quadrantCornerWorstRisk"',
            '"eightZoneWorst"',
            '"hierarchyDefectRisk"',
        ):
            self.assertIn(token, contract_source)

    def test_eight_zone_features_are_saved_for_verified_learning(self):
        source = (ROOT / "index.html").read_text(encoding="utf-8")
        for token in (
            'eightZoneWorstRisk',
            'eightZoneSurfaceWorstRisk',
            'eightZoneEdgeWorstRisk',
            'eightZoneCornerWorstRisk',
            'hierarchyDefectRisk',
            'hierarchyConfidence',
        ):
            self.assertIn(token, source)
            self.assertIn(token, verified._OPTIONAL_VISION_FIELDS)

    def test_calibration_bucket_uses_eight_zone_local_defect(self):
        vision = {
            "frontCenter": 48,
            "backCenter": 48,
            "surfaceRisk": 8,
            "quadrantSurfaceWorstRisk": 8,
            "quadrantWorstRisk": 8,
            "quadrantImbalance": 4,
            "eightZoneSurfaceWorstRisk": 42,
            "eightZoneWorstRisk": 66,
            "eightZoneImbalance": 52,
            "hierarchyDefectRisk": 66,
            "multiAngle": True,
        }
        self.assertEqual(
            vision_calibration.vision_bucket(vision),
            "centered|surface-high|q-local-defect|multi",
        )

    def test_legacy_verified_vision_bucket_remains_readable(self):
        vision = {
            "frontCenter": 48,
            "backCenter": 48,
            "surfaceRisk": 8,
            "quadrantSurfaceWorstRisk": 8,
            "quadrantWorstRisk": 8,
            "quadrantImbalance": 4,
            "multiAngle": True,
        }
        self.assertEqual(
            vision_calibration.vision_bucket(vision),
            "centered|surface-low|q-balanced|multi",
        )

    def test_browser_verified_guard_tries_modern_then_legacy_profile(self):
        source = (ROOT / "grade_learning_guard_v135.js").read_text(encoding="utf-8")
        self.assertIn("function currentVisionBuckets()", source)
        self.assertIn("localBand", source)
        self.assertIn("eightZoneWorstRisk", source)
        self.assertIn("for(const bucket of currentVisionBuckets())", source)
        self.assertIn("three-part bucket", source)

    def test_calibration_policy_documents_hierarchy_without_upward_learning(self):
        trained = vision_calibration.train_calibration([])
        policy = trained["policy"]
        self.assertTrue(policy["grading_hierarchy_1_4_8"])
        self.assertTrue(policy["eight_zone_features_isolated"])
        self.assertTrue(policy["legacy_verified_rows_backward_compatible"])
        self.assertFalse(policy["upward_correction_allowed"])
        self.assertFalse(policy["raw_image_model_retrained"])
        self.assertFalse(policy["official_grade_guaranteed"])


if __name__ == "__main__":
    unittest.main()
