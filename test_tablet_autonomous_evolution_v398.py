import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v398 as autonomy

NOW = datetime(2026, 10, 2, 13, 30, tzinfo=timezone.utc)


def fixture(*, allow=True, kpi=0.80, freshness=0.25, coverage=0.68, source_health=0.72, neural=0.70, uncertainty=0.32, drift=0.18):
    upstream = autonomy.v397.v391.v390.v373._capability(
        "REQUEST_FRESHNESS_REFRESH", "V397_TEST", {"max_runs": 1}, {"reason": "test"}, now=NOW
    )
    return {
        "controller_version": "v397",
        "v397_status": "V397_VERIFIED_ALLOW" if allow else "V397_UPSTREAM_HOLD",
        "v397_autonomous_gate": {"status": "V397_VERIFIED_ALLOW" if allow else "V397_UPSTREAM_HOLD", "allow_execution": allow},
        "v397_operating_mode": {
            "mode": "FRESHNESS_RECOVERY" if freshness < 0.55 else "STEADY_OPTIMIZATION",
            "reason": "market_freshness" if freshness < 0.55 else "balanced_operational_state",
            "learning_budget": 0.16,
            "dimensions": {
                "market_freshness": freshness,
                "market_coverage": coverage,
                "source_health": source_health,
                "neural_consensus": neural,
                "resource_headroom": 0.80,
            },
            "uncertainty": uncertainty,
            "drift": drift,
            "market_direction_inferred": False,
        },
        "v391_remediation_candidate": {"candidate": upstream, "owner": "v390", "written_by_v391": False},
        "v390_goal_plan": {
            "primary_goal": {"goal_id": "RECOVER_MARKET_FRESHNESS", "urgency": 0.82},
            "recommended_action": "REFRESH_MARKET_DATA",
        },
        "v390_goal_capability": {"candidate": upstream, "write": {"status": "NOT_WRITTEN", "written": False}},
        "v382_kpis": {
            "score": kpi,
            "dimensions": {
                "market_freshness": freshness,
                "market_coverage": coverage,
                "source_health": source_health,
                "neural_consensus": neural,
                "resource_headroom": 0.80,
            },
        },
        "v388_resource_budget": {
            "selected_uncertainty": uncertainty,
            "drift_score": drift,
            "resource_headroom": 0.80,
        },
        "market_adaptation_v381": {
            "low_coverage_regions": ["KR"],
            "degraded_source_ratio": max(0.0, 1.0 - source_health),
        },
        "execution": {"status": "PLAN_ONLY", "executed": False, "git_write": False, "source_code_modified": False},
        "safety": {},
    }


