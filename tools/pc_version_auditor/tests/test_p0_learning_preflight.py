"""P0 verified training and POST preservation: negative-path static regressions."""
from __future__ import annotations
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pc_auditor"))
import audit
import p0_learning_preflight as preflight


def grading(expr: str) -> bytes:
    return ("def sanitize_sample(sample, legacy_verified=False):\n"
            "    verified = " + expr + "\n"
            "    if not verified: raise ValueError('unverified')\n"
            "    return verified\n").encode("utf-8")


def updater(dictionary: str) -> bytes:
    return ("def do_post(post_path):\n"
            "    if post_path == '/api/learning-store':\n"
            "        data = " + dictionary + "\n"
            "        save_json_atomic(LEARNING_STORE, data)\n").encode("utf-8")


class P0LearningPreflightTests(unittest.TestCase):
    def test_truthy_verified_flag_is_held(self):
        for value in ("bool(sample.get('verified', legacy_verified))",
                      "bool(sample.get('verified'))"):
            with self.subTest(value=value):
                r = preflight.inspect_grading(grading(value))
                self.assertEqual("HOLD_TRUTHY_VERIFICATION", r["status"])

    def test_string_comparison_is_not_approved(self):
        for value in ("sample.get('verified') == 'true'",
                      "sample.get('verified', legacy_verified)",
                      "sample.get('verified') == True"):
            with self.subTest(value=value):
                self.assertEqual("HOLD_VERIFICATION_SEMANTICS_UNKNOWN",
                                 preflight.inspect_grading(grading(value))["status"])

    def test_explicit_true_requires_real_regression(self):
        result = preflight.inspect_grading(grading(
            "sample.get('verified', legacy_verified) is True"))
        self.assertEqual("STATIC_TRUE_GUARD_PRESENT_REQUIRES_REGRESSION", result["status"])

    def test_missing_verified_assignment_fails_closed(self):
        result = preflight.inspect_grading(b"def sanitize_sample(sample):\n    return 1\n")
        self.assertEqual("HOLD_VERIFICATION_SEMANTICS_UNKNOWN", result["status"])

    def test_missing_sanitizer_fails_closed(self):
        result = preflight.inspect_grading(b"def other():\n    return True\n")
        self.assertEqual("HOLD_SOURCE_SHAPE_UNKNOWN", result["status"])

    def test_three_validation_arrays_omit_certified_evidence(self):
        data = "{'version':2,'v99_validation': [],'v30_validation': [],'v11_validation': []}"
        self.assertEqual("HOLD_CONFIRMED_SAMPLES_DISCARDED",
                         preflight.inspect_updater(updater(data))["status"])

    def test_comment_or_unrelated_variable_cannot_fake_preservation(self):
        raw = updater("{'v99_validation': []}") + b"\n# confirmed_samples\n"
        self.assertEqual("HOLD_CONFIRMED_SAMPLES_DISCARDED",
                         preflight.inspect_updater(raw)["status"])

    def test_explicit_field_is_still_not_runtime_proof(self):
        self.assertEqual("HOLD_PERSISTENCE_SEMANTICS_REVIEW",
                         preflight.inspect_updater(updater("{'confirmed_samples': []}"))["status"])

    def test_absent_endpoint_fails_closed(self):
        self.assertEqual("HOLD_POST_ENDPOINT_UNKNOWN",
                         preflight.inspect_updater(b"def do_post(post_path):\n    return 1\n")["status"])

    def test_unrecognized_write_is_held(self):
        raw = b"def do_post(post_path):\n    if post_path == '/api/learning-store':\n        other_save(LEARNING_STORE, {})\n"
        self.assertEqual("HOLD_SAVE_OPERATION_UNKNOWN",
                         preflight.inspect_updater(raw)["status"])

    def test_missing_files_never_approve(self):
        r = preflight.evaluate({}, head="a"*40)
        self.assertEqual("HOLD_P0_RUNTIME_NOT_APPROVED", r["status"])
        self.assertFalse(r["next_window_allowed"])
        self.assertEqual(2, len(r["findings"]))
        self.assertTrue(all(x["status"] == "HOLD_SOURCE_ABSENT" for x in r["findings"]))
        self.assertFalse(r["physical_device_verified"])

    def test_malformed_source_fails_closed(self):
        r = preflight.evaluate({"grading_self_learning.py": b"def !!!",
                                "tcg_updater.py": b"\xff"}, head="b"*40)
        self.assertEqual(2, sum(x["status"] == "HOLD_UNPARSEABLE_SOURCE"
                                for x in r["findings"]))

    def test_source_size_is_bounded(self):
        with self.assertRaisesRegex(audit.AuditError, "p0_source_too_large"):
            preflight.evaluate({"tcg_updater.py": b"x"*(preflight.MAX_SOURCE+1)}, head="c"*40)

    def test_source_receipts_hash_exact_bytes(self):
        g=grading("sample.get('verified') is True")
        u=updater("{'confirmed_samples': []}")
        a=preflight.evaluate({"grading_self_learning.py":g,"tcg_updater.py":u},head="d"*40)
        b=preflight.evaluate({"grading_self_learning.py":g,"tcg_updater.py":u},head="d"*40)
        self.assertEqual(a,b)
        self.assertEqual(64,len(a["findings"][0]["source_sha256"]))
        self.assertEqual(64,len(a["findings"][1]["source_sha256"]))
        self.assertEqual("NOT_RUN",a["functional_test"])


if __name__ == "__main__":
    unittest.main()
