"""V101–V109 report-source audit; never run historical mutable verification scripts."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v101_v109_forensics as hist

ROOT = Path(__file__).resolve().parents[2]


class HistoricalV101V109Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reports = {
            version: hist._parse(hist.git(
                ROOT, "show", f"{hist.BASE}:V{version}_FINAL_VERIFICATION_REPORT.json"))
            for version in hist.REPORT_BLOBS
        }

    def test_pinned_protected_main_git_blob_verification(self):
        obj = hist.inspect(ROOT)
        self.assertEqual(9, obj["reviewed_historical_report_count"])
        self.assertIsNone(obj["quality_score"])
        self.assertEqual("DEVICE_UNVERIFIED", obj["device"])
        self.assertEqual(0, obj["complete_code_reviews"])

    def test_report_ok_does_not_mean_runtime_certification(self):
        obj = hist.analyze(copy.deepcopy(self.reports))
        self.assertEqual("NOT_EXECUTED_BY_FORENSIC_TOOL", obj["current_head_tests_per_version"])
        self.assertFalse(obj["v101"]["real_photo_accuracy_verified"])
        self.assertFalse(obj["v104"]["hardware_camera_verified"])

    def test_v101_small_synthetic_evidence_and_nonadoption(self):
        obj = hist.analyze(copy.deepcopy(self.reports))
        self.assertEqual((12, 24), (obj["v101"]["synthetic_positive"],
                                    obj["v101"]["synthetic_negative"]))
        self.assertIs(obj["v101"]["calibration_adopted"], False)

    def test_v108_verified_only_one_not_two_hundred_training_rows(self):
        obj = hist.analyze(copy.deepcopy(self.reports))
        self.assertEqual(200, obj["v108"]["files_scanned"])
        self.assertEqual(1, obj["v108"]["officially_verified_certifications"])
        self.assertEqual(199, obj["v108"]["quarantined_files"])
        self.assertEqual(0, obj["v108"]["training_rows_written"])

    def test_v105_v107_live_credentials_and_v106_v107_publication_hold(self):
        obj = hist.analyze(copy.deepcopy(self.reports))
        self.assertFalse(obj["v105_v107"]["real_social_credentials_exercised"])
        self.assertFalse(obj["v105_v107"]["v106_v107_published"])

    def test_missing_version_report_is_fail_closed(self):
        reports = copy.deepcopy(self.reports)
        reports.pop(108)
        with self.assertRaisesRegex(ValueError, "missing_versions"):
            hist.analyze(reports)

    def test_corrupted_v108_counts_rejected(self):
        reports = copy.deepcopy(self.reports)
        for check in reports[108]["checks"]:
            detail = check.get("detail", "")
            if '"officially_verified_certifications"' in detail:
                check["detail"] = detail.replace('"training_rows_written": 0',
                                                  '"training_rows_written": 200')
        with self.assertRaisesRegex(ValueError, "v108_count_invariants"):
            hist.analyze(reports)

    def test_false_v105_live_api_claim_is_rejected(self):
        reports = copy.deepcopy(self.reports)
        reports[105]["live_credential_note"] = "live authenticated calls all passed"
        with self.assertRaisesRegex(ValueError, "v105_live_not_executed"):
            hist.analyze(reports)

    def test_v104_digital_deblur_overclaim_blocked(self):
        reports = copy.deepcopy(self.reports)
        reports[104]["note"] = "We verified actual tablet digital deblurring"
        with self.assertRaisesRegex(ValueError, "v104_not_digital_deblur"):
            hist.analyze(reports)

    def test_v109_auto_training_promotion_is_rejected(self):
        reports = copy.deepcopy(self.reports)
        reports[109]["policy"]["automatic_ocr_predictions_train"] = True
        with self.assertRaisesRegex(ValueError, "v109_policy"):
            hist.analyze(reports)

    def test_pinned_report_parsing_rejects_duplicate_and_nonfinite_json(self):
        for raw, reason in ((b'{"ok":true,"ok":false}', "duplicate_historical_report_key"),
                            (b'{"x":NaN}', "historical_report_nonfinite")):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, reason):
                hist._parse(raw)

    def test_no_repo_mutation_by_read_only_forensics(self):
        before = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True)
        hist.inspect(ROOT)
        after = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
