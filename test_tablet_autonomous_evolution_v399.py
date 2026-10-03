import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v399 as autonomy

NOW = datetime(2026, 10, 3, 1, 0, tzinfo=timezone.utc)


def fixture(*, allow=True):
    return {
        "controller_version": "v398",
        "v398_status": "V398_VERIFIED_ALLOW" if allow else "V398_UPSTREAM_HOLD",
        "v398_autonomous_gate": {
            "status": "V398_VERIFIED_ALLOW" if allow else "V398_UPSTREAM_HOLD",
            "allow_execution": allow,
        },
        "v398_operating_mode": {
            "mode": "STEADY_OPTIMIZATION",
            "learning_budget": 0.16,
            "market_direction_inferred": False,
        },
        "v398_candidate_tournament": {
            "candidate_count": 3,
            "selected_recipe_key": "REQUEST_FRESHNESS_REFRESH|{}",
            "selected_score": 0.73,
            "selected_capability": {"primitive": "REQUEST_FRESHNESS_REFRESH"},
        },
        "v398_active_evaluation": {
            "status": "CANARY_OBSERVE",
            "rollback": False,
        },
        "v398_self_extension": {
            "write": {"status": "NOT_REQUESTED", "written": False},
        },
        "v390_goal_plan": {
            "primary_goal": {
                "goal_id": "RECOVER_MARKET_FRESHNESS",
                "urgency": 0.72,
            },
        },
        "v390_meta_critic": {"sample_count": 14},
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


def write_healthy_ui(root: Path):
    (root / "index.html").write_text(
        '<meta name="viewport"><div id="tabletManagerHub"></div>'
        '<link href="tablet_autonomy_dashboard_v399.css">'
        '<script src="tablet_autonomy_dashboard_v399.js"></script>',
        encoding="utf-8",
    )
    (root / "tablet_autonomy_dashboard_v399.css").write_text(
        ".tablet-autonomy-v399{} @media(prefers-reduced-motion:reduce){}",
        encoding="utf-8",
    )
    (root / "tablet_autonomy_dashboard_v399.js").write_text(
        'const report="tablet_autonomy_v399_report.json"; node.setAttribute("aria-live","polite");',
        encoding="utf-8",
    )
    (root / "sw.js").write_text(
        "tablet_autonomy_dashboard_v399.js tablet_autonomy_dashboard_v399.css",
        encoding="utf-8",
    )
    (root / "tcg_updater.py").write_text(
        "tablet_autonomy_v399_report.json",
        encoding="utf-8",
    )
    (root / "tablet_runtime_manifest.py").write_text(
        "tablet_autonomous_evolution_v399.py tablet_autonomy_dashboard_v399.js tablet_autonomy_dashboard_v399.css",
        encoding="utf-8",
    )
    (root / "main").write_text(
        "tablet_autonomous_evolution_v399.py --domain tablet_gpt",
        encoding="utf-8",
    )


class TabletAutonomousEvolutionV399Tests(unittest.TestCase):
    def test_safety_boundaries(self):
        self.assertTrue(autonomy.SAFETY["cross_surface_self_diagnosis_enabled"])
        self.assertTrue(autonomy.SAFETY["ui_gap_recurrence_learning_enabled"])
        self.assertTrue(autonomy.SAFETY["ui_source_feature_candidates_non_executable"])
        self.assertTrue(autonomy.SAFETY["v398_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["runtime_source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["runtime_source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["runtime_ui_source_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_ui_runtime_health_covers_ui_pwa_server_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_healthy_ui(root)
            health = autonomy.ui_runtime_health(root)
        self.assertTrue(health["healthy"])
        self.assertEqual(health["total"], health["passed"])
        self.assertEqual(0, health["critical_failed"])

    def test_repeated_ui_gap_becomes_protected_pr_candidate_only(self):
        state = autonomy._default_state()
        health = {
            "checks": [
                {
                    "check_id": "index_dashboard_js",
                    "ok": False,
                    "component": "ui",
                    "critical": True,
                }
            ]
        }
        state1, candidates1 = autonomy.update_gap_memory(state, health)
        self.assertEqual("observe", candidates1[0]["stage"])
        state2, candidates2 = autonomy.update_gap_memory(state1, health)
        self.assertEqual("protected_pr_candidate", candidates2[0]["stage"])
        self.assertFalse(candidates2[0]["auto_execute"])
        self.assertFalse(candidates2[0]["auto_generate_source"])
        self.assertFalse(candidates2[0]["auto_rewrite_source"])
        self.assertFalse(candidates2[0]["git_write"])
        self.assertTrue(candidates2[0]["protected_pr_ci_required"])

    def test_attention_surface_when_ui_is_critical_or_gate_holds(self):
        health = {"critical_failed": 1}
        policy = autonomy.composition_policy(fixture(), health)
        self.assertEqual("ATTENTION", policy["surface_mode"])
        self.assertEqual(30, policy["refresh_seconds"])
        self.assertFalse(policy["source_layout_auto_rewrite"])

        policy2 = autonomy.composition_policy(fixture(allow=False), {"critical_failed": 0})
        self.assertEqual("ATTENTION", policy2["surface_mode"])

    def test_upstream_hold_blocks_mutating_v398_execution(self):
        base = fixture(allow=False)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_healthy_ui(root)
            with mock.patch.object(autonomy.v398, "run_cycle", return_value=base) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=root / ".v399-state.json",
                    persist_outputs=False,
                )
            self.assertEqual("V399_UPSTREAM_HOLD", result["v399_status"])
            self.assertFalse(result["v399_autonomous_gate"]["allow_execution"])
            self.assertEqual(1, run.call_count)
            self.assertFalse(result["execution"]["executed"])

    def test_mutating_cycle_delegates_to_v398_and_persists_ui_learning(self):
        base = fixture(allow=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_healthy_ui(root)
            state_path = root / ".v399-state.json"
            with mock.patch.object(autonomy.v398, "run_cycle", return_value=base) as run:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    state_path=state_path,
                    persist_outputs=False,
                )
            self.assertEqual(2, run.call_count)
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("v399", saved["controller_version"])
            self.assertEqual(1, saved["cycle"])
            self.assertEqual("V399_VERIFIED_ALLOW", result["v399_status"])
            self.assertEqual(1.0, result["v399_ui_runtime_health"]["score"])
            self.assertEqual(3, result["v399_ui"]["candidate_count"])
            self.assertFalse(result["safety"]["runtime_ui_source_auto_rewrite"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
