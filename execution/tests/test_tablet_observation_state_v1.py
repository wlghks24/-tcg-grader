"""Fail-closed tests for pure observation-only state updates."""
import copy
import unittest
from datetime import datetime, timedelta, timezone

from execution.tests.tablet_observation_state_v1 import observation_snapshot


class ObservationSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc) - timedelta(seconds=2)
        self.state = {"network": {"updates": 7}, "capability_registry": {"keep": 1},
                      "quarantines": {"action": "hold"}, "history": ["old"],
                      "last_kpis": {"score": 0.1}}
        self.v382 = {"verified": True, "last_kpis": {
            "score": 0.9, "dimensions": {
                "market_freshness": 1.0, "market_coverage": 1.0,
                "source_health": 0.76, "neural_consensus": 0.4,
                "resource_headroom": 0.6}},
            "last_market_regime": "HEALTHY",
            "last_model_signature": "sha",
            "last_exchange_digest": "digest",
            "last_calibration_error": None}
        self.v385 = {"verified": True, "last_kpi_score": 0.9,
                     "ewma_kpi": 0.85, "ewma_drift": 0.2}

    def test_v382_only_observation_fields_change(self):
        before = copy.deepcopy(self.state)
        result = observation_snapshot("v382", self.state, self.v382, observed_at=self.now)
        self.assertEqual(before, self.state)
        for key in ("network", "capability_registry", "quarantines", "history"):
            self.assertEqual(before[key], result[key])
        self.assertEqual(1.0, result["last_kpis"]["dimensions"]["market_freshness"])
        result["last_kpis"]["dimensions"]["market_freshness"] = 0.0
        self.assertEqual(1.0, self.v382["last_kpis"]["dimensions"]["market_freshness"])

    def test_v385_does_not_train_or_promote(self):
        result = observation_snapshot("v385", self.state, self.v385, observed_at=self.now)
        self.assertEqual(self.state["network"], result["network"])
        self.assertEqual(self.state["capability_registry"], result["capability_registry"])
        self.assertEqual(0.85, result["ewma_kpi"])

    def test_unverified_incomplete_or_nonfinite_rejected(self):
        for invalid in (
            dict(self.v382, verified=False),
            {k: v for k, v in self.v382.items() if k != "last_kpis"},
            dict(self.v382, last_kpis={"score": float("nan"), "dimensions": {}}),
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    observation_snapshot("v382", self.state, invalid, observed_at=self.now)

    def test_future_and_naive_timestamps_rejected(self):
        for when in (datetime.now(timezone.utc) + timedelta(days=1),
                     datetime.now()):
            with self.assertRaises(ValueError):
                observation_snapshot("v385", self.state, self.v385, observed_at=when)


if __name__ == "__main__":
    unittest.main()
