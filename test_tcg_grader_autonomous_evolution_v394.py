from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import tcg_grader_autonomous_evolution_v394 as autonomy

NOW = datetime(2026, 10, 2, 13, 10, tzinfo=timezone.utc)


def vision() -> dict:
    return {
        "analysisConfidence": 95, "frontCenter": 48, "backCenter": 48,
        "surfaceRisk": 8, "edgeRisk": 4, "cornerRisk": 4, "surfaceConfidence": 90,
        "quadrantWorstRisk": 8, "quadrantSurfaceWorstRisk": 8,
        "quadrantEdgeWorstRisk": 4, "quadrantCornerWorstRisk": 4,
        "quadrantMeanRisk": 5, "quadrantImbalance": 4, "quadrantConfidence": 90,
        "eightZoneWorstRisk": 9, "eightZoneSurfaceWorstRisk": 8,
        "eightZoneEdgeWorstRisk": 4, "eightZoneCornerWorstRisk": 4,
        "eightZoneMeanRisk": 5, "eightZoneImbalance": 5, "eightZoneConfidence": 90,
        "hierarchyDefectRisk": 9, "hierarchyConfidence": 90, "multiAngle": True,
    }


def rows(count=40, company="PSA", actual=9.0, raw=10.0):
    return [{
        "company": company, "actual": actual, "raw_pred": raw, "pred": raw,
        "certification_id": f"{company}-CERT-{i:04d}",
        "card_id": f"pokemon|set|{company}|{i:04d}",
        "official_result": True, "server_verified": True, "mode": "raw",
        "game": "pokemon", "vision": vision(),
    } for i in range(count)]


def core_fixture():
    return {
        "controller_version": "tcg-grader-v393",
        "tcg_grader_autonomy_v393": {
            "verified_rows": 40, "audit_ok": True,
            "company_drift": {"critical": False, "critical_companies": [], "companies": {}},
        },
        "safety": dict(autonomy.v393.SAFETY),
    }


