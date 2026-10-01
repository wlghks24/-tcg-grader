import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v371 as autonomy


class TabletAutonomousEvolutionV371Tests(unittest.TestCase):
    def test_safety_boundary_forbids_unbounded_self_modification(self):
        self.assertTrue(autonomy.SAFETY["bounded_autonomy"])
        self.assertTrue(autonomy.SAFETY["verified_learning_only"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["direct_main_write"])
        self.assertFalse(autonomy.SAFETY["verification_bypass"])
        self.assertTrue(autonomy.SAFETY["feature_proposals_require_normal_pr_pipeline"])

    def test_degraded_model_is_selected_for_safe_retraining(self):
        signals = {
            "runtime_models": {
                "status": "degraded",
                "models": {
                    "query_strategy": {"status": "degraded", "reason": "active_model_stale"},
                    "job_strategy": {"status": "active"},
                },
            },
            "repair_neural": {"active": True, "label_count": 1500, "requires_attention": False},
            "market": {"status": "fresh", "stale": [], "invalid": []},
        }
        result = autonomy.plan_cycle(signals)
        self.assertEqual(["TRAIN_QUERY_STRATEGY"], result["safe_learning_actions"])
        self.assertEqual([], result["proposal_actions"])
        self.assertEqual("ACTION_REQUIRED", result["status"])

    def test_market_freshness_is_fail_closed(self):
        now = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "exchange_rates.json").write_text(json.dumps({
                "updated_at": (now - timedelta(hours=1)).isoformat(),
                "source": "test",
            }), encoding="utf-8")
            (root / "market_prices.json").write_text(json.dumps({
                "updated_at": (now - timedelta(hours=80)).isoformat(),
            }), encoding="utf-8")
            result = autonomy.market_freshness(root=root, now=now)
        self.assertEqual("hold", result["status"])
        self.assertEqual(["market_prices.json"], result["stale"])
        self.assertEqual([], result["invalid"])

    def test_future_or_missing_timestamp_is_hold(self):
        now = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "exchange_rates.json").write_text(json.dumps({
                "updated_at": (now + timedelta(hours=1)).isoformat(),
            }), encoding="utf-8")
            (root / "market_prices.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
            result = autonomy.market_freshness(root=root, now=now)
        self.assertEqual("hold", result["status"])
        self.assertEqual(
            {"exchange_rates.json", "market_prices.json"},
            set(result["invalid"]),
        )

    def test_execute_safe_learning_never_executes_proposals(self):
        plan = {
            "safe_learning_actions": [
                "TRAIN_QUERY_STRATEGY",
                "TRAIN_JOB_STRATEGY",
                "TRAIN_REPAIR_PRIORITY",
            ],
            "proposal_actions": ["REFRESH_MARKET_DATA", "PROPOSE_VERIFIED_FEATURE"],
        }
        with mock.patch("verified_collection_neural.train_if_ready", return_value={"status": "ok"}) as q, \
             mock.patch("verified_collection_job_neural.train_if_ready", return_value={"status": "ok"}) as j, \
             mock.patch("verified_neural_self_refine.train_if_ready", return_value={"status": "ok"}) as r:
            result = autonomy.execute_safe_learning(plan)
        self.assertEqual("SAFE_LEARNING_EXECUTED", result["status"])
        self.assertEqual(3, len(result["results"]))
        self.assertFalse(result["proposals_executed"])
        self.assertFalse(result["git_write"])
        self.assertFalse(result["source_code_modified"])
        q.assert_called_once_with()
        j.assert_called_once_with()
        r.assert_called_once_with()

    def test_unallowlisted_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNALLOWLISTED_AUTONOMOUS_ACTION"):
            autonomy.execute_safe_learning({"safe_learning_actions": ["WRITE_SOURCE_CODE"]})

    def test_broken_runtime_proposes_normal_pipeline_repair(self):
        signals = {
            "runtime_models": {"status": "broken", "reason": "model_json_invalid", "models": {}},
            "repair_neural": {"active": True, "label_count": 1200, "requires_attention": False},
            "market": {"status": "fresh", "stale": [], "invalid": []},
        }
        plan = autonomy.plan_cycle(signals)
        repair = next(row for row in plan["actions"] if row["id"] == "REPAIR_AI_RUNTIME")
        self.assertTrue(repair["normal_pr_pipeline_required"])
        self.assertFalse(repair["may_modify_source"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
