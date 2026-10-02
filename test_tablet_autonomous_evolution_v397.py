import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v397 as autonomy

NOW = datetime(2026, 10, 2, 13, 0, tzinfo=timezone.utc)


def fixture(*, allow=True, kpi=0.80, freshness=0.82, source_health=0.88, coverage=0.84):
    candidate = autonomy.v391.v390.v373._capability(
        "REQUEST_FRESHNESS_REFRESH",
        "V391_TEST",
        {"max_runs": 1},
        {"reason": "test"},
        now=NOW,
    )
    return {
        "controller_version": "v391",
        "v391_status": "V391_VERIFIED_ALLOW" if allow else "V391_UPSTREAM_HOLD",
        "v391_autonomous_gate": {
            "status": "V391_VERIFIED_ALLOW" if allow else "V391_UPSTREAM_HOLD",
            "allow_execution": allow,
        },
        "v391_self_diagnosis": {
            "operational_regime": "STEADY_VERIFIED_OPTIMIZATION" if allow else "RECOVERY_GOVERNANCE",
            "top_fault": None if allow else {"fault_id": "UPSTREAM_GATE_HOLD"},
            "stress_score": 0.1 if allow else 0.9,
            "market_direction_inferred": False,
        },
        "v391_remediation_candidate": {
            "status": "V390_CAPABILITY_ALREADY_SELECTED",
            "candidate": candidate,
            "owner": "v390",
            "written_by_v391": False,
        },
        "v390_goal_plan": {
            "primary_goal": {"goal_id": "RECOVER_MARKET_FRESHNESS", "urgency": 0.72},
            "recommended_action": "REFRESH_MARKET_DATA",
        },
        "v390_goal_capability": {
            "candidate": candidate,
            "write": {"status": "NOT_WRITTEN", "written": False},
            "next_cycle_only": True,
            "canonical_allowlist_only": True,
        },
        "v391_feature_lifecycle": [
            {
                "v388_proposal_id": "SOURCE_GAP:KR:Pokemon",
                "v388_priority_score": 0.82,
                "v388_recurrence": 4,
                "v391_stage": "canary_spec_candidate",
                "auto_execute": False,
                "auto_generate_source": False,
                "git_write": False,
            }
        ],
        "v382_kpis": {
            "score": kpi,
            "dimensions": {
                "market_freshness": freshness,
                "market_coverage": coverage,
                "source_health": source_health,
                "neural_consensus": 0.86,
                "resource_headroom": 0.80,
            },
        },
        "v388_resource_budget": {
            "selected_uncertainty": 0.12,
            "drift_score": 0.10,
            "resource_headroom": 0.80,
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


class TabletAutonomousEvolutionV397Tests(unittest.TestCase):
    def test_safety_preserves_v391_and_source_boundaries(self):
        self.assertTrue(autonomy.SAFETY["declarative_self_extension_enabled"])
        self.assertTrue(autonomy.SAFETY["declarative_self_extension_allowlisted_only"])
        self.assertTrue(autonomy.SAFETY["owned_capability_auto_rollback_enabled"])
        self.assertTrue(autonomy.SAFETY["source_feature_verified_canary_required"])
        self.assertTrue(autonomy.SAFETY["v391_gate_cannot_be_bypassed"])
        self.assertTrue(autonomy.SAFETY["v390_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_operating_mode_uses_v391_and_operational_market_flow_only(self):
        low = fixture(freshness=0.22)
        mode = autonomy.operating_mode(low)
        self.assertEqual("FRESHNESS_RECOVERY", mode["mode"])
        self.assertEqual("market_freshness", mode["reason"])
        self.assertFalse(mode["market_direction_inferred"])

        held = fixture(allow=False)
        self.assertEqual("HOLD", autonomy.operating_mode(held)["mode"])

    def test_source_feature_requires_verified_canary_to_reach_protected_pr(self):
        base = fixture()
        state = autonomy._default_state()
        rows = autonomy.source_feature_lifecycle(base, state)
        self.assertEqual("canary_spec", rows[0]["stage"])
        self.assertFalse(rows[0]["auto_execute"])
        self.assertFalse(rows[0]["auto_generate_source"])

        base["v391_feature_lifecycle"][0].update({
            "verified_canary_successes": 2,
            "verified_canary_failures": 0,
            "verified_kpi_delta": 0.04,
            "verified_output_passed": True,
        })
        rows = autonomy.source_feature_lifecycle(base, state)
        self.assertEqual("protected_pr_candidate", rows[0]["stage"])
        self.assertIn("protected_pr_ci", rows[0]["promotion_requires"])

        base["v391_feature_lifecycle"][0]["verified_canary_failures"] = 1
        rows = autonomy.source_feature_lifecycle(base, state)
        self.assertEqual("rollback_candidate", rows[0]["stage"])

    def test_material_kpi_regression_requests_owned_capability_rollback(self):
        state = autonomy._default_state()
        state["cycle"] = 1
        state["active_capability"] = {
            "id": "REQUEST_FRESHNESS_REFRESH:V397_GOAL",
            "primitive": "REQUEST_FRESHNESS_REFRESH",
            "baseline_kpi": 0.85,
            "activated_cycle": 1,
            "goal_id": "RECOVER_MARKET_FRESHNESS",
        }
        decision = autonomy.rollback_decision(state, fixture(kpi=0.70))
        self.assertTrue(decision["rollback"])
        self.assertEqual("MATERIAL_OPERATIONAL_KPI_REGRESSION", decision["reason"])

    def test_mutating_cycle_owns_only_allowlisted_next_cycle_capability(self):
        base = fixture(kpi=0.80)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v397-state.json"
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v391, "run_cycle", return_value=base) as run:
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    capability_path=cap_path,
                    persist_outputs=False,
                )
            self.assertEqual("v397", result["controller_version"])
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(1, saved["cycle"])
            self.assertIsNotNone(saved["active_capability"])
            self.assertTrue(cap_path.is_file())
            caps = json.loads(cap_path.read_text(encoding="utf-8"))["capabilities"]
            owned = [row for row in caps if "V397_GOAL" in row["id"]]
            self.assertEqual(1, len(owned))
            self.assertIn(owned[0]["primitive"], autonomy.v391.v390.v373.CAPABILITY_PRIMITIVES)
            self.assertFalse(result["v397_self_extension"]["source_code_generated"])
            self.assertFalse(result["safety"]["git_write"])
            # Preview and actual upstream runs never let V390/V391 persist a competing capability.
            self.assertTrue(all(call.kwargs["apply_capabilities"] is False for call in run.call_args_list))

    def test_second_cycle_regression_removes_exact_v397_owned_capability(self):
        good = fixture(kpi=0.84)
        bad = fixture(kpi=0.68)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v397-state.json"
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v391, "run_cycle", return_value=good):
                first = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    capability_path=cap_path,
                    persist_outputs=False,
                )
            self.assertIsNotNone(first["v397_self_extension"]["new_capability"])

            with mock.patch.object(autonomy.v391, "run_cycle", return_value=bad):
                second = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    capability_path=cap_path,
                    persist_outputs=False,
                )
            self.assertTrue(second["v397_rollback"]["decision"]["rollback"])
            self.assertTrue(second["v397_rollback"]["write"]["rolled_back"])
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIsNone(saved["active_capability"])
            caps = json.loads(cap_path.read_text(encoding="utf-8"))["capabilities"]
            self.assertFalse(any("V397_GOAL" in row["id"] for row in caps))

    def test_upstream_v391_hold_blocks_self_extension_and_execution(self):
        base = fixture(allow=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v391, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    root=root,
                    now=NOW,
                    capability_path=cap_path,
                    state_path=root / ".v397-state.json",
                    persist_outputs=False,
                )
            self.assertEqual("V397_UPSTREAM_HOLD", result["v397_status"])
            self.assertFalse(result["v397_autonomous_gate"]["allow_execution"])
            self.assertFalse(cap_path.exists())
            self.assertFalse(result["execution"]["executed"])

    def test_missing_or_expired_owned_capability_is_reconciled_from_local_state(self):
        base = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / ".v397-state.json"
            state = autonomy._default_state()
            state["cycle"] = 2
            state["active_capability"] = {
                "id": "REQUEST_FRESHNESS_REFRESH:V397_GOAL",
                "primitive": "REQUEST_FRESHNESS_REFRESH",
                "baseline_kpi": 0.8,
                "activated_cycle": 1,
                "goal_id": "RECOVER_MARKET_FRESHNESS",
            }
            autonomy.save_state(state, state_path, corruption_hold=False)
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v391, "run_cycle", return_value=base):
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    root=root,
                    now=NOW,
                    capability_path=cap_path,
                    state_path=state_path,
                    persist_outputs=False,
                )
            self.assertIsNotNone(result["v397_self_extension"]["new_capability"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
