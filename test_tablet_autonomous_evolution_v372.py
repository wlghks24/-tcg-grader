import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v372 as autonomy


NOW = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


def signals_for_two_models():
    return {
        "runtime_models": {
            "status": "degraded",
            "models": {
                "query_strategy": {"status": "broken", "reason": "model_json_invalid"},
                "job_strategy": {"status": "degraded", "reason": "active_model_stale"},
            },
            "broken_models": ["query_strategy"],
        },
        "repair_neural": {
            "active": True,
            "label_count": 1500,
            "minimum_labels": 1000,
            "requires_attention": False,
            "reason": "active",
        },
        "market": {"status": "fresh", "stale": [], "invalid": []},
    }


def write_market(root: Path, *, updated_at: datetime = NOW):
    entries = {
        "KR|A|CARD": {"link_status": "정상", "source_date": "2026-10-01"},
        "KR|B|BOX": {"link_status": "정상", "source_date": "2026-10-01"},
        "JP|C|CARD": {"link_status": "정상", "source_date": "2026-10-01"},
        "JP|D|BOX": {"link_status": "정상", "source_date": "2026-10-01"},
        "US|E|CARD": {"link_status": "정상", "source_date": "2026-10-01"},
        "US|F|BOX": {"link_status": "정상", "source_date": "2026-10-01"},
    }
    (root / "market_prices.json").write_text(
        json.dumps({"updated_at": updated_at.isoformat(), "entries": entries}), encoding="utf-8"
    )
    (root / "exchange_rates.json").write_text(
        json.dumps({"updated_at": updated_at.isoformat()}), encoding="utf-8"
    )


def write_proc(root: Path, *, load1: float, available_kib: int, total_kib: int):
    root.mkdir(parents=True, exist_ok=True)
    (root / "loadavg").write_text(f"{load1} 0.10 0.10 1/100 1\n", encoding="utf-8")
    (root / "meminfo").write_text(
        f"MemTotal:       {total_kib} kB\nMemAvailable:   {available_kib} kB\n", encoding="utf-8"
    )


