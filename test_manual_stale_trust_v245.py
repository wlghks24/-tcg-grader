import math
import unittest

import manual_collection_mode as mode


class ManualStaleTrustV245Tests(unittest.TestCase):
    def _stale_row(self, **overrides):
        row = {
            "company": "PSA",
            "certification_id": "12345678",
            "grade": 10,
            "official_result": True,
            "official_grade": 10,
            "verification_method": "live_official_lookup",
            "official_lookup_status": "healthy",
            "official_verification": "verified",
            "manual_official_verification_required": False,
            "official_lookup_suppressed": False,
            "automatic_official_lookup_used": True,
        }
        row.update(overrides)
        return row

    def test_stale_trust_is_cleared_when_registry_cannot_revalidate_candidate(self):
        cases = [
            (self._stale_row(), {}),
            (self._stale_row(), {("PSA", "12345678"): 9}),
            (self._stale_row(company="UNKNOWN"), {}),
            (self._stale_row(certification_id=""), {}),
            (self._stale_row(grade=float("nan")), {}),
        ]
        for original, registry in cases:
            with self.subTest(company=original.get("company"), cert=original.get("certification_id"), grade=original.get("grade")):
                snapshot = dict(original)
                out, stats = mode._registry_only_official_verify_rows([original], registry)
                result = out[0]

                self.assertFalse(result["official_result"])
                self.assertTrue(result["manual_official_verification_required"])
                self.assertNotEqual(result.get("verification_method"), "live_official_lookup")
                self.assertNotIn("official_grade", result)
                self.assertNotIn("official_lookup_status", result)
                self.assertEqual(result.get("official_verification"), "manual_verification_required" if not result.get("evidence_conflicts") else "manual_registry_grade_conflict")
                self.assertTrue(result.get("official_lookup_suppressed"))
                self.assertFalse(result.get("automatic_official_lookup_used"))
                self.assertEqual(original, snapshot, "runtime boundary must not mutate caller-owned candidate rows")
                self.assertEqual(stats["live_attempts"], 0)

    def test_trust_is_rebuilt_only_after_exact_registry_match(self):
        original = self._stale_row(official_grade=9, verification_method="stale_source")
        snapshot = dict(original)
        out, stats = mode._registry_only_official_verify_rows(
            [original], {("PSA", "12345678"): 10}
        )
        result = out[0]

        self.assertTrue(result["official_result"])
        self.assertEqual(result["official_grade"], 10)
        self.assertEqual(result["verification_method"], "persisted_official_registry")
        self.assertEqual(result["official_verification"], "validated_manual_registry")
        self.assertFalse(result["manual_official_verification_required"])
        self.assertTrue(result["official_lookup_suppressed"])
        self.assertFalse(result["automatic_official_lookup_used"])
        self.assertEqual(stats["registry_matches"], 1)
        self.assertEqual(stats["conflicts"], 0)
        self.assertEqual(stats["live_attempts"], 0)
        self.assertEqual(original, snapshot)


if __name__ == "__main__":
    unittest.main()
