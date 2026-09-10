#!/usr/bin/env python3
import unittest

from instagram_tcg_content.production_recovery_policy import (
    BLOCKED_MODE,
    GENERAL_MODE,
    RECOVERY_MODE,
    build_visible_failure_report,
    decide_preproduction_recovery,
)


class ProductionRecoveryPolicyTests(unittest.TestCase):
    def test_stale_production_slot_gets_one_bounded_collection_recovery(self):
        report = {
            "production_ready": False,
            "general_cardinfo_ready": False,
            "market_price_ready": False,
            "status": "NOT_READY",
            "reasons": [
                "SNAPSHOT_STALE:88.0h>36h",
                "COMPLETED_SALE_COVERAGE_INSUFFICIENT",
            ],
        }
        decision = decide_preproduction_recovery(
            report,
            is_production_slot=True,
            recovery_collection_attempts=0,
        )
        self.assertEqual(decision.action, RECOVERY_MODE)
        self.assertTrue(decision.run_bounded_collection)
        self.assertFalse(decision.render_allowed)
        self.assertFalse(decision.market_sections_allowed)
        self.assertTrue(decision.must_emit_visible_report)
        self.assertEqual(decision.recovery_attempt_limit, 1)

    def test_second_general_failure_blocks_render_but_never_silences_report(self):
        report = {
            "production_ready": False,
            "general_cardinfo_ready": False,
            "market_price_ready": False,
            "status": "NOT_READY",
            "reasons": ["OUTPUT_MATRIX_COVERAGE_MISSING:pokemon:KR"],
        }
        decision = decide_preproduction_recovery(
            report,
            is_production_slot=True,
            recovery_collection_attempts=1,
        )
        self.assertEqual(decision.action, BLOCKED_MODE)
        self.assertFalse(decision.run_bounded_collection)
        self.assertFalse(decision.render_allowed)
        self.assertTrue(decision.must_emit_visible_report)

    def test_general_ready_market_not_ready_still_renders_without_price_sections(self):
        report = {
            "production_ready": True,
            "general_cardinfo_ready": True,
            "market_price_ready": False,
            "status": "GENERAL_READY_MARKET_NOT_READY",
            "reasons": ["COMPLETED_SALE_COVERAGE_INSUFFICIENT"],
        }
        decision = decide_preproduction_recovery(
            report,
            is_production_slot=True,
            recovery_collection_attempts=0,
        )
        self.assertEqual(decision.action, GENERAL_MODE)
        self.assertTrue(decision.render_allowed)
        self.assertFalse(decision.market_sections_allowed)
        self.assertFalse(decision.run_bounded_collection)
        self.assertTrue(decision.must_emit_visible_report)

    def test_nonproduction_slot_does_not_trigger_render_recovery(self):
        decision = decide_preproduction_recovery(
            {
                "production_ready": False,
                "general_cardinfo_ready": False,
                "market_price_ready": False,
                "status": "NOT_READY",
                "reasons": ["SNAPSHOT_STALE:88.0h>36h"],
            },
            is_production_slot=False,
            recovery_collection_attempts=0,
        )
        self.assertEqual(decision.action, BLOCKED_MODE)
        self.assertFalse(decision.run_bounded_collection)
        self.assertFalse(decision.render_allowed)
        self.assertTrue(decision.must_emit_visible_report)

    def test_ready_collection_goes_to_full_preflight(self):
        decision = decide_preproduction_recovery(
            {
                "production_ready": True,
                "general_cardinfo_ready": True,
                "market_price_ready": True,
                "status": "READY",
                "reasons": [],
            },
            is_production_slot=True,
            recovery_collection_attempts=0,
        )
        self.assertTrue(decision.render_allowed)
        self.assertTrue(decision.market_sections_allowed)
        self.assertFalse(decision.run_bounded_collection)
        self.assertTrue(decision.must_emit_visible_report)

    def test_visible_failure_report_contains_split_readiness_fields(self):
        report = build_visible_failure_report(
            scheduled_slot_kst="2026-09-10T10:30:00+09:00",
            collection_report={
                "status": "NOT_READY",
                "general_cardinfo_ready": False,
                "market_price_ready": False,
                "unique_fact_count": 1,
                "matrix_counts": {
                    "pokemon:KR": 0,
                    "pokemon:EN": 0,
                    "one_piece:KR": 0,
                    "one_piece:EN": 0,
                    "naruto:KR": 0,
                    "naruto:EN": 0,
                },
                "completed_sale_counts": {
                    "pokemon:KR": 0,
                    "pokemon:EN": 0,
                    "one_piece:KR": 0,
                    "one_piece:EN": 0,
                    "naruto:KR": 0,
                    "naruto:EN": 0,
                },
                "next_action": "RUN_BOUNDED_FULL_COLLECTION_AND_PERSIST_VERIFIED_IG_FACTS",
            },
            producer_phase="COLLECTION_HEALTH",
            exchange_status="RUN_INVOKED_NO_PRODUCER_RECEIPT",
            recovery_collection_attempted=True,
            artifact_count=0,
        )
        self.assertEqual(report["OUTPUT_STATUS"], "MISSING")
        self.assertEqual(report["FAILED_STAGE"], "COLLECTION_HEALTH")
        self.assertEqual(report["ERROR_CODE"], "GENERAL_CARDINFO_NOT_READY")
        self.assertEqual(report["ROOT_CAUSE"], "VERIFIED_GENERAL_CARDINFO_REQUIREMENTS_NOT_MET")
        self.assertFalse(report["GENERAL_CARDINFO_READY"])
        self.assertFalse(report["MARKET_PRICE_READY"])
        self.assertFalse(report["RENDER_ATTEMPTED"])
        self.assertEqual(report["ARTIFACT_COUNT"], 0)
        self.assertTrue(report["automation_continues"])
        self.assertTrue(report["must_emit_visible_report"])


if __name__ == "__main__":
    unittest.main()
