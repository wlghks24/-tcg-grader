from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import tcg_grader_autonomous_evolution_v393 as autonomy

NOW = datetime(2026, 10, 2, 13, 0, tzinfo=timezone.utc)


def vision() -> dict:
    return {
        "analysisConfidence": 95,
        "frontCenter": 48,
        "backCenter": 48,
        "surfaceRisk": 8,
        "edgeRisk": 4,
        "cornerRisk": 4,
        "surfaceConfidence": 90,
        "quadrantWorstRisk": 8,
        "quadrantSurfaceWorstRisk": 8,
        "quadrantEdgeWorstRisk": 4,
        "quadrantCornerWorstRisk": 4,
        "quadrantMeanRisk": 5,
        "quadrantImbalance": 4,
        "quadrantConfidence": 90,
        "eightZoneWorstRisk": 9,
        "eightZoneSurfaceWorstRisk": 8,
        "eightZoneEdgeWorstRisk": 4,
        "eightZoneCornerWorstRisk": 4,
        "eightZoneMeanRisk": 5,
        "eightZoneImbalance": 5,
        "eightZoneConfidence": 90,
        "hierarchyDefectRisk": 9,
        "hierarchyConfidence": 90,
        "multiAngle": True,
    }


def rows(
    count: int = 30,
    *,
    company: str = "PSA",
    actual: float = 9.0,
    raw: float = 10.0,
) -> list[dict]:
    return [{
        "company": company,
        "actual": actual,
        "raw_pred": raw,
        "pred": raw,
        "certification_id": f"CERT-{i:04d}",
        "card_id": f"pokemon|set|card|{i:04d}",
        "official_result": True,
        "server_verified": True,
        "mode": "raw",
        "game": "pokemon",
        "vision": vision(),
    } for i in range(count)]


def core_fixture() -> dict:
    return {
        "controller_version": "tcg-grader-v392",
        "tcg_grader_autonomy_v392": {
            "quality_score": 0.75,
            "neural_plan": {"selected_actions": ["REVALIDATE_ONLY"]},
        },
        "safety": dict(autonomy.v392.SAFETY),
    }


