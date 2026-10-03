import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v400 as autonomy

NOW = datetime(2026, 10, 3, 0, 15, tzinfo=timezone.utc)


def upstream_fixture(*, allow=True):
    return {
        "controller_version": "v399",
        "v399_status": "V399_VERIFIED_ALLOW" if allow else "V399_UPSTREAM_HOLD",
        "v399_autonomous_gate": {
            "allow_execution": allow,
            "status": "V399_VERIFIED_ALLOW" if allow else "V399_UPSTREAM_HOLD",
        },
        "v399_ui_runtime_health": {
            "score": 1.0,
            "passed": 13,
            "total": 13,
            "critical_failed": 0,
            "healthy": True,
        },
        "v398_self_extension": {"new_capability": None, "write": {"written": False}},
        "v398_active_evaluation": {
            "status": "NO_ACTIVE_V398_CAPABILITY",
            "rollback": False,
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


def write_assets(root: Path, *, verification=True, market=True, events=True):
    (root / "index.html").write_text(
        '<meta name="viewport"><link href="tablet_autonomy_dashboard_v400.css">'
        '<div id="tabletManagerHub"></div><script src="tablet_autonomy_dashboard_v400.js"></script>',
        encoding="utf-8",
    )
    (root / "tablet_autonomy_dashboard_v400.css").write_text(
        "@media(prefers-reduced-motion:reduce){}", encoding="utf-8"
    )
    (root / "tablet_autonomy_dashboard_v400.js").write_text(
        'const REPORT_URL="./tablet_autonomy_v400_report.json"; const x="aria-live";', encoding="utf-8"
    )
    (root / "sw.js").write_text(
        "tablet_autonomy_dashboard_v400.js tablet_autonomy_dashboard_v400.css", encoding="utf-8"
    )
    (root / "tcg_updater.py").write_text("tablet_autonomy_v400_report.json", encoding="utf-8")
    (root / "tablet_runtime_manifest.py").write_text(
        "tablet_autonomous_evolution_v400.py tablet_autonomy_dashboard_v400.js tablet_autonomy_dashboard_v400.css",
        encoding="utf-8",
    )
    (root / "main").write_text(
        "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
        encoding="utf-8",
    )
    for name in (
        "grading_vision_engine.js",
        "grading_accuracy_v99.js",
        "grading_accuracy_v99.py",
        "card_identity_recognition.js",
        "card_identity_recognition.py",
        "image_quality_guard.js",
        "auto_validation_flow.js",
        "grade_market_flow.js",
    ):
        (root / name).write_text("//ok\n", encoding="utf-8")
    if verification:
        (root / "V109_FINAL_VERIFICATION_REPORT.json").write_text(json.dumps({
            "checked_at": "2026-10-02T00:00:00Z",
            "ok": True,
            "policy": {
                "automatic_ocr_predictions_train": False,
                "user_confirmation_required": True,
                "raw_slab_grade_learning_isolated": True,
            },
        }), encoding="utf-8")
    if market:
        entries = {}
        for i, region in enumerate(("KR", "JP", "US") * 4):
            entries[f"{region}|CARD{i}|BOX"] = {
                "link_status": "정상",
                "source_date": "2026-10-02",
            }
        (root / "market_prices.json").write_text(json.dumps({
            "updated_at": "2026-10-02T00:00:00Z",
            "entries": entries,
        }), encoding="utf-8")
    if events:
        items = []
        for game in ("포켓몬 카드", "원피스 카드", "나루토 카드"):
            for region in ("KR", "JP", "US"):
                items.append({
                    "game": game,
                    "region": region,
                    "category": "collaboration" if region == "KR" else "promo",
                    "source_grade": "official",
                    "link_status": "정상",
                })
        (root / "promo_events.json").write_text(json.dumps({
            "updated_at": "2026-10-02T00:00:00Z",
            "items": items,
            "coverage": {
                "expected_game_region_pairs": 9,
                "watched_game_region_pairs": 9,
                "covered_game_region_pairs": 9,
                "movie_game_region_pairs": 9,
            },
        }), encoding="utf-8")


class TabletAutonomousEvolutionV400Tests(unittest.TestCase):
    def test_safety_contract_keeps_source_and_fact_boundaries(self):
        self.assertTrue(autonomy.SAFETY["ui_card_measurement_market_event_governance_enabled"])
        self.assertTrue(autonomy.SAFETY["missing_surface_evidence_triggers_revalidation"])
        self.assertTrue(autonomy.SAFETY["surface_runtime_self_extension_allowlisted_only"])
        self.assertTrue(autonomy.SAFETY["surface_source_feature_candidates_non_executable"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["card_measurement_grade_invention"])
        self.assertFalse(autonomy.SAFETY["card_market_price_invention"])
        self.assertFalse(autonomy.SAFETY["event_fact_invention"])
        self.assertFalse(autonomy.SAFETY["git_write"])

    def test_four_surfaces_are_scored_from_operational_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            rows = {row["surface"]: row for row in portfolio["surfaces"]}
            self.assertEqual(set(autonomy.SURFACES), set(rows))
            self.assertEqual(["JP", "KR", "US"], rows["card_market"]["evidence"]["regions"])
            self.assertEqual(3, rows["collab_event"]["evidence"]["collaboration_count"])
            self.assertFalse(rows["card_market"]["evidence"]["prices_invented"])
            self.assertFalse(rows["collab_event"]["evidence"]["event_facts_invented"])

    def test_missing_grading_verification_becomes_revalidation_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root, verification=False)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            rows = {row["surface"]: row for row in portfolio["surfaces"]}
            self.assertEqual(0.0, rows["card_measurement"]["confidence"])
            self.assertEqual("attention", rows["card_measurement"]["status"])
            self.assertEqual("card_measurement", portfolio["selected_surface"])
            cap = autonomy.steering_capability(portfolio, now=NOW)
            self.assertIsNotNone(cap)
            self.assertEqual("INCREASE_OBSERVATION", cap["primitive"])
            self.assertTrue(autonomy._v373().validate_capability(cap, now=NOW))

    def test_surface_candidates_never_execute_source_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root, verification=False)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            state = autonomy.update_surface_memory(autonomy._default_state(), portfolio)
            state2 = autonomy.update_surface_memory(state, portfolio)
            candidates = autonomy.source_feature_candidates(portfolio, state2["surface_memory"])
            card = next(row for row in candidates if row["surface"] == "card_measurement")
            self.assertEqual("protected_pr_candidate", card["stage"])
            self.assertFalse(card["auto_execute"])
            self.assertFalse(card["auto_generate_source"])
            self.assertFalse(card["auto_rewrite_source"])
            self.assertFalse(card["git_write"])
            self.assertIn("certified_grade_holdout_validation", card["validation_required"])

    def test_upstream_hold_prevents_mutation_and_capability_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root, verification=False)
            cap_path = root / "caps.json"
            with mock.patch.object(autonomy.v399, "run_cycle", return_value=upstream_fixture(allow=False)):
                result = autonomy.run_cycle(
                    domain="tablet_gpt",
                    execute=True,
                    apply_capabilities=True,
                    train_meta=True,
                    apply_skills=True,
                    root=root,
                    now=NOW,
                    capability_path=cap_path,
                    persist_outputs=False,
                )
            self.assertEqual("V400_UPSTREAM_HOLD", result["v400_status"])
            self.assertFalse(result["v400_autonomous_gate"]["allow_execution"])
            self.assertFalse(cap_path.exists())
            self.assertFalse(result["execution"]["executed"])

    def test_mutating_cycle_persists_domain_state_and_bounded_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root, verification=False)
            cap_path = root / "caps.json"
            state_path = root / ".v400-state.json"
            base = upstream_fixture()
            with mock.patch.object(autonomy.v399, "run_cycle", return_value=base):
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
            self.assertTrue(state_path.is_file())
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual("v400", saved["controller_version"])
            self.assertEqual(1, saved["cycle"])
            self.assertEqual("card_measurement", saved["active"]["surface"])
            self.assertTrue(cap_path.is_file())
            caps = json.loads(cap_path.read_text(encoding="utf-8"))["capabilities"]
            self.assertEqual(1, len([
                row for row in caps
                if (row.get("evidence") or {}).get("owner_controller") == "v400"
            ]))
            self.assertEqual("v400", result["controller_version"])
            self.assertEqual("V400_VERIFIED_ALLOW", result["v400_status"])
            self.assertEqual("card_measurement", result["v400_surface_portfolio"]["selected_surface"])
            self.assertFalse(result["safety"]["source_code_auto_generation"])

    def test_active_surface_regression_requests_exact_rollback(self):
        state = autonomy._default_state()
        state["cycle"] = 2
        state["active"] = {
            "id": "CAP",
            "surface": "card_market",
            "primitive": "REQUEST_FRESHNESS_REFRESH",
            "baseline_score": 0.90,
            "activated_cycle": 1,
        }
        portfolio = {
            "surfaces": [{
                "surface": "card_market",
                "score": 0.70,
                "confidence": 1.0,
                "urgency": 0.30,
                "status": "observe",
            }]
        }
        result = autonomy.evaluate_active(state, portfolio, {"CAP"}, upstream_allow=True)
        self.assertEqual("MATERIAL_SURFACE_REGRESSION", result["status"])
        self.assertTrue(result["rollback"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
