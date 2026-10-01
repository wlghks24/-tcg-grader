import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import tablet_autonomy_engine as autonomy
import verified_autonomy_neural as neural


class TabletAutonomyV371Tests(unittest.TestCase):
    def setUp(self):
        self.signals = {name: 0.2 for name in neural.NUMERIC_FEATURES}

    def _valid_model(self, trained_at):
        hidden = neural.HIDDEN_SIZES[0]
        return {
            "schema": neural.SCHEMA,
            "active": True,
            "feature_fingerprint": neural.FEATURE_FINGERPRINT,
            "feature_count": neural.FEATURE_COUNT,
            "protocol_version": neural.PROTOCOL_VERSION,
            "trained_at": trained_at.isoformat(),
            "label_count": neural.MIN_INDEPENDENT_LABELS,
            "hidden": hidden,
            "w1": [[0.0] * neural.FEATURE_COUNT for _ in range(hidden)],
            "b1": [0.0] * hidden,
            "w2": [0.0] * hidden,
            "b2": 0.0,
            "metrics": {"accuracy": 0.7, "logloss": 0.6},
            "safety": neural.SAFETY,
        }

    def test_neural_rejects_unknown_and_unverified_outcomes(self):
        with tempfile.TemporaryDirectory() as td:
            labels = Path(td) / "labels.json"
            unknown = neural.record_verified_outcome(
                "invent_action", self.signals, outcome=True, evidence="x",
                verification_level="postflight_verified", labels_path=labels,
            )
            self.assertFalse(unknown["accepted"])
            rejected = neural.record_verified_outcome(
                "refresh_market_data", self.signals, outcome=True, evidence="not enough",
                verification_level="unverified", labels_path=labels,
            )
            self.assertFalse(rejected["accepted"])
            self.assertFalse(labels.exists())

    def test_feature_vector_is_bounded_and_finite(self):
        signals = dict(self.signals)
        signals["market_shift"] = float("nan")
        signals["coverage_gap"] = 99
        vector = neural.feature_vector("rebalance_market_priority", signals)
        self.assertEqual(neural.FEATURE_COUNT, len(vector))
        self.assertTrue(all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in vector))

    def test_stale_and_future_models_fail_closed(self):
        now = datetime(2026, 10, 1, 5, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.json"
            stale = self._valid_model(now - timedelta(seconds=neural.MAX_RUNTIME_MODEL_AGE_SECONDS + 1))
            path.write_text(json.dumps(stale), encoding="utf-8")
            score = neural.score_action("refresh_market_data", self.signals, model_path=path, now=now)
            self.assertFalse(score["active"])
            self.assertEqual("model_stale", score["reason"])

            future = self._valid_model(now + timedelta(seconds=neural.RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS + 1))
            path.write_text(json.dumps(future), encoding="utf-8")
            score = neural.score_action("refresh_market_data", self.signals, model_path=path, now=now)
            self.assertFalse(score["active"])
            self.assertEqual("trained_at_in_future", score["reason"])

    def test_decision_is_allowlisted_bounded_and_market_aware(self):
        signals = {name: 0.0 for name in neural.NUMERIC_FEATURES}
        signals.update({"data_staleness": 1.0, "market_shift": 1.0, "market_uncertainty": 0.8})
        with patch.object(neural, "score_action", return_value={
            "active": False, "score": 0.5, "reason": "model_inactive",
            "neural_output_is_priority_only": True,
        }):
            plan = autonomy.decide(signals)
        selected = plan["selected_actions"]
        self.assertLessEqual(len(selected), autonomy.MAX_SELECTED_ACTIONS)
        self.assertTrue(all(row["action"] in neural.ACTIONS for row in selected))
        names = {row["action"] for row in selected}
        self.assertIn("refresh_market_data", names)
        self.assertIn("rebalance_market_priority", names)

    def test_capability_proposals_are_non_executable_and_pr_gated(self):
        signals = {name: 0.0 for name in neural.NUMERIC_FEATURES}
        signals.update({"coverage_gap": 0.9, "tablet_sync_risk": 0.9, "repair_pressure": 0.9})
        proposals = autonomy._capability_proposals(signals)
        self.assertTrue(proposals)
        for proposal in proposals:
            self.assertFalse(proposal["executable"])
            self.assertEqual("pr_required", proposal["implementation_mode"])
            self.assertIn("protected-main PR", proposal["required_gates"])

    def test_priority_multiplier_is_bounded_and_never_suppresses_jobs(self):
        state = {"priority": {"market_priority_boost": 1.0, "exploration_priority_boost": 1.0}}
        market = autonomy.job_priority_multiplier("market_prices.json", state)
        explore = autonomy.job_priority_multiplier("__integration__", state)
        normal = autonomy.job_priority_multiplier("releases.json", state)
        self.assertGreaterEqual(market, 1.0)
        self.assertLessEqual(market, 1.0 + autonomy.MAX_MARKET_PRIORITY_BOOST)
        self.assertLessEqual(explore, 1.0 + autonomy.MAX_EXPLORATION_PRIORITY_BOOST)
        self.assertEqual(1.0, normal)

    def test_corrupt_market_inputs_degrade_to_uncertainty_without_crash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name in ("market_watch.json", "market_prices.json", "exchange_rates.json"):
                (root / name).write_text("{broken", encoding="utf-8")
            with patch.object(autonomy.verified_collection_neural, "status", return_value={
                "minimum_labels": 1000, "labels_remaining": 1000
            }), patch.object(autonomy.verified_collection_job_neural, "status", return_value={
                "minimum_labels": 1000, "labels_remaining": 1000
            }):
                signals = autonomy.collect_signals(root, now=datetime(2026, 10, 1, tzinfo=timezone.utc))
            self.assertEqual(1.0, signals["data_staleness"])
            self.assertGreater(signals["market_uncertainty"], 0.0)
            self.assertTrue(all(0.0 <= value <= 1.0 for value in signals.values()))

    def test_refresh_state_writes_only_runtime_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            signals = {name: 0.1 for name in neural.NUMERIC_FEATURES}
            plan = {"selected_actions": [], "all_actions": [], "bounded": True, "safety": autonomy.SAFETY}
            with patch.object(autonomy, "collect_signals", return_value=signals), \
                 patch.object(autonomy, "decide", return_value=plan):
                report = autonomy.refresh_state(root, execute_learning=False)
            self.assertTrue(report["ok"])
            self.assertTrue((root / autonomy.STATE_PATH.name).is_file())
            proposal_payload = json.loads((root / autonomy.PROPOSALS_PATH.name).read_text(encoding="utf-8"))
            self.assertTrue(proposal_payload["non_executable"])
            self.assertEqual("pr_required", proposal_payload["implementation_mode"])

    def test_safety_contract_forbids_self_modifying_execution(self):
        self.assertFalse(neural.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(neural.SAFETY["git_write"])
        self.assertFalse(neural.SAFETY["verification_bypass"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertTrue(autonomy.SAFETY["mandatory_collectors_preserved"])
        self.assertTrue(autonomy.SAFETY["new_executable_capability_requires_pr"])


if __name__ == "__main__":
    unittest.main()
