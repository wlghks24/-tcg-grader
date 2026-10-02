from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import tcg_grader_autonomous_evolution_v395 as autonomy

NOW = datetime(2026, 10, 2, 13, 20, tzinfo=timezone.utc)


def vision(bucket_shift=0):
    return {
        "analysisConfidence": 95, "frontCenter": 48, "backCenter": 48,
        "surfaceRisk": 8 + bucket_shift, "edgeRisk": 4, "cornerRisk": 4,
        "surfaceConfidence": 90, "quadrantWorstRisk": 8 + bucket_shift,
        "quadrantSurfaceWorstRisk": 8 + bucket_shift, "quadrantEdgeWorstRisk": 4,
        "quadrantCornerWorstRisk": 4, "quadrantMeanRisk": 5,
        "quadrantImbalance": 4, "quadrantConfidence": 90,
        "eightZoneWorstRisk": 9 + bucket_shift, "eightZoneSurfaceWorstRisk": 8 + bucket_shift,
        "eightZoneEdgeWorstRisk": 4, "eightZoneCornerWorstRisk": 4,
        "eightZoneMeanRisk": 5, "eightZoneImbalance": 5,
        "eightZoneConfidence": 90, "hierarchyDefectRisk": 9 + bucket_shift,
        "hierarchyConfidence": 90, "multiAngle": True,
    }


def rows(count=24, company="PSA", actual=9.0, raw=10.0, game="pokemon", bucket_shift=0):
    return [{
        "company": company, "actual": actual, "raw_pred": raw, "pred": raw,
        "certification_id": f"{company}-{game}-{i:04d}",
        "card_id": f"{game}|set|{company}|{i:04d}",
        "official_result": True, "server_verified": True, "mode": "raw",
        "game": game, "vision": vision(bucket_shift),
    } for i in range(count)]


def evidence_for(sample):
    return autonomy.v394.evidence_report(sample)


def stable_drift():
    return {
        "critical": False,
        "critical_companies": [],
        "companies": {
            company: {"status": "stable", "severity": 0.0}
            for company in autonomy.v394.COMPANIES
        },
    }


def preview_fixture(headroom=0.8):
    return {
        "controller_version": "tcg-grader-v394",
        "tcg_grader_autonomy_v394": {"blocked": False},
        "v382_kpis": {"dimensions": {
            "resource_headroom": headroom,
            "market_freshness": 0.8,
            "market_coverage": 0.8,
            "source_health": 0.8,
            "neural_consensus": 0.8,
        }},
        "v388_resource_budget": {"selected_uncertainty": 0.5, "drift_score": 0.4},
        "market_adaptation_v381": {
            "regime": "NORMAL_VOLATILITY",
            "low_coverage_regions": [],
            "degraded_source_ratio": 0.05,
            "stress_score": 0.2,
        },
    }


