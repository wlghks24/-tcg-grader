"""Deterministic W001 historical forensic source and report checks."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v31_v100_forensics as forensic

ROOT = Path(__file__).resolve().parents[2]


class V31V100HistoricalForensicsTests(unittest.TestCase):
    def test_pinned_original_git_evidence_not_synthetic_release_approval(self):
        result = forensic.inspect(ROOT)
        self.assertEqual(8, result["original_root_file_count"])
        self.assertEqual(forensic.ROOT_COMMIT, result["original_root"])
        self.assertFalse(result["full_v1_v100_code_review"])
        self.assertIsNone(result["quality_score"])
        self.assertFalse(result["device_verified"])
        self.assertFalse(result["v31"]["current_runtime_regression_proven"])

    def test_v31_original_serviceworker_icon_paths_are_absent_from_root_tree(self):
        r = forensic.inspect(ROOT)["v31"]
        self.assertEqual(
            ["icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png"],
            r["missing_in_first_commit_icons"],
        )
        self.assertEqual(
            ["icons/icon-180.png", "icons/icon-192.png", "icons/icon-512.png"],
            r["missing_in_first_commit_serviceworker_precache"],
        )
        self.assertTrue(r["serviceworker_precache_uses_add_all"])
        self.assertTrue(r["report_claims_icon_fix"])

    def test_icon_parser_rejects_malformed_input(self):
        with self.assertRaisesRegex(ValueError, "malformed_root_manifest"):
            forensic.icon_references({}, "const CORE=['./']; cache.addAll(CORE)")
        with self.assertRaisesRegex(ValueError, "unrecognized_original_serviceworker"):
            forensic.icon_references({"icons": [{"src": "icon.svg"}]}, "nothing")

    def test_present_icon_does_not_create_false_missing_asset(self):
        manifest={"icons":[{"src":"icons/icon-192.png"}]}
        sw="const CORE=['./','./icons/icon-192.png'];cache.addAll(CORE)"
        icons, core=forensic.icon_references(manifest, sw)
        self.assertEqual(["icons/icon-192.png"], icons)
        self.assertIn("icons/icon-192.png", core)
        self.assertEqual(set(), set(icons)-{"icons/icon-192.png"})

    def test_v99_root_history_is_not_original_release_accuracy_proof(self):
        r=forensic.inspect(ROOT)["v99"]
        self.assertTrue(r["original_skipped_missing_channel"])
        self.assertEqual(forensic.ORIGINAL_V99_IMPORT, r["first_pinned_source_seen_at"])
        self.assertEqual(forensic.V291_REPAIR_COMMIT, r["later_v291_repair_commit"])
        self.assertFalse(r["complete_current_grading_review"])

    def test_v100_historical_report_metadata_mismatch_and_synthetic_limits(self):
        data=forensic.inspect(ROOT)["v100"]
        self.assertEqual("MISMATCH", data["build_label_vs_metadata"])
        self.assertEqual(1, data["metadata_version"])
        self.assertIn("v100", data["build_label"])
        self.assertEqual(6, data["historical_record_passes"])
        self.assertEqual(12, data["synthetic_positive_labels"])
        self.assertEqual(24, data["synthetic_negative_labels"])
        self.assertFalse(data["calibration_adopted"])
        self.assertTrue(data["explicit_real_photo_limitation"])
        self.assertFalse(data["real_photo_accuracy_verified"])

    def test_v100_rejects_forged_negative_counts_and_inconsistent_passes(self):
        d={"build":"TCG_v100", "version":100, "successful_passes":1,
           "final_full_verification_passes":[{}],
           "vision_self_learning":{"metrics":{"counts":{"tp":-1,"tn":24,"fp":0,"fn":0}}},
           "limitations":["synthetic result is not real evidence"]}
        with self.assertRaisesRegex(ValueError, "invalid_v100_count"):
            forensic.report_semantics(d)
        d["vision_self_learning"]["metrics"]["counts"]["tp"]=12
        d["successful_passes"]=2
        with self.assertRaisesRegex(ValueError, "internal_pass_count_mismatch"):
            forensic.report_semantics(d)

    def test_v100_rejects_missing_or_nonlist_pass_evidence(self):
        d={"build":"TCG_v100","version":100,"successful_passes":0,
           "final_full_verification_passes":[],
           "vision_self_learning":{"metrics":{"counts":{"tp":0,"tn":0,"fp":0,"fn":0}}},
           "limitations":["synthetic is not real"]}
        for bad in (None, "not-a-list", {}, 7):
            with self.subTest(bad=bad):
                d["final_full_verification_passes"]=bad
                with self.assertRaisesRegex(ValueError, "internal_pass_count_mismatch"):
                    forensic.report_semantics(d)
        d["final_full_verification_passes"]=[]
        for bad in (None, True, "0", -1):
            with self.subTest(successful=bad):
                d["successful_passes"]=bad
                with self.assertRaisesRegex(ValueError, "internal_pass_count_mismatch"):
                    forensic.report_semantics(d)

    def test_scope_gaps_are_not_equated_with_absent_or_certified_releases(self):
        out=forensic.inspect(ROOT)
        self.assertEqual("HISTORICAL_SOURCE_DISCREPANCY_REPRODUCED_REVIEW_PENDING", out["status"])
        self.assertNotIn("accuracy_score", out["v100"])
        self.assertIsNone(out["quality_score"])


if __name__ == "__main__":
    unittest.main()
