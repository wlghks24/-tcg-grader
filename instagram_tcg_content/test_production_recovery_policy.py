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

    def test_matrix_coverage_gap_gets_first_bounded_refresh(self):
        decision = decide_preproduction_recovery(
            {
                "production_ready": False,
                "general_cardinfo_ready": False,
                "market_price_ready": False,
                "status": "NOT_READY",
                "reasons": ["OUTPUT_MATRIX_COVERAGE_MISSING:pokemon:KR,naruto:EN"],
            },
            is_production_slot=True,
            recovery_collection_attempts=0,
        )
        self.assertEqual(decision.action, RECOVERY_MODE)
        self.assertTrue(decision.run_bounded_collection)

    def test_latest_failed_collection_attempt_gets_one_refresh(self):
        decision = decide_preproduction_recovery(
            {
                "production_ready": False,
                "general_cardinfo_ready": False,
                "market_price_ready": False,
                "status": "NOT_READY",
                "reasons": ["LATEST_COLLECTION_ATTEMPT_NOT_READY:NO_VERIFIED_FACTS"],
            },
            is_production_slot=True,
            recovery_collection_attempts=0,
        )
        self.assertEqual(decision.action, RECOVERY_MODE)
        self.assertTrue(decision.run_bounded_collection)

    def test_malformed_or_invalid_snapshot_gets_one_rebuild_attempt(self):
        for reason in (
            "SNAPSHOT_FACTS_INVALID",
            "SNAPSHOT_BUILT_AT_INVALID",
            "MALFORMED_VERIFIED_FACTS:2",
            "DUPLICATE_FACT_LINEAGE:1",
        ):
            with self.subTest(reason=reason):
                decision = decide_preproduction_recovery(
                    {
                        "production_ready": False,
                        "general_cardinfo_ready": False,
                        "market_price_ready": False,
                        "status": "NOT_READY",
                        "reasons": [reason],
                    },
                    is_production_slot=True,
                    recovery_collection_attempts=0,
                )
                self.assertEqual(decision.action, RECOVERY_MODE)
                self.assertTrue(decision.run_bounded_collection)

    def test_route_configuration_gap_does_not_waste_collection_retry(self):
        for reason in (
            "PROVIDER_GROUP_MISSING:pokemon",
            "OFFICIAL_ROUTE_SHORTAGE:pokemon:0/1",
            "COMPLETED_SALE_ROUTE_SHORTAGE:one_piece:1/2",
            "MARKET_ROUTE_SHORTAGE:naruto:1/2",
            "PROVIDER_GROUPS_MISSING",
        ):
            with self.subTest(reason=reason):
                decision = decide_preproduction_recovery(
                    {
                        "production_ready": False,
                        "general_cardinfo_ready": False,
                        "market_price_ready": False,
                        "status": "NOT_READY",
                        "reasons": [reason],
                    },
                    is_production_slot=True,
                    recovery_collection_attempts=0,
                )
                self.assertEqual(decision.action, BLOCKED_MODE)
                self.assertFalse(decision.run_bounded_collection)
                self.assertEqual(
                    decision.reason,
                    "SOURCE_ROUTE_CONFIGURATION_NOT_RECOVERABLE_BY_COLLECTION",
                )

    def test_second_failure_blocks_render_but_never_silences_report(self):
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