class TcgGraderAutonomyV393Tests(unittest.TestCase):
    def test_state_contract(self):
        state = autonomy._default_state()
        self.assertTrue(autonomy._valid_state(state))
        self.assertTrue(autonomy.SAFETY["verified_shadow_experiments"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_holdout_split_is_deterministic_disjoint_and_bounded(self):
        sample = rows(30)
        train1, hold1 = autonomy.split_train_holdout(sample)
        train2, hold2 = autonomy.split_train_holdout(sample)
        self.assertEqual([autonomy._row_key(x) for x in hold1], [autonomy._row_key(x) for x in hold2])
        self.assertEqual(
            set(autonomy._row_key(x) for x in sample),
            set(autonomy._row_key(x) for x in train1) | set(autonomy._row_key(x) for x in hold1),
        )
        self.assertFalse(
            set(autonomy._row_key(x) for x in train1) & set(autonomy._row_key(x) for x in hold1)
        )

    def test_company_drift_detects_large_verified_error_shift(self):
        sample = rows(12, actual=9, raw=9) + [
            {
                **row,
                "certification_id": f"SHIFT-{i:04d}",
                "card_id": f"shift|{i:04d}",
                "raw_pred": 10.0,
                "pred": 10.0,
            }
            for i, row in enumerate(rows(12, actual=9, raw=10))
        ]
        report = autonomy.company_drift_report(sample)
        self.assertIn("PSA", report["critical_companies"])
        self.assertTrue(report["critical"])
        self.assertEqual("critical", report["companies"]["PSA"]["status"])

    def test_shadow_candidate_improves_verified_holdout_before_promotion(self):
        sample = rows(40, actual=9, raw=10)
        train, holdout = autonomy.split_train_holdout(sample)
        candidate = autonomy.build_snapshot(train, tag="shadow")
        comparison = autonomy.compare_candidate(candidate, None, holdout)
        self.assertTrue(comparison["eligible_for_promotion"])
        self.assertGreaterEqual(comparison["candidate"]["gain"], autonomy.MIN_PROMOTION_GAIN)
        self.assertLess(
            comparison["candidate"]["candidate_mae"],
            comparison["candidate"]["baseline_mae"],
        )

    def test_candidate_worse_than_champion_is_rejected(self):
        sample = rows(40, actual=9, raw=10)
        train, holdout = autonomy.split_train_holdout(sample)
        candidate = autonomy.build_snapshot(train, tag="shadow")
        champion = autonomy.build_snapshot(train, tag="champion")
        candidate["global_models"]["PSA"] = {
            **candidate["global_models"]["PSA"],
            "enabled": False,
            "correction": 0.0,
        }
        candidate["vision_profiles"] = {}
        comparison = autonomy.compare_candidate(candidate, champion, holdout)
        self.assertFalse(comparison["eligible_for_promotion"])
        self.assertIn("not_better_than_champion", comparison["reasons"])

    def test_critical_drift_blocks_promotion_and_core_mutation(self):
        stable = rows(12, actual=9, raw=9)
        shifted = []
        for i, row in enumerate(rows(12, actual=9, raw=10)):
            shifted.append({
                **row,
                "certification_id": f"SHIFT-{i:04d}",
                "card_id": f"shift|{i:04d}",
            })
        sample = stable + shifted
        audit = {"eligible": len(sample), "cert_conflicts": 0}
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.grade_learning, "eligible_training_rows", return_value=(sample, audit)), \
             mock.patch.object(autonomy.v392, "run_cycle", return_value=core_fixture()) as core, \
             mock.patch.object(autonomy.grade_learning, "rebuild_safe_vision_calibration") as rebuild:
            result = autonomy.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                now=NOW,
                persist_outputs=False,
            )
        self.assertEqual(1, core.call_count)
        payload = result["tcg_grader_autonomy_v393"]
        self.assertTrue(payload["critical_hold"])
        self.assertEqual("V393_CRITICAL_DRIFT_HOLD", payload["experiment"]["promotion"]["status"])
        rebuild.assert_not_called()

    def test_corrupt_experiment_state_fails_closed(self):
        sample = rows(30)
        audit = {"eligible": len(sample), "cert_conflicts": 0}
        with TemporaryDirectory() as td:
            root = Path(td)
            (root / autonomy.EXPERIMENT_STATE.name).write_text("{bad-json", encoding="utf-8")
            with mock.patch.object(autonomy.grade_learning, "eligible_training_rows", return_value=(sample, audit)), \
                 mock.patch.object(autonomy.v392, "run_cycle", return_value=core_fixture()) as core:
                result = autonomy.run_cycle(
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    persist_outputs=False,
                )
        self.assertEqual(1, core.call_count)
        self.assertTrue(result["tcg_grader_autonomy_v393"]["critical_hold"])
        self.assertFalse(result["v393_state_write"]["written"])

    def test_registry_gated_promotion_captures_deployed_champion(self):
        sample = rows(40)
        train, holdout = autonomy.split_train_holdout(sample)
        candidate = autonomy.build_snapshot(train, tag="shadow")
        comparison = autonomy.compare_candidate(candidate, None, holdout)
        drift = autonomy.company_drift_report(sample)
        fake_payload = {
            "registry_gate_v135": True,
            "registry_verified_training_rows": len(sample),
            "profiles": {},
        }
        with mock.patch.object(
            autonomy.grade_learning,
            "rebuild_safe_vision_calibration",
            return_value=fake_payload,
        ), mock.patch.object(
            autonomy,
            "production_snapshot",
            return_value={
                **candidate,
                "snapshot_id": "deployed",
                "vision_payload": fake_payload,
                "promotion_evaluation": {"candidate_mae": None},
            },
        ):
            result = autonomy.maybe_promote(
                rows=sample,
                candidate=candidate,
                comparison=comparison,
                drift=drift,
                execute=True,
                now=NOW,
            )
        self.assertTrue(result["executed"])
        self.assertEqual("V393_PROMOTED_VERIFIED_CALIBRATION", result["status"])
        self.assertEqual("champion", result["champion"]["tag"])

    def test_rollback_never_forces_global_calibration(self):
        sample = rows(30)
        _, holdout = autonomy.split_train_holdout(sample)
        champion = autonomy.build_snapshot(sample, tag="champion")
        champion["vision_payload"] = {"registry_gate_v135": True, "profiles": {}}
        good = {
            "rows": len(holdout), "candidate_mae": 0.1, "baseline_mae": 1.0,
            "candidate_worst": 0.5, "baseline_worst": 1.0, "gain": 0.9, "companies": {},
        }
        bad = {
            "rows": len(holdout), "candidate_mae": 0.8, "baseline_mae": 1.0,
            "candidate_worst": 1.0, "baseline_worst": 1.0, "gain": 0.2, "companies": {},
        }
        with mock.patch.object(autonomy, "production_snapshot", return_value=champion), \
             mock.patch.object(autonomy, "evaluate_snapshot", side_effect=[bad, good]), \
             mock.patch.object(autonomy.grade_learning.base, "_atomic_json") as write:
            result = autonomy.maybe_rollback_vision(
                rows=sample,
                champion=champion,
                drift={"critical": False},
                execute=True,
            )
        self.assertTrue(result["executed"])
        self.assertFalse(result["global_calibration_rollback_forced"])
        write.assert_called_once()

    def test_run_cycle_promotes_only_after_shadow_comparison(self):
        sample = rows(40)
        audit = {"eligible": len(sample), "cert_conflicts": 0}
        promoted = {
            "status": "V393_PROMOTED_VERIFIED_CALIBRATION",
            "executed": True,
            "champion": {
                **autonomy.build_snapshot(sample, tag="champion"),
                "tag": "champion",
                "promoted_at": NOW.isoformat(),
            },
        }
        promoted["champion"]["promotion_evaluation"] = {"candidate_mae": 0.0}
        with TemporaryDirectory() as td, \
             mock.patch.object(autonomy.grade_learning, "eligible_training_rows", return_value=(sample, audit)), \
             mock.patch.object(autonomy.v392, "run_cycle", side_effect=[core_fixture(), core_fixture()]) as core, \
             mock.patch.object(autonomy, "maybe_rollback_vision", return_value={"status": "OK", "executed": False}), \
             mock.patch.object(autonomy, "maybe_promote", return_value=promoted):
            result = autonomy.run_cycle(
                execute=True,
                apply_capabilities=True,
                train_meta=True,
                apply_skills=True,
                root=Path(td),
                now=NOW,
                persist_outputs=False,
            )
        self.assertEqual(2, core.call_count)
        self.assertTrue(result["v393_state_write"]["written"])
        self.assertIsNotNone(result["tcg_grader_autonomy_v393"]["experiment"]["champion_id"])


if __name__ == "__main__":
    unittest.main()
