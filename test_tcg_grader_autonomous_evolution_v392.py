from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import tcg_grader_autonomous_evolution_v392 as autonomy

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def core_fixture(
    *,
    audit_ok: bool = True,
    vision_ok: bool = True,
    rows: int = 8,
    profiles: int = 0,
    open_errors: int = 1,
    market_age: float = 9.0,
    low_regions: list[str] | None = None,
    degraded: float = 0.6,
    gate_allow: bool = True,
) -> dict:
    snap = {
        "observed_at": NOW.isoformat(),
        "verified_grade_learning": {
            "audit_ok": audit_ok,
            "verified_training_rows": rows,
            "vision_profile_count": profiles,
            "registry_gate_required": True,
            "error_code": None,
        },
        "vision_1_4_8": {
            "engine_present": vision_ok,
            "hierarchy_test_present": vision_ok,
            "one_four_eight_contract_present": vision_ok,
        },
        "selfrefine": {"open_error_count": open_errors, "ledger_present": True},
        "market": {
            "market_prices_present": True,
            "market_prices_age_hours": market_age,
            "stale_after_hours": 6.0,
            "market_direction_inferred": False,
        },
    }
    return {
        "controller_version": "tcg-grader-v391",
        "v390_status": "V390_VERIFIED_ALLOW" if gate_allow else "V390_UPSTREAM_HOLD",
        "v390_autonomous_gate": {
            "status": "V390_VERIFIED_ALLOW" if gate_allow else "V390_UPSTREAM_HOLD",
            "allow_execution": gate_allow,
        },
        "v382_kpis": {
            "score": 0.74,
            "dimensions": {
                "market_freshness": 0.45,
                "market_coverage": 0.40,
                "source_health": 0.55,
                "neural_consensus": 0.58,
                "resource_headroom": 0.80,
            },
        },
        "v388_resource_budget": {
            "selected_uncertainty": 0.45,
            "drift_score": 0.35,
        },
        "market_adaptation_v381": {
            "regime": "UNDERCOVERED",
            "low_coverage_regions": low_regions or ["KR"],
            "degraded_source_ratio": degraded,
        },
        "tcg_grader_autonomy_v391": {
            "snapshot_before": snap,
            "snapshot_after": snap,
            "grade_calibration_action": {
                "status": "GRADE_CALIBRATION_PLAN_ONLY",
                "executed": False,
            },
        },
        "safety": dict(autonomy.v391.SAFETY),
    }


