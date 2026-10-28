"""W601–W700 selected original source and carried-finding integrity tests."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v601_v700_forensics as audit

ROOT = Path(__file__).resolve().parents[2]


class W601ForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = audit.review(ROOT)

    def test_seven_selected_versions_and_no_full_window_claim(self):
        self.assertEqual([619, 645, 646, 653, 657, 661, 664],
                         self.result["selected_version_ids"])
        self.assertFalse(self.result["all_100_versions_reviewed"])
        self.assertFalse(self.result["current_head_target_tests_executed"])
        self.assertIsNone(self.result["quality_score"])

    def test_all_eleven_original_git_blobs_pin_exact_baseline(self):
        self.assertEqual(11, len(self.result["selected_source_test_blobs"]))
        self.assertEqual(audit.BASE, self.result["baseline_main_sha"])
        for entry in self.result["selected_source_test_blobs"]:
            self.assertEqual(audit.PINNED[entry["path"]], entry["blob"])
            self.assertTrue(audit.read_object(ROOT, audit.BASE,
                                             entry["path"], entry["blob"]))

    def test_successor_receipt_is_not_device_install_proof(self):
        self.assertFalse(self.result["physical_tablet_verified"])
        for proof in self.result["proof_summaries"].values():
            self.assertFalse(proof["device_verified"])
            self.assertFalse(proof["deployment_allowed"])
            self.assertGreater(proof["reviewed_sha256_count"], 0)

    def test_v619_is_only_a_test_suite_registration(self):
        path="execution/tests/test_free_only_ai_code_improver_v619.py"
        text=audit.read_object(ROOT,audit.BASE,path,audit.PINNED[path]).decode()
        self.assertIn("from verify_ai_code_improver import ImproverTests",text)
        self.assertEqual([], self.result["test_function_names"][path])

    def test_v646_uses_immutable_source_and_tamper_tests(self):
        tests=self.result["test_function_names"]["execution/tests/test_tablet_successor_v646.py"]
        self.assertIn("test_exact_source_lineage",tests)
        self.assertIn("test_current_ui_tampering_cannot_delegate",tests)
        self.assertIn("test_historical_changes_and_non_head_checks_remain_visible",tests)

    def test_v657_supervisor_tests_are_fixture_clock_checks(self):
        tests=self.result["test_function_names"]["execution/tests/test_learning_scan_budget_v657.py"]
        self.assertIn("test_one_label_scan_for_fifteen_healthy_minute_ticks",tests)
        self.assertIn("test_failed_learning_waits_five_minutes_without_restarting_server",tests)

    def test_v661_missing_image_data_is_not_training_success(self):
        tests=self.result["test_function_names"]["execution/tests/test_image_autonomy_v661.py"]
        self.assertIn("test_missing_labels_are_waiting_not_false_training_success",tests)
        self.assertIn("test_low_resources_defer_optional_image_work",tests)

    def test_v664_invalid_challenger_is_kept_out_of_champion(self):
        tests=self.result["test_function_names"]["execution/tests/test_image_worker_isolation_v664.py"]
        self.assertIn("test_malformed_real_challenger_is_held_and_champion_is_untouched",tests)

    def test_all_previous_findings_referenced_not_reset(self):
        self.assertEqual(31,self.result["inherited_finding_count"])
        self.assertEqual(7,self.result["new_finding_count"])
        self.assertEqual(38,self.result["total_carried_finding_count"])
        self.assertEqual("SELECTED_PROVENANCE_ONLY_HOLD",self.result["status"])

    def test_wrong_original_git_sha_is_rejected(self):
        path="execution/tests/test_learning_scan_budget_v657.py"
        with self.assertRaisesRegex(ValueError,"original_git_blob_drift"):
            audit.read_object(ROOT,audit.BASE,path,"0"*40)

    def test_fake_approved_photo_successor_is_rejected(self):
        original=audit.read_object
        target=".github/tablet-autonomy/image_autonomy_successor_v661.json"
        def forged(root, commit, path, blob):
            raw=original(root,commit,path,blob)
            if path==target:
                d=json.loads(raw);d["deployment_allowed"]=True
                return json.dumps(d).encode()
            return raw
        with patch.object(audit,"read_object",side_effect=forged):
            with self.assertRaisesRegex(ValueError,"unexpected_successor_deploy_allowed"):
                audit.review(ROOT)

    def test_bad_inherited_count_is_rejected(self):
        actual=audit.git
        def forged(root,*args):
            raw=actual(root,*args)
            if len(args)>1 and args[0]=="show" and args[1]=="HEAD:"+audit.DELTA:
                d=json.loads(raw);d["inherited_finding_count"]=30
                return json.dumps(d).encode()
            return raw
        with patch.object(audit,"git",side_effect=forged):
            with self.assertRaisesRegex(ValueError,"broken_parent_finding_count"):
                audit.review(ROOT)

    def test_duplicates_nonfinite_and_empty_object_fail_closed(self):
        for raw,expected in [
            (b'{"a":1,"a":2}',"duplicate_json_key"),
            (b'{"v":NaN}',"nonfinite_evidence"),
            (b'[]',"evidence_not_object"),
        ]:
            with self.subTest(raw=raw),self.assertRaisesRegex(ValueError,expected):
                audit.parse(raw)

    def test_originals_parsed_not_executed_and_status_is_unchanged(self):
        before=subprocess.check_output(["git","status","--porcelain"],cwd=ROOT)
        second=audit.review(ROOT)
        after=subprocess.check_output(["git","status","--porcelain"],cwd=ROOT)
        self.assertEqual(before,after)
        self.assertEqual(self.result,second)
        self.assertFalse(second["current_head_target_tests_executed"])


if __name__=="__main__":
    unittest.main()
