from __future__ import annotations
import unittest

from market_ai_decision_engine import (
    DecisionStatus,
    EvidenceRecord,
    decide,
    grading_fusion,
    persistence_can_finalize,
    repeated_error_action,
    source_health,
)


class MarketAIDecisionEngineTests(unittest.TestCase):
    def evidence(self, **overrides):
        base = dict(
            evidence_id="e1",
            fact_type="card_price",
            identity="pokemon:test:001",
            value=100000,
            value_type="market_price",
            freshness="2026-09-06T09:00:00+09:00",
            source_locator="https://example.invalid/item/1",
            source_role="official",
            lineage_key="lineage-1",
            verification_status="verified",
            effective_date="2026-09-06",
        )
        base.update(overrides)
        return EvidenceRecord(**base)

    def test_good_local_primary_can_verify(self):
        packet = decide([self.evidence()])
        self.assertEqual(packet.status, DecisionStatus.VERIFIED)
        self.assertGreaterEqual(packet.confidence, 0.72)

    def test_peer_verified_never_auto_promotes(self):
        packet = decide([self.evidence(peer=True)])
        self.assertEqual(packet.status, DecisionStatus.PROVISIONAL)
        self.assertIn("PEER_ONLY_EVIDENCE", packet.reason_codes)

    def test_market_reference_cannot_be_completed_sale(self):
        row = self.evidence(
            fact_type="completed_sale",
            value_type="realized_amount",
            source_role="market_reference",
            transaction_finality="sold",
        )
        packet = decide([row])
        self.assertEqual(packet.status, DecisionStatus.QUARANTINE)
        self.assertIn("MARKET_REFERENCE_CANNOT_PROMOTE_TO_COMPLETED_SALE", packet.reason_codes)

    def test_completed_sale_requires_finality(self):
        row = self.evidence(
            fact_type="completed_sale",
            value_type="realized_amount",
            source_role="completed_sale_primary",
            transaction_finality=None,
        )
        packet = decide([row])
        self.assertEqual(packet.status, DecisionStatus.QUARANTINE)

    def test_independent_value_conflict_is_not_silently_resolved(self):
        a = self.evidence(lineage_key="a", evidence_id="a", value=100000)
        b = self.evidence(lineage_key="b", evidence_id="b", value=130000)
        packet = decide([a, b])
        self.assertEqual(packet.status, DecisionStatus.CONFLICT)
        self.assertEqual(set(packet.conflict_values), {100000, 130000})

    def test_same_lineage_is_deduplicated(self):
        a = self.evidence(lineage_key="same", evidence_id="a", value=100000)
        b = self.evidence(lineage_key="same", evidence_id="b", value=100000, source_role="market_reference")
        packet = decide([a, b])
        self.assertEqual(packet.lineage_count, 1)

    def test_placeholder_is_fail_closed(self):
        packet = decide([self.evidence(metadata={"marker": "placeholder"})])
        self.assertEqual(packet.status, DecisionStatus.QUARANTINE)

    def test_http_200_without_semantic_parse_is_not_healthy(self):
        result = source_health(
            http_ok=True, parsed_identity=False, parsed_value=False,
            parsed_date=False, parsed_source=False,
        )
        self.assertFalse(result["healthy"])
        self.assertEqual(result["state"], "semantic_parse_failed")

    def test_403_429_bypass_is_never_allowed(self):
        for status in (403, 429):
            result = source_health(
                http_ok=False, parsed_identity=False, parsed_value=False,
                parsed_date=False, parsed_source=False, blocked_status=status,
            )
            self.assertFalse(result["healthy"])
            self.assertFalse(result["bypass_allowed"])

    def test_repeated_error_changes_strategy_before_retry(self):
        second = repeated_error_action(2)
        third = repeated_error_action(3)
        self.assertFalse(second["plain_retry"])
        self.assertEqual(second["action"], "change_strategy_before_retry")
        self.assertEqual(third["action"], "quarantine_and_alternate")

    def test_grading_fusion_reports_uncertainty(self):
        result = grading_fusion([9.5] * 8, artifact_risk=0.2, lighting_risk=0.1)
        self.assertEqual(result["status"], "PREDICTIVE_ONLY")
        self.assertLess(result["confidence"], 1.0)
        self.assertFalse(result["raw_calibration_share_allowed"])
        self.assertAlmostEqual(sum(result["grade_probabilities"].values()), 1.0, places=3)

    def test_persistence_requires_every_readback_gate(self):
        all_pass = {
            "manifest_fetch": True,
            "building_write": True,
            "building_readback": True,
            "schema_validation": True,
            "isolation_validation": True,
            "finalized_write": True,
            "finalized_readback": True,
        }
        self.assertTrue(persistence_can_finalize(all_pass))
        all_pass["building_readback"] = False
        self.assertFalse(persistence_can_finalize(all_pass))


if __name__ == "__main__":
    unittest.main()
