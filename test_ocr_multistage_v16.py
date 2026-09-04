#!/usr/bin/env python3
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import card_identity_recognition as identity
import ocr_accuracy_boost_v147 as slab_ocr
import ocr_multistage_regions_v16 as regions


class OcrMultistageV16Tests(unittest.TestCase):
    def test_region_plan_is_exactly_full_then_four_then_eight(self):
        self.assertEqual(len(regions.region_specs(1)), 1)
        self.assertEqual(len(regions.region_specs(2)), 4)
        self.assertEqual(len(regions.region_specs(3)), 8)
        plan = regions.hierarchical_specs()
        self.assertEqual(len(plan), 13)
        self.assertEqual([spec.stage for spec in plan], [1] + [2] * 4 + [3] * 8)
        self.assertEqual(regions.validate_plan()["total_regions"], 13)

    def test_split_regions_overlap_without_leaving_image_bounds(self):
        for stage in (2, 3):
            specs = regions.region_specs(stage)
            self.assertTrue(all(0 <= s.left < s.right <= 1 for s in specs))
            self.assertTrue(all(0 <= s.top < s.bottom <= 1 for s in specs))
        q1, q2 = regions.region_specs(2)[:2]
        self.assertGreater(q1.right, q2.left)
        o1, o2 = regions.region_specs(3)[:2]
        self.assertGreater(o1.right, o2.left)

    def test_crop_region_produces_nonempty_precision_tiles(self):
        source = Image.new("RGB", (800, 1200), "white")
        for spec in regions.hierarchical_specs():
            crop = regions.crop_region(source, spec, target_width=900)
            self.assertGreaterEqual(crop.width, 480)
            self.assertGreater(crop.height, 0)

    def test_card_identity_runs_all_thirteen_regions_and_cross_validates(self):
        buffer = io.BytesIO()
        Image.new("RGB", (900, 1300), "white").save(buffer, format="PNG")
        best = {
            "market_key": "JP|Luffy|HIT",
            "region": "JP",
            "game": "onepiece",
            "card_name": "Monkey D. Luffy",
            "card_number": "OP13-007",
            "confidence": 0.997,
            "matched_by": "card_number_exact+card_name",
        }

        def fake_match(text, game="unknown", limit=5, *, region="UNKNOWN"):
            return [best] if "OP13-007" in text else []

        with mock.patch.object(identity, "_tesseract_binary", return_value="/usr/bin/tesseract"), \
             mock.patch.object(identity, "_tesseract_languages", return_value=frozenset({"eng", "jpn"})), \
             mock.patch.object(identity, "_run_card_tesseract", return_value=("MONKEY D LUFFY OP13-007", None)) as run, \
             mock.patch.object(identity, "match_catalog", side_effect=fake_match):
            text, error, diag = identity.ocr_image_detailed(
                buffer.getvalue(), game="onepiece", region="JP"
            )

        self.assertIsNone(error)
        self.assertIn("OP13-007", text)
        self.assertEqual(run.call_count, 13)
        self.assertEqual(diag["stage_order"], [1, 2, 3])
        self.assertEqual(diag["stage_region_counts"], {"1": 1, "2": 4, "3": 8})
        self.assertEqual(diag["stages_completed"], [1, 2, 3])
        self.assertTrue(diag["all_stages_completed"])
        self.assertEqual(diag["pass_count"], 13)
        self.assertEqual(len(diag["regions"]), 13)
        self.assertTrue(diag["cross_validation"]["cross_validated"])
        self.assertTrue(diag["cross_validation"]["three_stage_agreement"])
        self.assertEqual(diag["cross_validation"]["number_stage_votes"], 3)

    def test_seed_text_does_not_skip_requested_three_stage_image_analysis(self):
        buffer = io.BytesIO()
        Image.new("RGB", (900, 1300), "white").save(buffer, format="PNG")
        best = {
            "market_key": "KR|Luffy|HIT",
            "region": "KR",
            "game": "onepiece",
            "card_name": "Luffy",
            "card_number": "OP13-007",
            "confidence": 0.997,
            "matched_by": "card_number_exact+card_name",
        }
        with mock.patch.object(identity, "_tesseract_binary", return_value="/usr/bin/tesseract"), \
             mock.patch.object(identity, "_tesseract_languages", return_value=frozenset({"eng", "kor"})), \
             mock.patch.object(identity, "_run_card_tesseract", return_value=("LUFFY OP13-007", None)) as run, \
             mock.patch.object(identity, "match_catalog", return_value=[best]):
            _, _, diag = identity.ocr_image_detailed(
                buffer.getvalue(),
                game="onepiece",
                region="KR",
                seed_text="LUFFY OP13-007",
            )
        self.assertTrue(diag["seed_text_sufficient"])
        self.assertEqual(run.call_count, 13)
        self.assertEqual(diag["stages_completed"], [1, 2, 3])

    def test_slab_ocr_runs_full_four_eight_and_stage_consensus(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slab.png"
            Image.new("RGB", (900, 1400), "white").save(path)
            with mock.patch.object(
                slab_ocr,
                "_run_tesseract",
                return_value=("PSA GEM MT 10 CERT 12345678", None),
            ) as run:
                text, error, diag = slab_ocr.ocr_label(path, profile="accuracy")

        self.assertIsNone(error)
        self.assertIn("12345678", text)
        self.assertEqual(run.call_count, 13)
        self.assertEqual(diag["stage_region_counts"], {"1": 1, "2": 4, "3": 8})
        self.assertEqual(diag["stages_completed"], [1, 2, 3])
        self.assertEqual(diag["pass_count"], 13)
        self.assertEqual(diag["identity_score"], 100)
        self.assertTrue(diag["cross_validation"]["cross_validated"])
        self.assertTrue(diag["cross_validation"]["three_stage_agreement"])

    def test_fast_slab_profile_keeps_all_three_stages_with_lighter_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slab.png"
            Image.new("RGB", (900, 1400), "white").save(path)
            with mock.patch.object(
                slab_ocr,
                "_run_tesseract",
                return_value=("PSA GEM MT 10 CERT 12345678", None),
            ) as run:
                _, _, diag = slab_ocr.ocr_label(path, profile="fast")
        self.assertEqual(run.call_count, 13)
        self.assertEqual(diag["stages_completed"], [1, 2, 3])
        self.assertEqual(diag["analysis_mode"], "hierarchical_1_4_8")

    def test_browser_contract_reports_three_stage_analysis(self):
        source = (Path(__file__).resolve().parent / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("v16-ocr-hierarchical-1-4-8", source)
        self.assertIn("1차 전체→2차 4분할→3차 8분할 완료", source)
        self.assertIn("setTimeout(()=>controller.abort(),120000)", source)


if __name__ == "__main__":
    unittest.main()
