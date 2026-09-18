from pathlib import Path
import json
import tempfile
import unittest

import quality_review_policy as q
import tablet_runtime_manifest as manifest

ROOT = Path(__file__).resolve().parent


class QualityReviewPolicyV2Tests(unittest.TestCase):
    def test_policy_has_exact_25_by_40_matrix(self):
        result = q.validate()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["expert_groups"], 25)
        self.assertEqual(result["review_lenses"], 40)
        self.assertEqual(result["review_cells"], 1000)

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

    def test_truthful_1000_lens_claim_is_enforced(self):
        data = json.loads(q.POLICY.read_text(encoding="utf-8"))
        self.assertFalse(data["tablet"]["claim_parallel_1000_external_reviewers"])
        self.assertIn("not a claim that 1000 external people", data["description"])

    def test_tablet_manifest_requires_and_validates_policy(self):
        self.assertIn("quality_review_policy.py", manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn("quality_review_policy_v2.json", manifest.ACTIVE_RUNTIME_FILES)
        result = manifest.audit(ROOT, compile_python=True)
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["quality_policy"]["ok"], result)
        self.assertEqual(result["quality_policy"]["review_cells"], 1000)

    def test_main_exposes_local_quality_check(self):
        entry = (ROOT / "main").read_text(encoding="utf-8")
        self.assertIn("quality)", entry)
        self.assertIn("quality_review_policy.py --check", entry)
        self.assertIn("bash main quality", entry)


if __name__ == "__main__":
    unittest.main()