class TabletAutonomousEvolutionV372Tests(unittest.TestCase):
    def test_safety_extends_v371_and_remains_bounded(self):
        self.assertTrue(autonomy.SAFETY["resource_aware_training"])
        self.assertTrue(autonomy.SAFETY["unknown_resource_pressure_is_hold"])
        self.assertTrue(autonomy.SAFETY["invalid_post_training_model_auto_rollback"])
        self.assertTrue(autonomy.SAFETY["capability_proposals_are_non_executable"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["autonomous_issue_or_pr_write"])
        self.assertEqual(1, autonomy.MAX_TRAINING_ACTIONS_PER_CYCLE)

    def test_repair_training_spec_includes_current_rule_fingerprints(self):
        fake = {"rule-a": "abcdef123456"}
        with mock.patch.object(autonomy, "_repair_rule_fingerprints", return_value=fake):
            module, kwargs = autonomy._trainer_spec("TRAIN_REPAIR_PRIORITY")
        self.assertEqual(fake, kwargs["current_rule_fingerprints"])
        self.assertEqual("verified_neural_self_refine", module.__name__)

    def test_resource_pressure_defers_heavy_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc"
            write_proc(proc, load1=64.0, available_kib=128 * 1024, total_kib=8 * 1024 * 1024)
            write_market(root)
            with mock.patch("tablet_autonomous_evolution_v372.os.cpu_count", return_value=4):
                plan = autonomy.plan_cycle(
                    signals_for_two_models(), root=root, now=NOW, proc_root=proc,
                    state_path=root / "state.json",
                )
        self.assertEqual("busy", plan["resources"]["status"])
        self.assertEqual(0, plan["training_budget"])
        self.assertEqual([], plan["selected_safe_learning_actions"])
        self.assertTrue(plan["deferred_safe_learning_actions"])

    def test_unknown_resource_metrics_are_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_market(root)
            plan = autonomy.plan_cycle(
                signals_for_two_models(), root=root, now=NOW,
                proc_root=root / "missing-proc", state_path=root / "state.json",
            )
        self.assertEqual("unknown", plan["resources"]["status"])
        self.assertEqual(0, plan["training_budget"])
        self.assertIn("resource_metrics_unavailable", plan["resources"]["reasons"])
        self.assertEqual([], plan["selected_safe_learning_actions"])

    def test_normal_resources_select_only_highest_priority_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc"
            write_proc(proc, load1=0.1, available_kib=4 * 1024 * 1024, total_kib=8 * 1024 * 1024)
            write_market(root)
            with mock.patch("tablet_autonomous_evolution_v372.os.cpu_count", return_value=8):
                plan = autonomy.plan_cycle(
                    signals_for_two_models(), root=root, now=NOW, proc_root=proc,
                    state_path=root / "state.json",
                )
        self.assertEqual(1, plan["training_budget"])
        self.assertEqual(["TRAIN_QUERY_STRATEGY"], plan["selected_safe_learning_actions"])
        self.assertIn("TRAIN_JOB_STRATEGY", {row["id"] for row in plan["deferred_safe_learning_actions"]})

    def test_success_cooldown_prevents_repeat_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = root / "proc"
            write_proc(proc, load1=0.1, available_kib=4 * 1024 * 1024, total_kib=8 * 1024 * 1024)
            write_market(root)
            state = {
                "schema_version": autonomy.SCHEMA_VERSION,
                "controller_version": autonomy.CONTROLLER_VERSION,
                "updated_at": NOW.isoformat(),
                "last_training": {
                    "TRAIN_QUERY_STRATEGY": {
                        "at": (NOW - timedelta(hours=1)).isoformat(), "status": "success"
                    }
                },
                "consecutive_failures": {},
            }
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with mock.patch("tablet_autonomous_evolution_v372.os.cpu_count", return_value=8):
                plan = autonomy.plan_cycle(
                    signals_for_two_models(), root=root, now=NOW, proc_root=proc,
                    state_path=state_path,
                )
        self.assertEqual(["TRAIN_JOB_STRATEGY"], plan["selected_safe_learning_actions"])
        row = next(x for x in plan["deferred_safe_learning_actions"] if x["id"] == "TRAIN_QUERY_STRATEGY")
        self.assertEqual("training_cooldown", row["reason"])
        self.assertGreater(row["cooldown_remaining_seconds"], 0)

    def test_corrupt_state_and_backup_fail_closed_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state.json"
            backup = root / "state.json.bak"
            state.write_text("{broken", encoding="utf-8")
            backup.write_text("[also broken", encoding="utf-8")
            loaded = autonomy.load_state(state_path=state, backup_path=backup)
            self.assertTrue(loaded["corruption_hold"])
            before = state.read_text(encoding="utf-8")
            result = autonomy.save_state(
                autonomy._default_state(), state_path=state, backup_path=backup, corruption_hold=True
            )
            self.assertEqual("STATE_CORRUPTION_HOLD", result["status"])
            self.assertEqual(before, state.read_text(encoding="utf-8"))

    def test_market_profile_emits_non_executable_coverage_proposal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "exchange_rates.json").write_text(json.dumps({"updated_at": NOW.isoformat()}), encoding="utf-8")
            (root / "market_prices.json").write_text(json.dumps({
                "updated_at": NOW.isoformat(),
                "entries": {
                    "KR|A|CARD": {"link_status": "정상", "source_date": "2026-10-01"},
                    "JP|B|CARD": {"link_status": "정상", "source_date": "2026-10-01"},
                },
            }), encoding="utf-8")
            profile = autonomy.market_profile(root=root, now=NOW)
        proposals = autonomy._proposal_rows(profile, {"status": "active"})
        coverage = next(row for row in proposals if row["id"] == "EXPAND_MARKET_COVERAGE")
        self.assertFalse(coverage["auto_implementation"])
        self.assertTrue(coverage["normal_pr_pipeline_required"])
        self.assertIn("US", coverage["evidence"]["low_coverage_regions"])
        self.assertFalse(profile["market_direction_inferred"])

    def test_guarded_training_rolls_back_invalid_post_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "model.json"
            previous = {"active": True, "valid": True, "metrics": {"accuracy": 0.7, "logloss": 0.5}}
            model.write_text(json.dumps(previous), encoding="utf-8")

            def validate(payload):
                return isinstance(payload, dict) and payload.get("valid") is True

            def train_if_ready():
                model.write_text(json.dumps({"active": True, "valid": False}), encoding="utf-8")
                return {"active": True, "reason": "activated"}

            fake = types.SimpleNamespace(MODEL_PATH=model, _validate_model_payload=validate, train_if_ready=train_if_ready)
            result = autonomy.guarded_train("TRAIN_QUERY_STRATEGY", module_override=fake)
            restored = json.loads(model.read_text(encoding="utf-8"))
        self.assertEqual("ROLLED_BACK_INVALID_POST_TRAINING_MODEL", result["status"])
        self.assertEqual(previous, restored)
        self.assertTrue(result["rollback"]["restored"])

    def test_execution_budget_rejects_more_than_one_training_action(self):
        with self.assertRaisesRegex(ValueError, "TRAINING_BUDGET_EXCEEDED"):
            autonomy.execute_safe_learning({
                "selected_safe_learning_actions": ["TRAIN_QUERY_STRATEGY", "TRAIN_JOB_STRATEGY"]
            })


if __name__ == "__main__":
    unittest.main(verbosity=2)
