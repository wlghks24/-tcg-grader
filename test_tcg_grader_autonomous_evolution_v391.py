from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import tcg_grader_autonomous_evolution_v391 as autonomy

NOW = datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc)


def core_fixture(*, allow: bool = True) -> dict:
    return {
        "controller_version": "v390",
        "v390_status": "V390_VERIFIED_ALLOW" if allow else "V390_UPSTREAM_HOLD",
        "v390_goal_plan": {
            "primary_goal": {"goal_id": "IMPROVE_NEURAL_CONSENSUS", "urgency": 0.7},
            "recommended_action": "TRAIN_REPAIR_PRIORITY",
        },
        "v390_autonomous_gate": {
            "status": "V390_VERIFIED_ALLOW" if allow else "V390_UPSTREAM_HOLD",
            "allow_execution": allow,
        },
        "safety": dict(autonomy.v390.SAFETY),
    }


def snapshot(*, rows: int = 5, profiles: int = 0, open_errors: int = 0, market_age: float = 1.0) -> dict:
    return {
        "observed_at": NOW.isoformat(),
        "verified_grade_learning": {
            "audit_ok": True,
            "verified_training_rows": rows,
            "vision_profile_count": profiles,
            "registry_gate_required": True,
            "error_code": None,
        },
        "vision_1_4_8": {
            "engine_present": True,
            "hierarchy_test_present": True,
            "one_four_eight_contract_present": True,
        },
        "selfrefine": {"open_error_count": open_errors, "ledger_present": True},
        "market": {
            "market_prices_present": True,
            "market_prices_age_hours": market_age,
            "stale_after_hours": 6.0,
            "market_direction_inferred": False,
        },
    }


class TcgGraderAutonomyV391Tests(unittest.TestCase):
    def test_runtime_isolation_redirects_and_restores_all_autonomy_paths(self):
        before = {
            (module.__name__, key): value
            for module in autonomy._autonomy_modules()
            for key, value in vars(module).items()
            if isinstance(value, Path) and "tablet_autonomy" in value.name
        }
        self.assertTrue(before)
        with autonomy.isolated_tcg_runtime_paths():
            inside = {
                (module.__name__, key): value
                for module in autonomy._autonomy_modules()
                for key, value in vars(module).items()
                if (module.__name__, key) in before
            }
            self.assertEqual(set(before), set(inside))
            self.assertTrue(all("tcg_grader_autonomy" in value.name for value in inside.values()))
        after = {
            (module.__name__, key): value
            for module in autonomy._autonomy_modules()
            for key, value in vars(module).items()
            if (module.__name__, key) in before
        }
        self.assertEqual(before, after)

    def test_specialization_selects_verified_calibration_when_rows_exist_without_profiles(self):
        plan = autonomy.grader_specialization_plan(snapshot(rows=8, profiles=0), core_fixture())
        self.assertEqual("REBUILD_VERIFIED_GRADE_CALIBRATION", plan["primary_action"])
        self.assertGreaterEqual(plan["primary_urgency"], 0.8)
        self.assertTrue(plan["core_gate_allow_execution"])

    def test_specialization_prioritizes_missing_1_4_8_contract(self):
        snap = snapshot(rows=120, profiles=3)
        snap["vision_1_4_8"]["one_four_eight_contract_present"] = False
        plan = autonomy.grader_specialization_plan(snap, core_fixture())
        self.assertEqual("VERIFY_1_4_8_VISION_HIERARCHY", plan["primary_action"])
        self.assertFalse(plan["candidates"][0]["auto_execute"])

    def test_failed_grade_audit_is_fail_closed_and_never_auto_rebuilds(self):
        snap = snapshot(rows=8, profiles=0)
        snap["verified_grade_learning"]["audit_ok"] = False
        plan = autonomy.grader_specialization_plan(snap, core_fixture())
        self.assertEqual("RECOVER_VERIFIED_GRADE_AUDIT", plan["primary_action"])
        with mock.patch.object(autonomy.grade_learning, "rebuild_safe_vision_calibration") as rebuild:
            result = autonomy._maybe_rebuild_grade_calibration(execute=True, plan=plan)
        self.assertFalse(result["executed"])
        rebuild.assert_not_called()

    def test_calibration_rebuild_is_blocked_by_upstream_gate(self):
        plan = autonomy.grader_specialization_plan(snapshot(rows=8, profiles=0), core_fixture(allow=False))
        with mock.patch.object(autonomy.grade_learning, "rebuild_safe_vision_calibration") as rebuild:
            result = autonomy._maybe_rebuild_grade_calibration(execute=True, plan=plan)
        self.assertFalse(result["executed"])
        self.assertEqual("GRADE_CALIBRATION_UPSTREAM_HOLD", result["status"])
        rebuild.assert_not_called()

    def test_run_cycle_forces_tcg_domain_and_rebuilds_only_verified_calibration(self):
        snap = snapshot(rows=8, profiles=0)
        rebuilt = {"registry_verified_training_rows": 8, "registry_gate_v135": True}
        after = {
            **snap,
            "verified_grade_learning": {
                **snap["verified_grade_learning"],
                "vision_profile_count": 2,
            },
        }
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.v390, "run_cycle", return_value=core_fixture()) as core, \
             mock.patch.object(autonomy, "grader_snapshot", side_effect=[snap, after]), \
             mock.patch.object(
                 autonomy.grade_learning,
                 "rebuild_safe_vision_calibration",
                 return_value=rebuilt,
             ) as rebuild:
            result = autonomy.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                now=NOW,
                persist_outputs=False,
            )
        self.assertEqual("tcg_grader", core.call_args.kwargs["domain"])
        self.assertTrue(result["tcg_grader_autonomy_v391"]["domain_runtime_state_isolated"])
        self.assertTrue(result["tcg_grader_autonomy_v391"]["grade_calibration_action"]["executed"])
        rebuild.assert_called_once_with()
        self.assertFalse(result["safety"]["source_code_auto_generation"])
        self.assertFalse(result["safety"]["git_write"])


if __name__ == "__main__":
    unittest.main()
