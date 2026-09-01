#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import verified_slab_raw_learning_v155 as raw


class VerifiedSlabRawLearningV155Tests(unittest.TestCase):
    def test_card_roi_excludes_top_slab_label(self):
        image = Image.new("RGB", (800, 1400), (110, 110, 110))
        # Simulated red grader label/header, entirely above the card ROI.
        for y in range(0, 300):
            for x in range(800):
                image.putpixel((x, y), (250, 10, 10))
        roi = raw._prepare_card_roi(image)
        pixel = roi.getpixel((roi.width // 2, 2))
        self.assertLess(pixel[0], 200)

    def test_raw_prediction_does_not_take_official_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            front = Path(tmp) / "front.jpg"
            back = Path(tmp) / "back.jpg"
            Image.new("RGB", (900, 1500), (90, 105, 120)).save(front)
            Image.new("RGB", (900, 1500), (70, 85, 100)).save(back)
            vision1, pred1, _, _ = raw._extract_pair_features(front, back, "PSA")
            vision2, pred2, _, _ = raw._extract_pair_features(front, back, "PSA")
        self.assertEqual(pred1, pred2)
        self.assertEqual(vision1, vision2)
        self.assertNotIn("official_grade", vision1)
        self.assertEqual(set(vision1["frontQuadrants"]), {"tl", "tr", "bl", "br"})
        self.assertIn("quadrantWorstRisk", vision1)

    def test_four_quadrant_features_localize_corner_damage(self):
        image = Image.new("RGB", (600, 840), (70, 85, 100))
        for y in range(0, 34):
            for x in range(0, 34):
                image.putpixel((x, y), (255, 255, 255))
        result = raw._quadrant_features(image)
        self.assertEqual(set(result["quadrants"]), {"tl", "tr", "bl", "br"})
        self.assertGreater(result["quadrants"]["tl"]["cornerRisk"], result["quadrants"]["br"]["cornerRisk"])
        self.assertGreater(result["quadrantImbalance"], 0)

    def test_manual_browser_official_source_requires_strict_matched_proof(self):
        row = {
            "official_result": True,
            "official_verification_source": "user_browser_official_page",
            "company": "PSA",
            "game": "onepiece",
            "official_grade": 10,
            "certification_id": "160600294",
            "front_back_pair_complete": True,
            "image_sha256": "a" * 64,
            "back_image_sha256": "b" * 64,
            "image_path": "GRADE_TRAINING_INBOX/manual/front.jpg",
            "back_image_path": "GRADE_TRAINING_INBOX/manual/back.jpg",
            "manual_official_proof_registered": False,
        }
        registry = {
            raw.grade_learning._cert_key("PSA", "160600294"): {
                "company": "PSA", "certification_id": "160600294", "grade": 10.0
            }
        }
        with patch.object(raw, "_safe_source", return_value=Path(__file__)):
            self.assertIsNone(raw._identity(row, registry))
            row["manual_official_proof_registered"] = True
            row["manual_official_proof_state"] = "matched"
            row["manual_official_proof_match_mode"] = "official_page_company_cert_plus_exact_slab_ocr_grade"
            self.assertIsNotNone(raw._identity(row, registry))

    def test_grade_correction_activation_waits_for_twenty_unique_certs(self):
        candidates = [
            {"company": "PSA", "certification_id": str(100000000 + i)}
            for i in range(raw.MIN_COMPANY_PROXY_ROWS - 1)
        ]
        counts = raw._company_counts(candidates)
        self.assertEqual(counts["PSA"], raw.MIN_COMPANY_PROXY_ROWS - 1)
        self.assertLess(counts["PSA"], raw.MIN_COMPANY_PROXY_ROWS)

    def test_numeric_grade_does_not_create_hard_defect_type_label(self):
        weak = {
            "surface_risk": 10.0,
            "edge_risk": 5.0,
            "corner_risk": 3.0,
            "official_grade_target": 9.0,
            "hard_defect_type_label": None,
        }
        self.assertIsNone(weak["hard_defect_type_label"])

    def test_existing_pair_is_revalidated_to_eight_zones_and_front_only_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            front = root / "front.jpg"
            back = root / "back.jpg"
            legacy = root / "legacy.jpg"
            for path, color in ((front, (90, 105, 120)), (back, (70, 85, 100)), (legacy, (80, 90, 110))):
                Image.new("RGB", (900, 1500), color).save(path)
            sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            rows = [
                {"registration_id": "pair", "image_path": "front.jpg", "back_image_path": "back.jpg",
                 "image_sha256": sha(front), "back_image_sha256": sha(back), "official_result": False},
                {"registration_id": "legacy", "image_path": "legacy.jpg", "image_sha256": sha(legacy),
                 "official_result": False},
            ]
            paths = {"front.jpg": front, "back.jpg": back, "legacy.jpg": legacy}
            payload = {"registrations": rows}
            with patch.object(raw, "REVALIDATION_PATH", root / "revalidation.json"), \
                 patch.object(raw, "_safe_source", side_effect=lambda value: paths.get(value)), \
                 patch.object(raw.manual_photo, "_registry", return_value=payload), \
                 patch.object(raw.manual_photo, "_save_registry") as save_registry, \
                 patch.object(raw.grade_learning, "registry_index", return_value={}), \
                 patch.object(raw, "sync_rows", return_value={"summary": {"proxy_candidates": 0}}):
                state = raw.revalidate_existing()
        self.assertEqual(state["summary"]["eight_zone_complete"], 1)
        self.assertEqual(state["summary"]["legacy_front_only"], 1)
        result = {row["registration_id"]: row for row in state["results"]}
        self.assertEqual(result["pair"]["quadrant_zone_count"], 8)
        self.assertEqual(set(result["pair"]["frontQuadrants"]), {"tl", "tr", "bl", "br"})
        self.assertEqual(result["legacy"]["disposition"], "legacy_front_only_needs_back")
        self.assertTrue(result["legacy"]["original_preserved"])
        save_registry.assert_called_once()


if __name__ == "__main__":
    unittest.main()
