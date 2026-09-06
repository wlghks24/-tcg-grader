from __future__ import annotations

import unittest

import ai_reasoning_enhancer as enhancer


class AIReasoningEnhancerTests(unittest.TestCase):
    def test_explicit_domain_has_high_confidence(self):
        out = enhancer.domain_assessment({"domain": "tablet", "message": "price source failed"})
        self.assertEqual(out["domain"], "tablet")
        self.assertGreaterEqual(out["confidence"], 0.95)
        self.assertFalse(out["ambiguous"])

    def test_ambiguous_event_requires_review(self):
        out = enhancer.enrich_incident({"message": "unknown failure"})
        self.assertTrue(out["assessment"]["human_review_required"])
        self.assertEqual(out["assessment"]["root_cause"]["family"], "unknown")

    def test_rate_limit_is_market_and_never_bypass(self):
        out = enhancer.enrich_incident({
            "severity": "high",
            "message": "price collector HTTP 429 Retry-After 60",
            "path": "multi_market_price_collector.py",
            "error_type": "HTTPError",
            "evidence": "source returned 429",
        }, occurrences=3)
        self.assertEqual(out["assessment"]["domain"]["domain"], "market")
        self.assertEqual(out["assessment"]["root_cause"]["family"], "network_rate_limit")
        self.assertTrue(any("Retry-After" in row for row in out["recommended_checks"]))
        self.assertTrue(any("do not bypass" in row.lower() for row in out["recommended_checks"]))
        self.assertFalse(out["safety"]["auto_patch_from_reasoning"])

    def test_tablet_recurrence_escalates(self):
        event = {
            "domain": "tablet",
            "severity": "high",
            "stage": "BOOT_HEALTH",
            "path": "ANDROID_AUTO_START_INSTALL.sh",
            "error_type": "TimeoutError",
            "message": "Termux reboot health check timed out localhost 8765",
            "evidence": "api/v135-health unavailable",
        }
        one = enhancer.enrich_incident(event, occurrences=1, code_map={"available": True})
        many = enhancer.enrich_incident(
            event,
            occurrences=8,
            code_map={"available": True, "structural_risk": "high"},
        )
        self.assertGreater(many["assessment"]["score"], one["assessment"]["score"])
        self.assertEqual(many["assessment"]["recurrence"]["level"], "persistent")
        self.assertIn(many["assessment"]["priority"], {"P0", "P1"})

    def test_evidence_quality_rewards_verified_structure(self):
        event = {
            "stage": "CI",
            "path": "x.py",
            "error_type": "AssertionError",
            "message": "test failed",
            "evidence": "assertion mismatch",
            "changed_files": ["x.py"],
            "regression_pass": False,
            "verification": "verified",
        }
        out = enhancer.evidence_quality(event, {"available": True})
        self.assertEqual(out["level"], "high")
        self.assertGreaterEqual(out["score"], 0.72)

    def test_code_map_targeted_tests_are_recommended_first(self):
        out = enhancer.enrich_incident(
            {
                "domain": "github",
                "severity": "high",
                "stage": "CI",
                "path": "collector.py",
                "message": "regression test failed",
            },
            code_map={
                "available": True,
                "structural_risk": "medium",
                "suggested_tests": ["test_collector.py", "test_runtime_delivery_guards.py"],
            },
        )
        self.assertIn("test_collector.py", out["recommended_checks"][0])
        self.assertTrue(any("test_runtime_delivery_guards.py" in row for row in out["recommended_checks"]))

    def test_stale_code_map_requires_review_for_high_severity(self):
        out = enhancer.enrich_incident(
            {
                "domain": "github",
                "severity": "high",
                "stage": "CI",
                "path": "collector.py",
                "error_type": "AssertionError",
                "message": "test failed",
                "evidence": "assertion mismatch",
            },
            code_map={
                "available": True,
                "status": "stale_for_origin",
                "structural_risk": "medium",
                "confidence": 0.55,
            },
        )
        self.assertTrue(out["assessment"]["human_review_required"])

    def test_secret_redaction(self):
        text = enhancer._clean("Bearer abc.def api_key=xyz token=123 https://example.com/a")
        self.assertNotIn("abc.def", text)
        self.assertNotIn("xyz", text)
        self.assertNotIn("123", text)
        self.assertNotIn("example.com", text)

    def test_tracker_report_enrichment_is_read_only_shape(self):
        source = {
            "schema": 1,
            "incidents": [{
                "incident_id": "abc",
                "domain": "github",
                "severity": "medium",
                "stage": "CI",
                "path": "test_x.py",
                "error_type": "AssertionError",
                "message": "regression test failed",
                "occurrences": 2,
                "code_map": {"available": True, "structural_risk": "low"},
            }],
        }
        out = enhancer.enrich_tracker_report(source)
        self.assertEqual(source["incidents"][0]["incident_id"], "abc")
        self.assertEqual(out["summary"]["reasoned"], 1)
        self.assertTrue(out["safety"]["read_only_report_enrichment"])
        self.assertFalse(out["safety"]["auto_patch_from_reasoning"])

    def test_parser_schema_recommends_quarantine(self):
        out = enhancer.enrich_incident({
            "domain": "market",
            "severity": "high",
            "stage": "COLLECT",
            "path": "update_releases.py",
            "error_type": "ValueError",
            "message": "parser schema structure changed",
            "evidence": "unexpected field",
        })
        self.assertEqual(out["assessment"]["root_cause"]["family"], "parser_schema")
        self.assertTrue(any("Quarantine" in row for row in out["recommended_checks"]))


if __name__ == "__main__":
    unittest.main()