class TcgGraderAutonomyV392Tests(unittest.TestCase):
    def test_model_contract_and_forward_shape(self):
        state = autonomy._default_state()
        self.assertTrue(autonomy._valid_state(state))
        _, outputs = autonomy._forward(state["model"], [0.5] * autonomy.INPUT_DIM)
        self.assertEqual(len(autonomy.ACTIONS), len(outputs))
        self.assertTrue(all(0.0 <= score <= 1.0 for score in outputs))

    def test_failed_grade_audit_forces_revalidate_only(self):
        obs = autonomy.observation(core_fixture(audit_ok=False))
        plan = autonomy.select_actions(autonomy._initial_model(), obs)
        self.assertTrue(plan["blockers_present"])
        self.assertEqual(["REVALIDATE_ONLY"], plan["selected_actions"])

    def test_failed_vision_hierarchy_forces_revalidate_only(self):
        obs = autonomy.observation(core_fixture(vision_ok=False))
        plan = autonomy.select_actions(autonomy._initial_model(), obs)
        self.assertEqual(["REVALIDATE_ONLY"], plan["selected_actions"])

    def test_healthy_stale_undercovered_market_composes_allowlisted_capabilities(self):
        obs = autonomy.observation(
            core_fixture(rows=30, profiles=2, market_age=12.0, degraded=0.8, low_regions=["JP"])
        )
        plan = {
            "selected_actions": [
                "REFRESH_MARKET_EVIDENCE",
                "RETRY_DEGRADED_SOURCES",
                "PRIORITIZE_LOW_COVERAGE_REGION",
            ]
        }
        rows = autonomy._capability_rows(plan, obs, now=NOW)
        primitives = {row["primitive"] for row in rows}
        self.assertEqual(
            {"REQUEST_FRESHNESS_REFRESH", "RETRY_DEGRADED_SOURCES", "PRIORITIZE_REGION"},
            primitives,
        )
        self.assertTrue(all(row["source_code_change"] is False for row in rows))
        self.assertTrue(all(row["arbitrary_command"] is False for row in rows))

    def test_previous_cycle_reward_trains_neural_policy_only_on_next_cycle(self):
        model = autonomy._initial_model()
        previous = {
            "observed_at": NOW.isoformat(),
            "features": [0.5] * autonomy.INPUT_DIM,
            "selected_actions": ["REFRESH_MARKET_EVIDENCE"],
            "baseline_quality": 0.40,
        }
        trained, report = autonomy.train_from_previous(model, previous, 0.55)
        self.assertTrue(report["trained"])
        self.assertGreater(report["reward"], 0.0)
        self.assertEqual(1, trained["sample_count"])
        self.assertNotEqual(model["w2"], trained["w2"])

    def test_negative_verified_outcome_updates_action_stats(self):
        state = autonomy._default_state()
        model, training = autonomy.train_from_previous(
            state["model"],
            {
                "observed_at": NOW.isoformat(),
                "features": [0.5] * autonomy.INPUT_DIM,
                "selected_actions": ["RETRY_DEGRADED_SOURCES"],
                "baseline_quality": 0.70,
            },
            0.55,
        )
        plan = {"selected_actions": ["RETRY_DEGRADED_SOURCES"]}
        obs = autonomy.observation(core_fixture(rows=30, profiles=2))
        nxt = autonomy._next_state(
            state, model, training, plan, obs, autonomy.quality_score(obs), now=NOW
        )
        stat = nxt["action_stats"]["RETRY_DEGRADED_SOURCES"]
        self.assertEqual(1, stat["observations"])
        self.assertLess(stat["last_reward"], 0.0)

    def test_specialist_calibration_executes_only_with_verified_rows_and_gate(self):
        core = core_fixture(rows=8, profiles=0, gate_allow=True)
        obs = autonomy.observation(core)
        plan = {"selected_actions": ["REBUILD_VERIFIED_GRADE_CALIBRATION"]}
        with mock.patch.object(
            autonomy.v391.grade_learning,
            "rebuild_safe_vision_calibration",
            return_value={"registry_verified_training_rows": 8, "registry_gate_v135": True},
        ) as rebuild:
            result = autonomy.execute_specialist_action(
                plan, obs, core, execute=True
            )
        self.assertTrue(result["executed"])
        self.assertTrue(result["registry_gate_v135"])
        rebuild.assert_called_once_with()

    def test_run_cycle_keeps_blocked_cycle_non_mutating(self):
        blocked = core_fixture(audit_ok=False)
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.v391, "run_cycle", return_value=blocked) as run, \
             mock.patch.object(autonomy, "persist_composed_capabilities") as persist:
            result = autonomy.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                now=NOW,
                persist_outputs=False,
            )
        self.assertEqual(1, run.call_count)
        plan = result["tcg_grader_autonomy_v392"]["neural_plan"]
        self.assertEqual(["REVALIDATE_ONLY"], plan["selected_actions"])
        persist.assert_not_called()
        self.assertFalse(result["safety"]["source_code_auto_generation"])
        self.assertFalse(result["safety"]["git_write"])

    def test_run_cycle_executes_verified_core_and_persists_composed_capabilities(self):
        preview = core_fixture(rows=30, profiles=2, open_errors=5, market_age=12.0, degraded=0.8)
        executed = core_fixture(rows=30, profiles=2, open_errors=4, market_age=1.0, degraded=0.2)
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.v391, "run_cycle", side_effect=[preview, executed]) as run, \
             mock.patch.object(
                 autonomy,
                 "persist_composed_capabilities",
                 return_value={"status": "CAPABILITIES_SAVED", "written": True, "count": 2},
             ) as persist, \
             mock.patch.object(
                 autonomy,
                 "execute_specialist_action",
                 return_value={"status": "SPECIALIST_DIRECT_ACTION_NOT_SELECTED", "executed": False},
             ):
            result = autonomy.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                now=NOW,
                persist_outputs=False,
            )
        self.assertEqual(2, run.call_count)
        self.assertTrue(result["v392_state_write"]["written"])
        self.assertTrue(persist.called)
        self.assertTrue(result["safety"]["autonomous_runtime_feature_composition"])


if __name__ == "__main__":
    unittest.main()