class TabletAutonomousEvolutionV398Tests(unittest.TestCase):
    def test_safety_boundaries(self):
        self.assertTrue(autonomy.SAFETY["multi_candidate_self_extension_enabled"])
        self.assertTrue(autonomy.SAFETY["candidate_tournament_verified_history_learning"])
        self.assertTrue(autonomy.SAFETY["candidate_failure_quarantine_enabled"])
        self.assertTrue(autonomy.SAFETY["single_canary_capability_only"])
        self.assertTrue(autonomy.SAFETY["v397_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_multiple_candidates_are_allowlisted(self):
        base = fixture(freshness=0.20, coverage=0.60, source_health=0.60, uncertainty=0.60)
        rows = autonomy.synthesize_candidates(base, autonomy._default_state(), now=NOW)
        primitives = {row["capability"]["primitive"] for row in rows}
        self.assertIn("REQUEST_FRESHNESS_REFRESH", primitives)
        self.assertIn("RETRY_DEGRADED_SOURCES", primitives)
        self.assertIn("PRIORITIZE_REGION", primitives)
        self.assertIn("INCREASE_OBSERVATION", primitives)
        for row in rows:
            cap = row["capability"]
            self.assertIn(cap["primitive"], autonomy.v397.v391.v390.v373.CAPABILITY_PRIMITIVES)
            self.assertEqual("v398", cap["evidence"]["owner_controller"])
            self.assertTrue(autonomy.v397.v391.v390.v373.validate_capability(cap, now=NOW))

    def test_tournament_quarantines_failed_recipe(self):
        base = fixture(freshness=0.10, coverage=0.70, source_health=0.75, uncertainty=0.30)
        state = autonomy._default_state()
        rows = autonomy.synthesize_candidates(base, state, now=NOW)
        one = autonomy.tournament(rows, base, state)
        self.assertEqual("REQUEST_FRESHNESS_REFRESH", one["selected_capability"]["primitive"])
        refresh = next(row for row in rows if row["capability"]["primitive"] == "REQUEST_FRESHNESS_REFRESH")
        state["candidate_memory"][refresh["recipe_key"]] = {
            **autonomy._memory_row(),
            "failures": 2,
            "reward_ewma": -0.8,
            "quarantine_until_cycle": 10,
        }
        two = autonomy.tournament(rows, base, state)
        self.assertNotEqual(refresh["recipe_key"], two["selected_recipe_key"])
        ranked = next(row for row in two["candidates"] if row["recipe_key"] == refresh["recipe_key"])
        self.assertTrue(ranked["quarantined"])
        self.assertEqual(0.0, ranked["tournament_score"])

    def test_active_canary_positive_and_regression(self):
        state = autonomy._default_state()
        state["cycle"] = 2
        state["active"] = {
            "id": "REQUEST_FRESHNESS_REFRESH:V398_FRESHNESS",
            "recipe_key": 'REQUEST_FRESHNESS_REFRESH|{"max_runs":1}',
            "primitive": "REQUEST_FRESHNESS_REFRESH",
            "baseline_kpi": 0.80,
            "activated_cycle": 1,
            "goal_id": "RECOVER_MARKET_FRESHNESS",
            "mode": "FRESHNESS_RECOVERY",
        }
        ids = {state["active"]["id"]}
        positive = autonomy.evaluate_active(state, fixture(kpi=0.84), ids)
        self.assertEqual("VERIFIED_POSITIVE_CANARY", positive["status"])
        self.assertFalse(positive["rollback"])
        bad = autonomy.evaluate_active(state, fixture(kpi=0.70), ids)
        self.assertEqual("MATERIAL_KPI_REGRESSION", bad["status"])
        self.assertTrue(bad["rollback"])

    def test_mutating_cycle_writes_one_v398_canary_and_blocks_competing_v397_write(self):
        base = fixture(kpi=0.80)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v398-state.json"
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v397, "run_cycle", return_value=base) as run:
                result = autonomy.run_cycle(
                    domain="tablet_gpt", execute=True, apply_capabilities=True,
                    train_meta=True, apply_skills=True, root=root, now=NOW,
                    state_path=state_path, capability_path=cap_path, persist_outputs=False,
                )
            self.assertEqual("v398", result["controller_version"])
            self.assertTrue(state_path.is_file())
            self.assertTrue(cap_path.is_file())
            caps = json.loads(cap_path.read_text(encoding="utf-8"))["capabilities"]
            owned = [row for row in caps if row.get("evidence", {}).get("owner_controller") == "v398"]
            self.assertEqual(1, len(owned))
            self.assertTrue(all(call.kwargs["apply_capabilities"] is False for call in run.call_args_list))

    def test_second_cycle_regression_rolls_back_and_quarantines(self):
        good, bad = fixture(kpi=0.82), fixture(kpi=0.70)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v398-state.json"
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v397, "run_cycle", return_value=good):
                first = autonomy.run_cycle(
                    domain="tablet_gpt", execute=True, apply_capabilities=True,
                    root=root, now=NOW, state_path=state_path,
                    capability_path=cap_path, persist_outputs=False,
                )
            recipe = first["v398_self_extension"]["selected_recipe_key"]
            self.assertTrue(recipe)
            with mock.patch.object(autonomy.v397, "run_cycle", return_value=bad):
                second = autonomy.run_cycle(
                    domain="tablet_gpt", execute=True, apply_capabilities=True,
                    root=root, now=NOW, state_path=state_path,
                    capability_path=cap_path, persist_outputs=False,
                )
            self.assertTrue(second["v398_active_evaluation"]["rollback"])
            self.assertTrue(second["v398_rollback"]["write"]["rolled_back"])
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIsNone(saved["active"])
            self.assertGreater(saved["candidate_memory"][recipe]["failures"], 0)
            self.assertGreater(saved["candidate_memory"][recipe]["quarantine_until_cycle"], saved["cycle"])

    def test_existing_v397_experiment_defers_v398(self):
        base = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cap_path = root / "caps.json"
            cap = autonomy.v397.v391.v390.v373._capability(
                "REQUEST_FRESHNESS_REFRESH", "V397_GOAL", {"max_runs": 1},
                {"owner_controller": "v397", "reason": "existing"}, now=NOW,
            )
            autonomy.v397.v391.v390.v373.save_capabilities([cap], path=cap_path, now=NOW)
            with mock.patch.object(autonomy.v397, "run_cycle", return_value=base) as run:
                result = autonomy.run_cycle(
                    domain="tablet_gpt", execute=True, apply_capabilities=True,
                    root=root, now=NOW, capability_path=cap_path,
                    state_path=root / ".v398-state.json", persist_outputs=False,
                )
            self.assertTrue(result["v398_self_extension"]["v397_experiment_present"])
            self.assertIsNone(result["v398_self_extension"]["new_capability"])
            self.assertTrue(run.call_args_list[-1].kwargs["apply_capabilities"])

    def test_upstream_hold_blocks_extension_and_execution(self):
        base = fixture(allow=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v397, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    domain="tablet_gpt", execute=True, apply_capabilities=True,
                    root=root, now=NOW, capability_path=cap_path,
                    state_path=root / ".v398-state.json", persist_outputs=False,
                )
            self.assertEqual("V398_UPSTREAM_HOLD", result["v398_status"])
            self.assertFalse(result["v398_autonomous_gate"]["allow_execution"])
            self.assertFalse(cap_path.exists())
            self.assertFalse(result["execution"]["executed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