class V394Tests(unittest.TestCase):
    def test_safety_contract(self):
        self.assertTrue(autonomy.SAFETY["multi_candidate_verified_tournament"])
        self.assertTrue(autonomy.SAFETY["evidence_sufficiency_gate"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_evidence_policy_prioritizes_missing_company_labels(self):
        sample = rows(40, "PSA")
        evidence = autonomy.evidence_report(sample)
        drift = autonomy.v393.company_drift_report(sample)
        policy = autonomy.company_policy(sample, drift, evidence)
        self.assertEqual("ready", evidence["companies"]["PSA"]["status"])
        self.assertEqual("collect_more", evidence["companies"]["BGS"]["status"])
        self.assertEqual("EXPAND_VERIFIED_LABELS", policy["companies"]["BGS"]["action"])

    def test_critical_company_drift_freezes_company(self):
        stable = rows(12, "PSA", actual=9, raw=9)
        shifted = [{
            **row,
            "certification_id": f"SHIFT-{i}",
            "card_id": f"shift|{i}",
            "raw_pred": 10.0,
            "pred": 10.0,
        } for i, row in enumerate(rows(12, "PSA", actual=9, raw=10))]
        sample = stable + shifted
        drift = autonomy.v393.company_drift_report(sample)
        evidence = autonomy.evidence_report(sample)
        policy = autonomy.company_policy(sample, drift, evidence)
        self.assertEqual("FREEZE_AND_REVERIFY", policy["companies"]["PSA"]["action"])
        self.assertEqual(1.0, policy["companies"]["PSA"]["priority"])

    def test_candidate_strategies_are_bounded(self):
        sample = rows(40)
        evidence = autonomy.evidence_report(sample)
        strategies = autonomy.candidate_strategies(sample, evidence)
        self.assertLessEqual(len(strategies), autonomy.MAX_CANDIDATES)
        self.assertEqual(
            {"global_only", "conservative", "company_guarded", "vision_specialist"},
            set(strategies),
        )

    def test_tournament_selects_verified_safe_winner(self):
        sample = rows(40)
        train, holdout = autonomy.v393.split_train_holdout(sample)
        evidence = autonomy.evidence_report(sample)
        result = autonomy.tournament(train, holdout, evidence, None)
        self.assertEqual("WINNER_SELECTED", result["status"])
        self.assertIsNotNone(result["winner"])
        self.assertTrue(result["winner"]["eligible"])
        maes = [row["mae"] for row in result["candidates"] if row["eligible"] and row["mae"] is not None]
        self.assertEqual(min(maes), result["winner"]["mae"])

    def test_tournament_fails_closed_on_small_verified_dataset(self):
        sample = rows(8)
        train, holdout = autonomy.v393.split_train_holdout(sample)
        result = autonomy.tournament(train, holdout, autonomy.evidence_report(sample), None)
        self.assertEqual("INSUFFICIENT_VERIFIED_EVIDENCE", result["status"])
        self.assertIsNone(result["winner"])

    def test_recovery_plan_includes_audit_drift_and_missing_evidence(self):
        sample = rows(8, "PSA")
        evidence = autonomy.evidence_report(sample)
        drift = {
            "critical": True,
            "critical_companies": ["PSA"],
            "companies": {"PSA": {"status": "critical", "severity": 1.0}},
        }
        tournament = {"status": "NO_SAFE_WINNER"}
        plan = autonomy.recovery_plan(
            audit_ok=False, drift=drift, evidence=evidence, tournament_result=tournament
        )
        actions = [row["action"] for row in plan]
        self.assertEqual("RECOVER_VERIFIED_GRADE_AUDIT", actions[0])
        self.assertIn("FREEZE_COMPANY_AND_REVERIFY", actions)
        self.assertIn("EXPAND_VERIFIED_LABELS", actions)

    def test_run_cycle_blocks_mutation_on_critical_drift(self):
        stable = rows(12, "PSA", actual=9, raw=9)
        shifted = [{
            **row,
            "certification_id": f"SHIFT-{i}",
            "card_id": f"shift|{i}",
            "raw_pred": 10.0,
            "pred": 10.0,
        } for i, row in enumerate(rows(12, "PSA", actual=9, raw=10))]
        sample = stable + shifted
        audit = {"eligible": len(sample), "cert_conflicts": 0}
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.v393, "run_cycle", return_value=core_fixture()) as core, \
             mock.patch.object(autonomy.v393.grade_learning, "eligible_training_rows", return_value=(sample, audit)), \
             mock.patch.object(autonomy.v393, "maybe_promote") as promote:
            result = autonomy.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=Path(td), now=NOW, persist_outputs=False,
            )
        self.assertEqual(1, core.call_count)
        self.assertTrue(result["tcg_grader_autonomy_v394"]["blocked"])
        promote.assert_not_called()

    def test_run_cycle_uses_v393_promotion_gate_for_winner(self):
        sample = rows(40)
        audit = {"eligible": len(sample), "cert_conflicts": 0}
        fake_promotion = {"status": "V393_PROMOTION_PLAN_ONLY", "executed": False}
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.v393, "run_cycle", side_effect=[core_fixture(), core_fixture()]) as core, \
             mock.patch.object(autonomy.v393.grade_learning, "eligible_training_rows", return_value=(sample, audit)), \
             mock.patch.object(autonomy.v393, "maybe_promote", return_value=fake_promotion) as promote:
            result = autonomy.run_cycle(
                execute=True, apply_capabilities=True, train_meta=True, apply_skills=True,
                root=Path(td), now=NOW, persist_outputs=False,
            )
        self.assertEqual(2, core.call_count)
        self.assertEqual("V393_PROMOTION_PLAN_ONLY", result["tcg_grader_autonomy_v394"]["promotion"]["status"])
        promote.assert_called_once()


if __name__ == "__main__":
    unittest.main()
