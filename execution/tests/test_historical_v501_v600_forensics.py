"""Strict W501 selected Git-source and 24+7 finding preservation regressions."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import historical_v501_v600_forensics as audit

ROOT=Path(__file__).resolve().parents[2]


class W501ForensicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.originals={p:audit.read_object(ROOT,audit.BASE,p,sha)
                       for p,sha in audit.PINNED.items()}
        cls.parent=audit.parse(audit.git(ROOT,"show","HEAD:"+audit.PARENT_LEDGER))
        cls.prior=audit.parse(audit.git(ROOT,"show","HEAD:"+audit.PARENT_W401))
        cls.delta=audit.parse(audit.git(ROOT,"show","HEAD:"+audit.DELTA))

    def check(self):
        return audit.analyze(self.originals,self.parent,self.prior,self.delta)

    def test_twelve_exact_original_git_blobs(self):
        result=audit.inspect(ROOT)
        self.assertEqual(12,result["pinned_git_blobs"])
        self.assertEqual(audit.BASE,result["baseline_main_sha"])

    def test_six_selected_versions_no_fake_full_review(self):
        row=self.check()
        self.assertEqual([503,516,546,563,566,599],row["selected_versions"])
        self.assertEqual(6,len(row["selected_source_and_test_records"]))
        self.assertFalse(row["entire_w501_window_reviewed"])
        self.assertIsNone(row["quality_score"])
        self.assertFalse(row["physical_tablet_verified"])
        self.assertEqual("SELECTED_GIT_SOURCE_TEST_SCOPE_ONLY",row["status"])

    def test_all_24_prior_plus_7_new_findings_link(self):
        row=self.check()
        self.assertEqual(24,len(row["previous_finding_ids"]))
        self.assertEqual(7,len(row["new_finding_ids"]))
        self.assertEqual(31,row["cumulative_finding_count"])
        self.assertEqual(31,len(set(row["cumulative_finding_ids"])))
        self.assertIn("W401-F001",row["cumulative_finding_ids"])

    def test_v503_test_scope_not_current_provider(self):
        row=next(v for v in self.check()["selected_source_and_test_records"]
                 if v["version"]==503)
        self.assertIn("NOT_LIVE_PROVIDER",row["scope"])
        self.assertIn("test_js_safe_link_function_and_syntax",row["test_functions_in_original_source"])
        self.assertFalse(row["current_head_tests_executed"])

    def test_v516_manual_prefill_no_device_receipt(self):
        row=next(v for v in self.check()["selected_source_and_test_records"]
                 if v["version"]==516)
        self.assertIn("NOT_LENOVO_RECEIPT",row["scope"])
        self.assertIn(b"window.confirm(",self.originals["tcg_local_collection_v505.js"])

    def test_v546_http403_is_mock_not_permission_proof(self):
        row=next(v for v in self.check()["selected_source_and_test_records"]
                 if v["version"]==546)
        self.assertIn("MOCK_HTTP403",row["scope"])
        self.assertIn(b"status=PENDING_EXTERNAL_PR",
                      self.originals[".github/workflows/tcg-static-data-refresh.yml"])

    def test_v563_offline_package_cannot_claim_tablet_import(self):
        row=next(v for v in self.check()["selected_source_and_test_records"]
                 if v["version"]==563)
        self.assertIn("NOT_TABLET_IMPORT",row["scope"])
        self.assertIn(b'"device_imported": False',
                      self.originals["execution/verify_tcg_artifact_v563.py"])

    def test_v566_saved_node_not_browser_render(self):
        row=next(v for v in self.check()["selected_source_and_test_records"]
                 if v["version"]==566)
        self.assertIn("NOT_RENDERED_TABLET_UI",row["scope"])

    def test_v599_official_msrp_not_sold_price(self):
        row=next(v for v in self.check()["selected_source_and_test_records"]
                 if v["version"]==599)
        self.assertIn("NOT_SOLD_PRICE_OR_STOCK",row["scope"])
        p=json.loads(self.originals["tcg_official_product_catalog_v599.json"])
        self.assertEqual(53,len(p["products"]))

    def test_bad_source_sha_or_path_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"immutable_git_blob_drift"):
            audit.read_object(ROOT,audit.BASE,"test_market_links_v503.py","0"*40)
        with self.assertRaisesRegex(ValueError,"invalid_immutable_reference"):
            audit.read_object(ROOT,audit.BASE,"../private.env","0"*40)

    def test_missing_source_assertion_rejected(self):
        originals=dict(self.originals)
        k="test_grade_collection_handoff_v516.py"
        originals[k]=originals[k].replace(b"test_identity_gate_with_region_and_card_number_cases",
                                          b"test_unchecked_identity")
        with self.assertRaisesRegex(ValueError,"missing_v516_identity_test"):
            audit.analyze(originals,self.parent,self.prior,self.delta)

    def test_removed_parent_w401_protection_rejected(self):
        d=copy.deepcopy(self.parent)
        d["findings"]=[x for x in d["findings"] if x["id"]!="W401-F001"]
        with self.assertRaisesRegex(ValueError,"lost_inherited_w401_finding"):
            audit.analyze(self.originals,d,self.prior,self.delta)

    def test_modified_parent_w401_list_rejected(self):
        d=copy.deepcopy(self.prior)
        d["findings"].pop()
        with self.assertRaisesRegex(ValueError,"incomplete_inherited_findings"):
            audit.analyze(self.originals,self.parent,d,self.delta)

    def test_fake_full_review_or_quality_or_device_claim_rejected(self):
        for k,v in [("entire_window_fully_reviewed",True),("grading_quality_score",99),
                    ("physical_tablet_verified",True)]:
            d=copy.deepcopy(self.delta)
            d[k]=v
            with self.subTest(k=k),self.assertRaisesRegex(ValueError,"false_w501_scope_or_inheritance"):
                audit.analyze(self.originals,self.parent,self.prior,d)

    def test_integer_zero_cannot_impersonate_false_device_or_review(self):
        for k in ("entire_window_fully_reviewed", "physical_tablet_verified"):
            d=copy.deepcopy(self.delta)
            d[k]=0
            with self.subTest(k=k),self.assertRaisesRegex(ValueError,"false_w501_scope_or_inheritance"):
                audit.analyze(self.originals,self.parent,self.prior,d)

    def test_duplicate_or_deleted_new_finding_rejected(self):
        d=copy.deepcopy(self.delta)
        d["findings"][1]["id"]=d["findings"][0]["id"]
        with self.assertRaisesRegex(ValueError,"duplicate_or_missing_w501_findings"):
            audit.analyze(self.originals,self.parent,self.prior,d)
        d=copy.deepcopy(self.delta)
        d["findings"].pop()
        with self.assertRaisesRegex(ValueError,"missing_seven_w501_findings"):
            audit.analyze(self.originals,self.parent,self.prior,d)

    def test_fake_automatic_patch_or_runtime_bug_claim_rejected(self):
        d=copy.deepcopy(self.delta)
        d["findings"][0]["patch_eligible"]=True
        with self.assertRaisesRegex(ValueError,"unsupported_w501_review_or_release_claim"):
            audit.analyze(self.originals,self.parent,self.prior,d)

    def test_fixture_tests_and_source_review_not_conflated(self):
        for row in self.check()["selected_source_and_test_records"]:
            self.assertTrue(row["test_functions_in_original_source"])
            self.assertFalse(row["source_review_complete"])
            self.assertFalse(row["current_head_tests_executed"])
            self.assertIsNone(row["quality_score"])

    def test_readonly_inspection_does_not_write_to_repo(self):
        before=subprocess.check_output(["git","status","--porcelain"],cwd=ROOT)
        audit.inspect(ROOT)
        self.assertEqual(before,subprocess.check_output(["git","status","--porcelain"],cwd=ROOT))


if __name__=="__main__":
    unittest.main()
