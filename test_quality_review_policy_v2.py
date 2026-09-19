from pathlib import Path
import json
import tempfile
import unittest

import quality_review_policy as q
import tablet_runtime_manifest as manifest

ROOT = Path(__file__).resolve().parent


class QualityReviewPolicyV2Tests(unittest.TestCase):
    def test_policy_has_100_senior_prep_then_exact_25_by_40_matrix(self):
        result = q.validate()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["preparation_senior_perspectives"], 100)
        self.assertTrue(result["preparation_before_expert_review"])
        self.assertEqual(result["expert_groups"], 25)
        self.assertEqual(result["review_lenses"], 40)
        self.assertEqual(result["review_cells"], 1000)

    def test_preparation_stage_is_separate_and_precedes_expert_review(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        prep = data["preparation_stage"]
        self.assertEqual(prep["independent_senior_perspectives"], 100)
        self.assertTrue(prep["separate_from_expert_review"])
        self.assertTrue(prep["must_run_before_expert_review"])
        self.assertFalse(prep["final_judgment_authority"])
        self.assertFalse(prep["claim_external_human_team"])
        self.assertEqual(prep["workflow"], q.REQUIRED_PREP_WORKFLOW)
        self.assertEqual(data["quality_pipeline"], q.REQUIRED_PIPELINE)
        self.assertEqual(data["quality_pipeline"][:2], ["100_senior_data_prep", "1000_expert_multi_lens_review"])

    def test_preparation_stage_requires_collection_cleanup_and_crosscheck(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        responsibilities = set(data["preparation_stage"]["responsibilities"])
        for token in (
            "normalization",
            "duplicate_removal",
            "typo_and_label_correction",
            "freshness_verification",
            "gap_analysis",
            "supplemental_collection",
            "cross_validation",
            "provenance_preservation",
        ):
            self.assertIn(token, responsibilities)

    def test_prep_count_or_order_tamper_fails_closed(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        data["preparation_stage"]["independent_senior_perspectives"] = 99
        data["quality_pipeline"][0], data["quality_pipeline"][1] = data["quality_pipeline"][1], data["quality_pipeline"][0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = q.validate(path)
        self.assertFalse(result["ok"])
        self.assertIn("prep_senior_count", result["errors"])
        self.assertIn("quality_pipeline", result["errors"])

    def test_prep_cross_validation_cannot_be_disabled(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        data["preparation_stage"]["rules"]["cross_validate_all_material_facts"] = False
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = q.validate(path)
        self.assertFalse(result["ok"])
        self.assertIn("prep_rules", result["errors"])

    def test_named_domains_are_present(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        names = " ".join(x["name"] for x in data["expert_groups"])
        for token in ("통역사", "회장", "프로그래머", "시니어 개발자", "SRE", "TCG", "Android", "감사"):
            self.assertIn(token, names)

    def test_policy_is_fail_closed_when_tampered(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        data["review_lenses"] = data["review_lenses"][:-1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = q.validate(path)
        self.assertFalse(result["ok"])
        self.assertIn("review_lens_count", result["errors"])

    def test_safety_cannot_be_weakened(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        data["safety"]["direct_main_push_allowed"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            result = q.validate(path)
        self.assertFalse(result["ok"])
        self.assertIn("safety_contract", result["errors"])

    def test_truthful_100_and_1000_lens_claims_are_enforced(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        self.assertFalse(data["tablet"]["claim_parallel_100_external_collectors"])
        self.assertFalse(data["tablet"]["claim_parallel_1000_external_reviewers"])
        self.assertIn("not a claim that 100 or 1000 external people", data["description"])

    def test_tablet_manifest_requires_and_validates_policy(self):
        self.assertIn("quality_review_policy.py", manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn("quality_review_policy_v2.json", manifest.ACTIVE_RUNTIME_FILES)
        result = manifest.audit(ROOT, compile_python=True)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["quality_policy"]["ok"], result)
        self.assertEqual(result["quality_policy"]["preparation_senior_perspectives"], 100)
        self.assertTrue(result["quality_policy"]["preparation_before_expert_review"])
        self.assertEqual(result["quality_policy"]["review_cells"], 1000)

    def test_main_exposes_local_quality_check(self):
        entry = (ROOT / "main").read_text(encoding="utf-8")
        self.assertIn("quality)", entry)
        self.assertIn("quality_review_policy.py --check", entry)
        self.assertIn("bash main quality", entry)


if __name__ == "__main__":
    unittest.main()
