"""Regression coverage for recovered market freshness and recovery-only gates.

These tests are intentionally read-only: no device state, model, or Git writes.
"""
import unittest
from datetime import datetime, timezone

import tablet_autonomous_evolution_v382 as v382
import tablet_autonomous_evolution_v385 as v385


class RecoveryGateRegressionTests(unittest.TestCase):
    def test_recovered_freshness_still_requires_recovery_action(self):
        old = v382._default_state()
        old["last_kpis"] = {
            "dimensions": {
                "market_freshness": 0.25,
                "market_coverage": 1.0,
                "source_health": 0.763158,
                "neural_consensus": 0.403,
                "resource_headroom": 0.6,
            }
        }
        old["last_market_regime"] = "FRESHNESS_HOLD"
        kpis = {"dimensions": {
            "market_freshness": 1.0,
            "market_coverage": 1.0,
            "source_health": 0.763158,
            "neural_consensus": 0.401591,
            "resource_headroom": 0.6,
        }}
        base = {"autonomous_decision": {"allow_execution": True}}
        drift = v382.operational_drift(old, kpis, base, {})
        self.assertEqual(0.75, drift["components"]["market_freshness"])
        self.assertEqual("HIGH", drift["level"])
        gate = v382.autonomous_gate(
            base, old, drift,
            {"action_id": "TRAIN_JOB_STRATEGY", "quarantine_recommended": False},
            {"score": 0.934832}, {"hold_recommended": False},
            now=datetime.now(timezone.utc),
        )
        self.assertFalse(gate["allow_execution"])
        self.assertIn("HIGH_DRIFT_RECOVERY_ONLY", gate["reasons"])

    def test_recovery_action_never_overrides_upstream_hold(self):
        gate = v382.autonomous_gate(
            {"autonomous_decision": {"allow_execution": False}},
            v382._default_state(), {"level": "HIGH", "score": 0.75},
            {"action_id": "REFRESH_MARKET_DATA", "quarantine_recommended": False},
            {"score": 0.93}, {"hold_recommended": False},
            now=datetime.now(timezone.utc),
        )
        self.assertFalse(gate["allow_execution"])
        self.assertIn("V381_UPSTREAM_GATE_HOLD", gate["reasons"])

    def test_change_point_observation_is_not_automatic_permission(self):
        base = {
            "v382_autonomous_gate": {
                "allow_execution": False,
                "selected_action": "TRAIN_JOB_STRATEGY",
            }
        }
        policy = {"selected_action": "TRAIN_QUERY_STRATEGY", "candidates": []}
        cp = {"detected": True}
        scheduler = {"resource_state": "NORMAL"}
        gate = v385.autonomous_gate(base, policy, cp, scheduler)
        self.assertFalse(gate["allow_execution"])
        self.assertIn("V382_UPSTREAM_GATE_HOLD", gate["reasons"])
        self.assertIn("CHANGE_POINT_RECOVERY_ONLY", gate["reasons"])


if __name__ == "__main__":
    unittest.main()
