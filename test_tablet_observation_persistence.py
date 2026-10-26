"""Isolated state-persistence tests: no live tablet files are touched."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tablet_autonomous_evolution_v382 as v382
import tablet_autonomous_evolution_v385 as v385
from tablet_observation_state_v1 import observation_snapshot


class ObservationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.when = datetime.now(timezone.utc) - timedelta(seconds=2)

    def test_v382_atomic_save_and_reload_without_other_state_changes(self):
        path = self.root / "v382.json"
        state = v382._default_state()
        state["quarantines"] = {"protected": {
            "until": (self.when + timedelta(days=1)).isoformat(),
            "reason": "verified_policy_regression"}}
        observed = {
            "verified": True, "last_kpis": {
                "score": 0.93,
                "dimensions": {"market_freshness": 1.0, "market_coverage": 1.0,
                               "source_health": 0.76, "neural_consensus": 0.4,
                               "resource_headroom": 0.6}},
            "last_market_regime": "HEALTHY", "last_model_signature": "model",
            "last_exchange_digest": "exchange", "last_calibration_error": None}
        before = copy.deepcopy(state)
        snapshot = observation_snapshot("v382", state, observed, observed_at=self.when)
        self.assertTrue(v382.save_state(snapshot, path=path, corruption_hold=False)["written"])
        loaded = v382.load_state(path)
        self.assertFalse(loaded["corruption_hold"])
        self.assertEqual(snapshot, loaded["state"])
        self.assertEqual(before, state)
        self.assertEqual(before["quarantines"], loaded["state"]["quarantines"])

    def test_v385_atomic_save_keeps_neural_weights_and_registry(self):
        path = self.root / "v385.json"
        state = v385._default_state()
        state["network"]["updates"] = 5
        state["capability_registry"]["keep"] = {
            "steps": ["REFRESH_VERIFIED_MARKET"], "status": "shadow"}
        observed = {"verified": True, "last_kpi_score": 0.93,
                    "ewma_kpi": 0.9, "ewma_drift": 0.2}
        snapshot = observation_snapshot("v385", state, observed, observed_at=self.when)
        self.assertTrue(v385.save_state(snapshot, path=path, corruption_hold=False)["written"])
        loaded = v385.load_state(path)
        self.assertFalse(loaded["corruption_hold"])
        self.assertEqual(state["network"], loaded["state"]["network"])
        self.assertEqual(state["capability_registry"], loaded["state"]["capability_registry"])

    def test_corruption_hold_refuses_overwrite(self):
        for version, controller in (("v382", v382), ("v385", v385)):
            with self.subTest(version=version):
                path = self.root / (version + "_corrupt.json")
                path.write_text("{corrupted", encoding="utf-8")
                loaded = controller.load_state(path)
                self.assertTrue(loaded["corruption_hold"])
                old = path.read_bytes()
                result = controller.save_state(controller._default_state(),
                                               path=path, corruption_hold=True)
                self.assertFalse(result["written"])
                self.assertEqual(old, path.read_bytes())

    def test_invalid_state_rejected_without_file_creation(self):
        for version, controller in (("v382", v382), ("v385", v385)):
            with self.subTest(version=version):
                path = self.root / (version + "_invalid.json")
                invalid = controller._default_state()
                invalid["schema_version"] = -1
                result = controller.save_state(invalid, path=path, corruption_hold=False)
                self.assertFalse(result["written"])
                self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
