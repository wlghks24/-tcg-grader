import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v396 as autonomy


NOW = datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc)


def candidate():
    return autonomy.v390.v373._capability(
        "REQUEST_FRESHNESS_REFRESH",
        "V396_TEST",
        {"max_runs": 1},
        {"reason": "v390_goal_directed_next_cycle_alignment", "goal_id": "RECOVER_MARKET_FRESHNESS"},
        now=NOW,
    )


def fixture(*, allow=True, freshness=0.20, health=0.82):
    cap = candidate()
    return {
        "controller_version": "v390",
        "v390_status": "V390_VERIFIED_ALLOW" if allow else "V390_UPSTREAM_HOLD",
        "v390_autonomous_gate": {
            "allow_execution": allow,
            "status": "V390_VERIFIED_ALLOW" if allow else "V390_UPSTREAM_HOLD",
        },
        "v390_goals": [
            {
                "goal_id": "RECOVER_MARKET_FRESHNESS",
                "urgency": 1.0 - freshness,
                "evidence_dimension": "market_freshness",
                "market_direction_inferred": False,
            }
        ],
        "v390_goal_plan": {
            "recommended_action": "REFRESH_MARKET_DATA",
            "upstream_selected_action": "REFRESH_MARKET_DATA",
        },
        "v390_meta_critic": {"sample_count": 12},
        "v390_goal_capability": {
            "candidate": cap,
            "next_cycle_only": True,
            "canonical_allowlist_only": True,
        },
        "v390_source_feature_plan": [
            {
                "v388_proposal_id": "SOURCE_GAP:KR:Pokemon",
                "v388_priority_score": 0.88,
                "v390_stage": "protected_pr_candidate",
                "auto_execute": False,
                "auto_generate_source": False,
                "git_write": False,
            }
        ],
        "v382_kpis": {
            "score": health,
            "dimensions": {
                "market_freshness": freshness,
                "market_coverage": health,
                "source_health": health,
                "neural_consensus": health,
                "resource_headroom": health,
            },
        },
        "v388_resource_budget": {
            "resource_headroom": health,
            "drift_score": 0.10,
            "selected_uncertainty": 0.12,
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


class TabletAutonomousEvolutionV396Tests(unittest.TestCase):
    def test_safety_contract_keeps_source_and_market_boundaries(self):
        self.assertTrue(autonomy.SAFETY["supervised_self_evolution"])
        self.assertTrue(autonomy.SAFETY["verified_kpi_regression_rollback"])
        self.assertTrue(autonomy.SAFETY["declarative_self_extension_allowlisted_only"])
        self.assertTrue(autonomy.SAFETY["source_feature_pr_spec_non_executable"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_market_mode_is_operational_and_freshness_driven(self):
        mode = autonomy.operating_mode(fixture(freshness=0.05))
        self.assertEqual("FRESHNESS_RECOVERY", mode["mode"])
        self.assertEqual("RECOVER_MARKET_FRESHNESS", mode["primary_goal"])
        self.assertFalse(mode["market_direction_inferred"])

    def test_feature_lifecycle_shadow_canary_active_and_rollback(self):
        state = autonomy._default_state()
        cap = candidate()
        first = autonomy.advance_feature_lifecycle(state, cap, 0.70)
        self.assertEqual("shadow", first["candidate_stage"])

        state2 = {
            **state,
            "cycle": first["cycle"],
            "features": first["features"],
        }
        second = autonomy.advance_feature_lifecycle(state2, cap, 0.71)
        self.assertEqual("canary", second["candidate_stage"])

        state3 = {**state, "cycle": second["cycle"], "features": second["features"]}
        third = autonomy.advance_feature_lifecycle(state3, cap, 0.72)
        state4 = {**state, "cycle": third["cycle"], "features": third["features"]}
        fourth = autonomy.advance_feature_lifecycle(state4, cap, 0.73)
        self.assertEqual("active", fourth["candidate_stage"])

        state5 = {**state, "cycle": fourth["cycle"], "features": fourth["features"]}
        rollback = autonomy.advance_feature_lifecycle(state5, cap, 0.60)
        self.assertEqual("rollback", rollback["candidate_stage"])

    def test_source_feature_candidates_never_execute_or_write_git(self):
        rows = autonomy.source_feature_candidates(
            fixture(),
            {"mode": "FEATURE_DISCOVERY"},
        )
        self.assertEqual(1, len(rows))
        self.assertFalse(rows[0]["auto_execute"])
        self.assertFalse(rows[0]["auto_generate_source"])
        self.assertFalse(rows[0]["git_write"])
        self.assertTrue(rows[0]["protected_pr_ci_required"])
        self.assertIn("actual_output_validation", rows[0]["required_validation"])

    def test_upstream_hold_blocks_mutating_cycle(self):
        base = fixture(allow=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".v396.json"
            with mock.patch.object(autonomy.v390, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state,
                    persist_outputs=False,
                )
        self.assertEqual("V396_UPSTREAM_HOLD", result["v396_status"])
        self.assertFalse(result["v396_autonomous_gate"]["allow_execution"])
        self.assertFalse(result["execution"]["executed"])
        self.assertFalse(result["safety"]["git_write"])

    def test_first_mutating_cycle_stays_shadow_and_does_not_apply_capability(self):
        base = fixture(allow=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / ".v396.json"
            cap_path = root / "capabilities.json"
            calls = []

            def fake_run_cycle(**kwargs):
                calls.append(kwargs)
                return base

            with mock.patch.object(autonomy.v390, "run_cycle", side_effect=fake_run_cycle):
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state,
                    capability_path=cap_path,
                    persist_outputs=False,
                )
            self.assertTrue(state.is_file())
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual("v396", saved["controller_version"])
            self.assertEqual("shadow", result["v396_feature_lifecycle"]["candidate_stage"])
            self.assertFalse(result["v396_feature_lifecycle"]["apply_capability_this_cycle"])
            self.assertGreaterEqual(len(calls), 2)
            self.assertFalse(calls[-1]["apply_capabilities"])
            self.assertFalse(result["safety"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
