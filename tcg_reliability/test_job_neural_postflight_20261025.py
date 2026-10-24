"""Offline guard tests for collection Job neural learning inputs."""
import unittest

from verified_collection_job_neural import _eligible_result, ingest_verified_report, JOB_KEYS


class JobNeuralPostflightTests(unittest.TestCase):
    def test_missing_postflight_cannot_ingest(self):
        report = {"results": [{"file": "anything.json", "ok": True}]}
        result = ingest_verified_report(report, {})
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["reason"], "postflight_not_verified")

    def test_preflight_blocked_and_disabled_attempts_rejected(self):
        key = next(iter(JOB_KEYS))
        self.assertFalse(_eligible_result(key, {"ok": True, "preflight_blocked": True}))
        self.assertFalse(_eligible_result(key, {"ok": True, "max_attempts": 0}))
        self.assertFalse(_eligible_result(key, {"status": "cooldown"}))

    def test_unknown_job_rejected(self):
        self.assertFalse(_eligible_result("__not_a_real_job__", {"ok": True}))


if __name__ == "__main__":
    unittest.main()