class V395Tests(unittest.TestCase):
    def test_safety_contract(self):
        self.assertTrue(autonomy.SAFETY["verified_active_learning"])
        self.assertFalse(autonomy.SAFETY["synthetic_label_training"])
        self.assertFalse(autonomy.SAFETY["source_reliability_changes_factual_trust"])
        self.assertTrue(autonomy.SAFETY["low_headroom_runtime_protection"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_active_learning_prioritizes_sparse_high_error_segment(self):
        sample = rows(3, "PSA", actual=8, raw=10, game="pokemon")
        sample += rows(24, "BGS", actual=9, raw=9, game="onepiece")
        evidence = evidence_for(sample)
        targets = autonomy.active_learning_targets(sample, stable_drift(), evidence, limit=12)
        psa = next(row for row in targets if row["company"] == "PSA")
        bgs = next(row for row in targets if row["company"] == "BGS")
        self.assertGreater(psa["priority"], bgs["priority"])
        self.assertFalse(psa["synthetic_label_allowed"])
        self.assertIn("official-registry-verified", psa["requested_evidence"])

    def test_active_learning_keeps_zero_row_company_visible(self):
        sample = rows(24, "PSA")
        targets = autonomy.active_learning_targets(sample, stable_drift(), evidence_for(sample))
        zero = [row for row in targets if row["company"] == "TAG" and row["verified_rows"] == 0]
        self.assertTrue(zero)
        self.assertEqual("coverage-gap", zero[0]["vision_bucket"])

    def test_source_reliability_cools_bad_routes_without_changing_trust(self):
        providers = {"providers": [{
            "provider": "p1", "configured_runs": 4, "errors": 3,
            "response_rate": 0.25, "error_streak": 3, "empty_streak": 1,
        }]}
        search = {"methods": [{
            "method": "m1", "attempts": 5, "response_rate": 0.2,
            "nonempty_rate": 0.1, "blocked_rate": 0.4,
            "rate_limited_rate": 0.1, "timeout_rate": 0.0,
            "failure_streak": 3, "cooling_down": True,
        }]}
        policy = autonomy.source_reliability_policy(providers, search)
        self.assertEqual(2, policy["counts"]["COOLDOWN"])
        self.assertFalse(policy["factual_trust_learning"])
        self.assertFalse(policy["permanent_blacklist"])
        self.assertTrue(all(not row["factual_trust_changed"] for row in policy["routes"]))

    def test_resource_schedule_protects_foreground_on_low_headroom(self):
        with mock.patch.object(
            autonomy.v394.v393.v392,
            "observation",
            return_value={"dimensions": {"resource_headroom": 0.1}, "uncertainty": 0.8, "drift": 0.7},
        ):
            schedule = autonomy.resource_schedule({})
        self.assertEqual("PROTECT_RUNTIME", schedule["mode"])
        self.assertFalse(schedule["allow_mutation"])
        flags = autonomy.effective_flags(
            schedule, execute=True, apply_capabilities=True, train_meta=True, apply_skills=True
        )
        self.assertFalse(any(flags.values()))

    def test_resource_schedule_light_mode_disables_optional_meta_and_skills(self):
        schedule = {
            "mode": "LIGHT_LEARNING", "allow_mutation": True,
            "resource_headroom": 0.4, "active_target_budget": 4,
        }
        flags = autonomy.effective_flags(
            schedule, execute=True, apply_capabilities=True, train_meta=True, apply_skills=True
        )
        self.assertTrue(flags["execute"])
        self.assertTrue(flags["apply_capabilities"])
        self.assertFalse(flags["train_meta"])
        self.assertFalse(flags["apply_skills"])

    def test_market_mode_prioritizes_source_recovery_before_coverage(self):
        core = {"market_adaptation_v381": {
            "regime": "UNDERCOVERED", "stress_score": 0.9,
            "low_coverage_regions": ["JP"],
        }}
        mode = autonomy.market_operating_mode(
            core, {"degraded_or_cooldown_ratio": 0.6}
        )
        self.assertEqual("SOURCE_RECOVERY", mode["mode"])
        self.assertFalse(mode["market_direction_inferred"])

    def test_feature_contracts_are_non_executable(self):
        targets = [{"priority": 0.9}]
        sources = {"degraded_or_cooldown_ratio": 0.7}
        schedule = {"mode": "PROTECT_RUNTIME"}
        contracts = autonomy.feature_contracts(targets, sources, schedule)
        self.assertGreaterEqual(len(contracts), 3)
        self.assertTrue(all(row["auto_execute"] is False for row in contracts))
        self.assertTrue(all(row["source_code_generated"] is False for row in contracts))
        self.assertTrue(all(row["protected_pr_ci_required"] is True for row in contracts))

    def test_run_cycle_low_headroom_keeps_core_preview_non_mutating(self):
        sample = rows(24, "PSA")
        audit = {"eligible": len(sample)}
        preview = preview_fixture(0.1)
        protect = {
            "mode": "PROTECT_RUNTIME", "resource_headroom": 0.1,
            "uncertainty": 0.8, "drift": 0.7, "allow_mutation": False,
            "optional_learning_budget": 0.0, "active_target_budget": 2,
            "protect_foreground_grading": True,
        }
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.v394, "run_cycle", return_value=preview) as core, \
             mock.patch.object(autonomy.v394.v393.grade_learning, "eligible_training_rows", return_value=(sample, audit)), \
             mock.patch.object(autonomy.v394.v393, "company_drift_report", return_value=stable_drift()), \
             mock.patch.object(autonomy, "read_source_reports", return_value={"provider_report": {}, "search_report": {}, "errors": []}), \
             mock.patch.object(autonomy, "resource_schedule", return_value=protect):
            result = autonomy.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=Path(td), now=NOW, persist_outputs=False,
            )
        self.assertEqual(1, core.call_count)
        self.assertEqual("PROTECT_RUNTIME", result["tcg_grader_autonomy_v395"]["resource_schedule"]["mode"])
        self.assertFalse(any(result["tcg_grader_autonomy_v395"]["effective_mutation_flags"].values()))

    def test_run_cycle_balanced_bounds_optional_skills(self):
        sample = rows(24, "PSA")
        audit = {"eligible": len(sample)}
        preview = preview_fixture(0.6)
        executed = {**preview, "controller_version": "tcg-grader-v394"}
        balanced = {
            "mode": "BALANCED", "resource_headroom": 0.6,
            "uncertainty": 0.5, "drift": 0.4, "allow_mutation": True,
            "optional_learning_budget": 0.6, "active_target_budget": 8,
            "protect_foreground_grading": False,
        }
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.v394, "run_cycle", side_effect=[preview, executed]) as core, \
             mock.patch.object(autonomy.v394.v393.grade_learning, "eligible_training_rows", return_value=(sample, audit)), \
             mock.patch.object(autonomy.v394.v393, "company_drift_report", return_value=stable_drift()), \
             mock.patch.object(autonomy, "read_source_reports", return_value={"provider_report": {}, "search_report": {}, "errors": []}), \
             mock.patch.object(autonomy, "resource_schedule", return_value=balanced):
            result = autonomy.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=Path(td), now=NOW, persist_outputs=False,
            )
        self.assertEqual(2, core.call_count)
        second = core.call_args_list[1].kwargs
        self.assertTrue(second["train_meta"])
        self.assertFalse(second["apply_skills"])
        self.assertEqual("BALANCED", result["tcg_grader_autonomy_v395"]["resource_schedule"]["mode"])


if __name__ == "__main__":
    unittest.main()
