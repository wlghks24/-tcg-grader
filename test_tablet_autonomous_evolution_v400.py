import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import tablet_autonomous_evolution_v400 as autonomy
import tablet_runtime_manifest

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
        "plan": {
            "meta_scores": {
                "TRAIN_QUERY_STRATEGY": 0.0,
                "TRAIN_JOB_STRATEGY": 0.0,
                "TRAIN_REPAIR_PRIORITY": 0.0,
                "REFRESH_MARKET_DATA": 0.0,
                "EXPAND_MARKET_COVERAGE": 0.0,
                "RECHECK_DEGRADED_SOURCES": 0.0,
            },
        },
        "meta_neural": {
            "active": False,
            "sample_count": 0,
            "training": {"status": "META_TRAINING_NOT_REQUESTED", "written": False},
        },
        "execution": {
            "status": "PLAN_ONLY",
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
        },
        "safety": {},
    }


def write_assets(root: Path, *, verification=True, market=True, releases=True, events=True):
    # V401: the tablet operations surface evaluates the same complete runtime
    # manifest used by START_TCG_UPDATER_ANDROID.sh. Unit fixtures therefore
    # materialize neutral placeholders for that deployable bundle before
    # overriding the files whose contents matter to each test.
    for name in tablet_runtime_manifest.ACTIVE_RUNTIME_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("{}\n" if path.suffix == ".json" else "ok\n", encoding="utf-8")
    category_markup = "".join(
        '<details class="feature-category" data-category-key="' + category + '">'
        + "".join(
            '<a class="feature-shortcut" href="#' + autonomy.FEATURE_TARGETS[feature]
            + '" data-feature-key="' + feature + '"></a>'
            for feature in autonomy.FEATURE_SHORTCUT_ORDER[category]
        )
        + "</details>"
        for category in autonomy.CATEGORY_ORDER
    )
    target_markup = "".join(
        '<section id="' + target + '"></section>'
        for target in sorted(set(autonomy.FEATURE_TARGETS.values()))
        if target != "tabletManagerHub"
    )
    video_dom_markup = (
        '<div id="purchasePanel"></div><div id="purchaseNearby"></div><div id="purchaseRegionGrid"></div>'
        '<div id="cameraStatus"></div><div id="glare"></div><div id="agmRawPrice"></div>'
    )
    (root / "index.html").write_text(
        '<meta name="viewport"><link href="tablet_autonomy_dashboard_v400.css">'
        '<div id="tabletManagerHub"></div><div id="featureCategories">' + category_markup + '</div>'
        + target_markup + video_dom_markup + '<script src="tablet_autonomy_dashboard_v400.js"></script>',
        encoding="utf-8",
    )
    (root / "tablet_autonomy_dashboard_v400.css").write_text(
        "/* V407 video-reference adaptive experience */"
        "/* V404 video-reference refinement */"
        ".video-experience-evidence{}@media(prefers-reduced-motion:reduce){}", encoding="utf-8"
    )
    (root / "tablet_autonomy_dashboard_v400.js").write_text(
        'const REPORT_URL="./tablet_autonomy_v400_report.json";'
        'const CATEGORY_KEYS=["grading","market","box","news","purchase","learning","tablet","code"];'
        'const FEATURE_KEYS={};const FEATURE_TARGETS={};'
        'function applyAdaptiveFeatures(){}function restoreOriginalFeatures(){};'
        'function applyAdaptiveModules(){}function restoreAdaptiveModules(){};'
        'const EXPERIENCE_KEYS=[];const PURCHASE_REGION_KEY="tcgPurchaseRecentRegionV404";'
        'const REGION_SUBREGIONS={};function videoExperienceV403(){};'
        'function validExperiencePlan(){const x={module_confidence:{},module_state:{}}};'
        'function applyExperienceOrder(){}function restoreExperienceOrder(){};'
        'function purchaseVideoSubregion(){}function videoCaptureReadiness(){}function economicsValue(){};'
        'const refs="market_watch.json market_prices.json releases.json promo_events.json MutationObserver video-hot-confidence module_confidence module_state";'
        'const x="aria-live";',
        encoding="utf-8"
    )
    (root / "sw.js").write_text(
        "tablet_autonomy_dashboard_v400.js tablet_autonomy_dashboard_v400.css", encoding="utf-8"
    )
    (root / "tcg_updater.py").write_text("tablet_autonomy_v400_report.json", encoding="utf-8")
    (root / "tablet_runtime_manifest.py").write_text(
        "tablet_autonomous_evolution_v400.py screen_policy_neural_v401.py tablet_autonomy_dashboard_v400.js tablet_autonomy_dashboard_v400.css",
        encoding="utf-8",
    )
    (root / "main").write_text(
        "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
        encoding="utf-8",
    )
    for name in (
        "TABLET_SCHEDULED_UPDATE.sh",
        "ANDROID_UPDATE_AND_START.sh",
        "ANDROID_RECOVER_UPDATE.sh",
        "VERIFY_TABLET_FINAL.sh",
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
    (root / "purchase_sources.json").write_text(json.dumps({
        "updated_at": "2026-10-02T00:00:00Z",
        "sources": [
            {"name": f"SRC-{region}-{game}", "region": region, "games": [game],
             "type": "official" if game == "Pokemon" else "marketplace",
             "link_status": "정상", "last_checked_at": "2026-10-02T00:00:00Z"}
            for region in ("KR", "JP", "US")
            for game in ("Pokemon", "ONE PIECE", "NARUTO")
        ],
    }), encoding="utf-8")
    (root / "purchase_signals.json").write_text(json.dumps({
        "updated_at": "2026-10-02T00:00:00Z", "items": []
    }), encoding="utf-8")
    (root / "market_watch.json").write_text(json.dumps({
        "updated_at": "2026-10-02T00:00:00Z",
        "items": [{"sale_status": "거래중"} for _ in range(12)],
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
    if releases:
        release_items = []
        game_names = ("Pokémon", "ONE PIECE", "NARUTO")
        for game in game_names:
            for region in ("KR", "JP", "US"):
                release_items.append({
                    "game": game,
                    "region": region,
                    "name": f"{game}-{region}-TEST",
                    "release_date": "2026-10-03",
                    "status": "공식 출시 확인",
                    "source": "https://example.invalid/official",
                    "last_verified_at": "2026-10-02T00:00:00Z",
                    "link_status": "정상",
                    "lifecycle": "current",
                })
        (root / "releases.json").write_text(json.dumps({
            "updated_at": "2026-10-02T00:00:00Z",
            "items": release_items,
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
        self.assertTrue(autonomy.SAFETY["ui_card_measurement_market_release_event_governance_enabled"])
        self.assertTrue(autonomy.SAFETY["missing_surface_evidence_triggers_revalidation"])
        self.assertTrue(autonomy.SAFETY["current_runtime_verification_preferred"])
        self.assertTrue(autonomy.SAFETY["historical_v109_audit_fallback_only"])
        self.assertTrue(autonomy.SAFETY["surface_runtime_self_extension_allowlisted_only"])
        self.assertTrue(autonomy.SAFETY["surface_source_feature_candidates_non_executable"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["card_measurement_grade_invention"])
        self.assertFalse(autonomy.SAFETY["card_market_price_invention"])
        self.assertFalse(autonomy.SAFETY["card_release_fact_invention"])
        self.assertFalse(autonomy.SAFETY["event_fact_invention"])
        self.assertTrue(autonomy.SAFETY["purchase_availability_surface_enabled"])
        self.assertTrue(autonomy.SAFETY["tablet_ops_surface_enabled"])
        self.assertTrue(autonomy.SAFETY["adaptive_ui_composition_enabled"])
        self.assertTrue(autonomy.SAFETY["adaptive_ui_user_override_required"])
        self.assertTrue(autonomy.SAFETY["adaptive_feature_shortcuts_enabled"])
        self.assertTrue(autonomy.SAFETY["adaptive_feature_shortcuts_allowlisted_only"])
        self.assertTrue(autonomy.SAFETY["adaptive_feature_shortcuts_existing_dom_only"])
        self.assertTrue(autonomy.SAFETY["adaptive_feature_shortcuts_user_reversible"])
        self.assertTrue(autonomy.SAFETY["adaptive_screen_modules_enabled"])
        self.assertTrue(autonomy.SAFETY["adaptive_screen_modules_existing_targets_only"])
        self.assertTrue(autonomy.SAFETY["adaptive_screen_modules_user_reversible"])
        self.assertTrue(autonomy.SAFETY["adaptive_feature_priority_scoring_enabled"])
        self.assertTrue(autonomy.SAFETY["autonomous_needed_feature_selection_enabled"])
        self.assertFalse(autonomy.SAFETY["autonomous_needed_feature_runtime_generation"])
        self.assertTrue(autonomy.SAFETY["meta_neural_screen_policy_enabled"])
        self.assertTrue(autonomy.SAFETY["meta_neural_screen_policy_verified_outcomes_only"])
        self.assertTrue(autonomy.SAFETY["meta_neural_screen_policy_advisory_only"])
        self.assertTrue(autonomy.SAFETY["meta_neural_screen_policy_bias_bounded"])
        self.assertTrue(autonomy.SAFETY["verified_surface_outcome_feedback_enabled"])
        self.assertTrue(autonomy.SAFETY["verified_surface_outcome_feedback_bias_bounded"])
        self.assertTrue(autonomy.SAFETY["verified_surface_outcome_feedback_no_user_behavior_tracking"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_adapter_enabled"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_verified_outcomes_only"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_allowlisted_features_only"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_advisory_only"])
        self.assertFalse(autonomy.SAFETY["screen_policy_neural_user_behavior_tracking"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_champion_challenger_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_holdout_validation_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_challenger_must_improve"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_input_drift_hold_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_backup_rollback_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_transactional_promotion"])
        self.assertFalse(autonomy.SAFETY["screen_policy_neural_source_generation"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_enabled"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_allowlisted_modules_only"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_verified_data_only"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_market_direction_invention"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_stock_fact_invention"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_user_reversible"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_precise_location_persistence"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_user_behavior_tracking"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_module_confidence_required"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_low_confidence_revalidation_required"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_hot_evidence_confidence_required"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_region_drilldown_strings_only"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_capture_readiness_structured"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_portfolio_economics_existing_results_only"])
        self.assertTrue(autonomy.SAFETY["market_activity_dataset_freshness_weighted"])
        self.assertTrue(autonomy.SAFETY["market_activity_expired_events_excluded"])
        self.assertTrue(autonomy.SAFETY["market_activity_tracking_placeholders_excluded"])
        self.assertTrue(autonomy.SAFETY["market_activity_claim_deadline_respected"])
        self.assertTrue(autonomy.SAFETY["market_lens_filter_before_topk_required"])
        self.assertTrue(autonomy.SAFETY["market_context_adapter_enabled"])
        self.assertTrue(autonomy.SAFETY["market_context_adapter_verified_activity_only"])
        self.assertTrue(autonomy.SAFETY["market_context_adapter_freshness_gated"])
        self.assertTrue(autonomy.SAFETY["market_context_adapter_bias_bounded"])
        self.assertTrue(autonomy.SAFETY["market_context_history_hysteresis_enabled"])
        self.assertTrue(autonomy.SAFETY["market_context_history_verified_signals_only"])
        self.assertTrue(autonomy.SAFETY["market_context_stable_focus_required_before_experience_bonus"])
        self.assertTrue(autonomy.SAFETY["market_context_screen_neural_input_shape_unchanged"])
        self.assertFalse(autonomy.SAFETY["market_context_adapter_market_direction_invention"])
        self.assertTrue(autonomy.SAFETY["market_lens_verified_rows_only"])
        self.assertTrue(autonomy.SAFETY["market_lens_game_region_focus_bounded"])
        self.assertTrue(autonomy.SAFETY["market_lens_user_reversible"])
        self.assertFalse(autonomy.SAFETY["market_lens_price_direction_used"])
        self.assertEqual(5, len(autonomy.VIDEO_EXPERIENCE_MODULES))
        self.assertEqual(("Pokémon", "ONE PIECE", "NARUTO"), autonomy.MARKET_LENS_GAMES)
        self.assertTrue({
            "GUNDAM CARD GAME", "UNION ARENA", "DRAGON BALL SUPER: FUSION WORLD",
            "Disney Lorcana", "Star Wars: Unlimited", "Riftbound: League of Legends",
            "Magic: The Gathering", "Yu-Gi-Oh!", "Digimon Card Game",
        }.issubset(set(autonomy.DISCOVERED_MARKET_LENS_GAMES)))
        self.assertEqual(("KR", "JP", "US"), autonomy.MARKET_LENS_REGIONS)
        self.assertTrue(autonomy.SAFETY["autonomous_tcg_category_discovery_enabled"])
        self.assertTrue(autonomy.SAFETY["autonomous_tcg_category_registry_declarative_only"])
        self.assertTrue(autonomy.SAFETY["autonomous_tcg_category_verified_evidence_required"])
        self.assertFalse(autonomy.SAFETY["autonomous_tcg_category_profit_guarantee"])
        self.assertFalse(autonomy.SAFETY["autonomous_tcg_category_market_direction_prediction"])
        self.assertFalse(autonomy.SAFETY["autonomous_tcg_category_source_code_generation"])
        self.assertFalse(autonomy.SAFETY["autonomous_tcg_category_git_write"])
        self.assertTrue(autonomy.SAFETY["new_tcg_grading_requires_separate_calibration"])
        self.assertEqual("grading", autonomy.CATEGORY_ORDER[0])
        self.assertFalse(autonomy.SAFETY["stock_fact_invention"])
        self.assertFalse(autonomy.SAFETY["git_write"])

    def test_seven_surfaces_are_scored_from_operational_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            rows = {row["surface"]: row for row in portfolio["surfaces"]}
            self.assertEqual(set(autonomy.SURFACES), set(rows))
            self.assertEqual(["JP", "KR", "US"], rows["card_market"]["evidence"]["regions"])
            self.assertEqual(9, rows["card_release"]["evidence"]["item_count"])
            self.assertEqual(["JP", "KR", "US"], rows["card_release"]["evidence"]["regions"])
            self.assertEqual(3, rows["collab_event"]["evidence"]["collaboration_count"])
            self.assertFalse(rows["card_market"]["evidence"]["prices_invented"])
            self.assertFalse(rows["card_release"]["evidence"]["release_facts_invented"])
            self.assertFalse(rows["collab_event"]["evidence"]["event_facts_invented"])
            self.assertEqual(9, rows["purchase_availability"]["evidence"]["source_count"])
            self.assertFalse(rows["purchase_availability"]["evidence"]["stock_facts_invented"])

    def test_purchase_surface_uses_all_promoted_registry_games(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_data = json.loads((Path(__file__).resolve().parent / "tcg_game_registry.json").read_text(encoding="utf-8"))
            (root / "tcg_game_registry.json").write_text(
                json.dumps(registry_data, ensure_ascii=False), encoding="utf-8"
            )
            promoted = [
                row["canonical"] for row in registry_data["games"]
                if row["state"] in {"core", "promoted"} and row["capabilities"]["purchase"]
            ]
            sources = [
                {
                    "name": "SRC-" + str(index),
                    "region": "US",
                    "games": [game],
                    "type": "marketplace",
                    "link_status": "정상",
                    "last_checked_at": "2026-10-03T00:00:00Z",
                }
                for index, game in enumerate(promoted)
            ]
            (root / "purchase_sources.json").write_text(json.dumps({
                "updated_at": "2026-10-03T00:00:00Z", "sources": sources,
            }, ensure_ascii=False), encoding="utf-8")
            (root / "purchase_signals.json").write_text(json.dumps({
                "updated_at": "2026-10-03T00:00:00Z", "items": [],
            }), encoding="utf-8")
            row = autonomy.purchase_availability_surface(root, NOW)
            evidence = row["evidence"]
            self.assertEqual(set(promoted), set(evidence["expected_games"]))
            self.assertEqual(set(promoted), set(evidence["games"]))
            self.assertEqual(1.0, evidence["game_coverage"])
            self.assertEqual(
                len(tablet_runtime_manifest.ACTIVE_RUNTIME_FILES),
                rows["tablet_ops"]["evidence"]["present_runtime_assets"],
            )
            self.assertEqual(
                len(tablet_runtime_manifest.TABLET_CONTROL_PLANE_FILES),
                rows["tablet_ops"]["evidence"]["present_control_plane_assets"],
            )
            self.assertEqual([], rows["tablet_ops"]["evidence"]["missing_control_plane_assets"])
            self.assertFalse(rows["tablet_ops"]["evidence"]["physical_tablet_runtime_verified"])



    def test_adaptive_ui_plan_is_allowlisted_reversible_and_non_directional(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            state = autonomy.update_surface_memory(autonomy._default_state(), portfolio)
            plan = autonomy.adaptive_layout_plan(
                root, portfolio, state["surface_memory"], NOW, allow_layout=True,
                base=upstream_fixture(), state=autonomy._default_state(),
            )
            self.assertEqual(set(autonomy.CATEGORY_ORDER), set(plan["order"]))
            self.assertEqual(list(autonomy.CATEGORY_ORDER), plan["allowlisted_categories"])
            self.assertEqual(
                {key: list(value) for key, value in autonomy.FEATURE_SHORTCUT_ORDER.items()},
                plan["feature_allowlist"],
            )
            self.assertEqual(set(autonomy.FEATURE_SHORTCUT_ORDER), set(plan["feature_orders"]))
            for key, expected in autonomy.FEATURE_SHORTCUT_ORDER.items():
                self.assertEqual(set(expected), set(plan["feature_orders"][key]))
            self.assertEqual(
                "verified_priority_scoring_existing_dom_shortcuts_only",
                plan["feature_adaptation"],
            )
            self.assertEqual(set(autonomy.FEATURE_TARGETS), set(plan["feature_priorities"]))
            module = plan["screen_module_plan"]
            self.assertEqual(18, len(module["rankings"]))
            self.assertEqual(dict(autonomy.FEATURE_TARGETS), module["targets"])
            self.assertTrue(module["existing_targets_only"])
            self.assertTrue(module["user_reversible"])
            self.assertFalse(module["dom_reorder"])
            self.assertEqual(5, len(module["top_features"]))
            learning = plan["policy_learning"]
            self.assertFalse(learning["meta_neural"]["active"])
            self.assertFalse(learning["screen_neural"]["active"])
            self.assertEqual(autonomy.screen_neural.INPUT_DIM, len(learning["policy_features"]))
            self.assertEqual(0, learning["verified_outcome_feedback"]["transitions_used"])
            self.assertFalse(learning["verified_outcome_feedback"]["user_behavior_tracking"])
            market_context = learning["market_context"]
            stability = learning["market_context_stability"]
            self.assertIn(market_context["state"], {"quiet", "revalidate", "mixed_attention", "trade_attention", "release_attention", "event_attention"})
            self.assertIn(stability["stable_focus_game"], {"ALL", *autonomy.MARKET_LENS_GAMES})
            self.assertIn(stability["stable_focus_region"], {"ALL", *autonomy.MARKET_LENS_REGIONS})
            self.assertTrue(stability["verified_history_only"])
            self.assertFalse(stability["user_behavior_tracking"])
            self.assertEqual(autonomy.screen_neural.INPUT_DIM, 17)
            self.assertLessEqual(market_context["max_abs_bias"], autonomy.MAX_MARKET_CONTEXT_BIAS)
            self.assertTrue(market_context["verified_activity_only"])
            self.assertTrue(market_context["freshness_gated"])
            self.assertFalse(market_context["market_direction_inferred"])
            self.assertFalse(market_context["price_direction_used"])
            self.assertFalse(market_context["user_behavior_tracking"])
            self.assertLessEqual(
                learning["max_combined_bias"],
                autonomy.MAX_COMBINED_FEATURE_BIAS,
            )
            self.assertTrue(plan["user_override_required"])
            self.assertTrue(plan["reversible"])
            self.assertFalse(plan["source_code_rewrite"])
            self.assertFalse(plan["new_ui_feature_generation"])
            experience = plan["video_experience_plan"]
            self.assertEqual(set(autonomy.VIDEO_EXPERIENCE_MODULES), set(experience["order"]))
            self.assertEqual(list(autonomy.VIDEO_EXPERIENCE_MODULES), experience["allowlist"])
            self.assertEqual(
                {key: list(value) for key, value in autonomy.VIDEO_EXPERIENCE_MODULES.items()},
                experience["feature_dependencies"],
            )
            self.assertEqual(set(autonomy.VIDEO_EXPERIENCE_MODULES), set(experience["module_confidence"]))
            self.assertEqual(set(autonomy.VIDEO_EXPERIENCE_MODULES), set(experience["module_state"]))
            self.assertTrue(all(0.0 <= float(value) <= 1.0 for value in experience["module_confidence"].values()))
            self.assertTrue(all(value in {"verified", "revalidate"} for value in experience["module_state"].values()))
            self.assertTrue(experience["user_reversible"])
            self.assertTrue(experience["verified_data_only"])
            self.assertFalse(experience["market_direction_inferred"])
            self.assertFalse(experience["stock_fact_invented"])
            self.assertFalse(experience["precise_location_persisted"])
            self.assertFalse(experience["user_behavior_tracking"])
            lens = experience["market_lens"]
            self.assertIn(lens["focus_game"], {"ALL", *autonomy.MARKET_LENS_GAMES})
            self.assertIn(lens["focus_region"], {"ALL", *autonomy.MARKET_LENS_REGIONS})
            self.assertIn(lens["stable_focus_game"], {"ALL", *autonomy.MARKET_LENS_GAMES})
            self.assertIn(lens["stable_focus_region"], {"ALL", *autonomy.MARKET_LENS_REGIONS})
            self.assertGreaterEqual(lens["game_confirmations"], 0)
            self.assertGreaterEqual(lens["region_confirmations"], 0)
            self.assertEqual(set(lens["allowed_games"]), set(lens["game_scores"]))
            self.assertTrue(set(autonomy.CORE_MARKET_LENS_GAMES).issubset(set(lens["allowed_games"])))
            self.assertEqual(set(autonomy.MARKET_LENS_REGIONS), set(lens["region_scores"]))
            self.assertTrue(lens["verified_data_only"])
            self.assertTrue(lens["user_reversible"])
            self.assertFalse(lens["market_direction_inferred"])
            self.assertFalse(lens["price_direction_used"])
            self.assertEqual(plan["market_activity"]["dataset_freshness"], experience["dataset_freshness"])
            self.assertEqual(plan["market_activity"]["stale_datasets"], experience["stale_datasets"])
            self.assertTrue(plan["video_reference_source_level_modules_predeclared"])
            self.assertFalse(plan["market_direction_inferred"])
            self.assertFalse(plan["market_activity"]["market_direction_inferred"])
            self.assertTrue(plan["market_activity"]["dataset_freshness_weighted"])

    def test_market_context_adapter_is_freshness_gated_bounded_and_non_directional(self):
        activity = {
            "market_activity": 0.90,
            "release_activity": 0.18,
            "event_activity": 0.06,
            "dataset_freshness": {
                "market_watch": 1.0,
                "releases": 0.95,
                "promo_events": 0.90,
            },
            "stale_datasets": [],
            "market_lens": {"focus_game": "Pokémon", "focus_region": "JP"},
        }
        context = autonomy.market_context_feature_bias(activity)
        self.assertTrue(context["active"])
        self.assertEqual("trade_attention", context["state"])
        self.assertGreater(context["feature_biases"]["market-search"], 0.0)
        self.assertGreater(context["feature_biases"]["trading-catalog"], 0.0)
        self.assertLessEqual(context["max_abs_bias"], autonomy.MAX_MARKET_CONTEXT_BIAS)
        self.assertTrue(context["verified_activity_only"])
        self.assertTrue(context["freshness_gated"])
        self.assertFalse(context["market_direction_inferred"])
        self.assertFalse(context["price_direction_used"])
        self.assertFalse(context["user_behavior_tracking"])

        stale = dict(activity)
        stale["dataset_freshness"] = {
            "market_watch": 0.20,
            "releases": 0.20,
            "promo_events": 0.20,
        }
        stale["stale_datasets"] = ["market_watch", "releases", "promo_events"]
        held = autonomy.market_context_feature_bias(stale)
        self.assertFalse(held["active"])
        self.assertEqual("revalidate", held["state"])
        self.assertEqual(0.0, held["max_abs_bias"])
        self.assertTrue(all(value == 0.0 for value in held["feature_biases"].values()))

    def test_market_context_requires_repeated_verified_focus_before_stable_bonus(self):
        activity = {
            "market_activity": 0.90,
            "release_activity": 0.20,
            "event_activity": 0.10,
            "dataset_freshness": {
                "market_watch": 1.0,
                "releases": 1.0,
                "promo_events": 1.0,
            },
            "stale_datasets": [],
            "market_lens": {
                "focus_game": "Pokémon",
                "focus_region": "JP",
                "game_confidence": 0.82,
                "region_confidence": 0.76,
                "game_margin": 0.25,
                "region_margin": 0.20,
            },
        }
        current = autonomy.market_context_feature_bias(activity)
        first = autonomy.stabilized_market_context(autonomy._default_state(), current)
        self.assertEqual("ALL", first["stable_focus_game"])
        self.assertEqual("ALL", first["stable_focus_region"])
        self.assertEqual(1, first["game_confirmations"])
        self.assertEqual(1, first["region_confirmations"])
        self.assertFalse(first["active"])

        state = autonomy._default_state()
        state["history"] = [{
            "market_context": {
                "focus_game": "Pokémon",
                "focus_region": "JP",
                "game_confidence": 0.80,
                "region_confidence": 0.75,
            }
        }]
        stable = autonomy.stabilized_market_context(state, current)
        self.assertEqual("Pokémon", stable["stable_focus_game"])
        self.assertEqual("JP", stable["stable_focus_region"])
        self.assertEqual(2, stable["game_confirmations"])
        self.assertEqual(2, stable["region_confirmations"])
        self.assertTrue(stable["active"])
        self.assertFalse(stable["market_direction_inferred"])
        self.assertFalse(stable["price_direction_used"])

        changed = dict(current)
        changed["focus_game"] = "ONE PIECE"
        changed["focus_region"] = "KR"
        changed["game_confidence"] = 0.90
        changed["region_confidence"] = 0.90
        held = autonomy.stabilized_market_context(state, changed)
        self.assertEqual("ALL", held["stable_focus_game"])
        self.assertEqual("ALL", held["stable_focus_region"])
        self.assertFalse(held["active"])

    def test_market_activity_downweights_stale_data_and_excludes_expired_or_tracking_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            (root / "market_watch.json").write_text(json.dumps({
                "updated_at": "2026-06-01T00:00:00Z",
                "items": [
                    {"game": "ONE PIECE", "region": "KR", "sale_status": "거래중"},
                    {"game": "ONE PIECE", "region": "KR", "sale_status": "거래중"},
                ],
            }), encoding="utf-8")
            (root / "promo_events.json").write_text(json.dumps({
                "updated_at": "2026-10-02T00:00:00Z",
                "items": [
                    {
                        "game": "원피스 카드", "region": "KR", "lifecycle": "current",
                        "end_date": "2026-09-30", "tracking_only": False,
                    },
                    {
                        "game": "포켓몬 카드", "region": "JP", "lifecycle": "current",
                        "end_date": "2027-12-31", "tracking_only": True,
                    },
                ],
            }), encoding="utf-8")
            activity = autonomy.market_activity(root, NOW)
            self.assertEqual(0, activity["current_event_count"])
            self.assertEqual(2, activity["expired_or_tracking_events_excluded"])
            self.assertIn("market_watch", activity["stale_datasets"])
            self.assertEqual(0.0, activity["market_activity"])
            self.assertTrue(activity["dataset_freshness_weighted"])
            self.assertTrue(activity["market_lens"]["verified_data_only"])
            self.assertFalse(activity["market_lens"]["price_direction_used"])

    def test_market_activity_keeps_verified_claim_window_after_event_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            (root / "market_watch.json").write_text(json.dumps({
                "updated_at": "2026-10-03T00:00:00Z",
                "items": [],
            }), encoding="utf-8")
            (root / "releases.json").write_text(json.dumps({
                "updated_at": "2026-10-03T00:00:00Z",
                "items": [],
            }), encoding="utf-8")
            (root / "promo_events.json").write_text(json.dumps({
                "updated_at": "2026-10-03T00:00:00Z",
                "items": [
                    {
                        "game": "포켓몬 카드", "region": "JP", "lifecycle": "current",
                        "end_date": "2026-08-31", "claim_deadline": "2026-10-31",
                        "tracking_only": False,
                    },
                    {
                        "game": "원피스 카드", "region": "KR", "lifecycle": "current",
                        "end_date": "2026-09-30", "claim_deadline": "2026-09-30",
                        "tracking_only": False,
                    },
                ],
            }), encoding="utf-8")
            activity = autonomy.market_activity(root, NOW)
            self.assertEqual(1, activity["current_event_count"])
            self.assertEqual(1, activity["expired_or_tracking_events_excluded"])
            self.assertGreater(activity["market_lens"]["game_scores"]["Pokémon"], 0.0)
            self.assertFalse(activity["market_lens"]["market_direction_inferred"])

    def test_video_reference_runtime_health_fails_closed_on_missing_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            health = autonomy.ui_runtime_health(root)
            checks = {row["check_id"]: row for row in health["checks"]}
            self.assertTrue(checks["video_reference_dom_contract"]["ok"])
            self.assertTrue(checks["video_reference_runtime_contract"]["ok"])
            index = (root / "index.html").read_text(encoding="utf-8").replace('id="cameraStatus"', 'id="cameraStatusMissing"')
            (root / "index.html").write_text(index, encoding="utf-8")
            broken = autonomy.ui_runtime_health(root)
            broken_checks = {row["check_id"]: row for row in broken["checks"]}
            self.assertFalse(broken_checks["video_reference_dom_contract"]["ok"])
            self.assertGreater(broken["critical_failed"], 0)
            self.assertFalse(broken["healthy"])

    def test_verified_meta_neural_scores_bias_screen_policy_only_with_enough_samples(self):
        base = upstream_fixture()
        base["meta_neural"] = {"active": True, "sample_count": 12, "training": {"status": "META_MODEL_SAVED"}}
        base["plan"]["meta_scores"]["REFRESH_MARKET_DATA"] = 0.80
        base["plan"]["meta_scores"]["TRAIN_REPAIR_PRIORITY"] = -0.50
        bias = autonomy.neural_feature_bias(base)
        self.assertTrue(bias["active"])
        self.assertEqual(12, bias["sample_count"])
        self.assertGreater(bias["feature_biases"]["market-search"], 0.0)
        self.assertLess(bias["feature_biases"]["code-audit"], 0.0)
        self.assertLessEqual(bias["max_abs_bias"], autonomy.MAX_NEURAL_FEATURE_BIAS)
        self.assertTrue(bias["verified_outcomes_only"])
        self.assertTrue(bias["advisory_only"])

        base["meta_neural"]["sample_count"] = 2
        held = autonomy.neural_feature_bias(base)
        self.assertFalse(held["active"])
        self.assertEqual(0.0, max(abs(value) for value in held["feature_biases"].values()))

    def test_applied_screen_plan_learns_weakly_from_later_verified_surface_score(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            state = autonomy._default_state()
            state["history"] = [{
                "observed_at": "2026-10-02T23:00:00+00:00",
                "cycle": 1,
                "adaptive_applied": True,
                "top_features": ["precision-grade", "market-search"],
                "surface_scores": {
                    "card_measurement": 0.20,
                    "card_market": 0.95,
                },
            }]
            rows = {row["surface"]: row for row in portfolio["surfaces"]}
            rows["card_measurement"]["score"] = 0.40
            rows["card_market"]["score"] = 0.80
            feedback = autonomy.verified_outcome_feature_feedback(state, portfolio)
            self.assertEqual(1, feedback["transitions_used"])
            self.assertGreater(feedback["feature_biases"]["precision-grade"], 0.0)
            self.assertLess(feedback["feature_biases"]["market-search"], 0.0)
            self.assertLessEqual(feedback["max_abs_bias"], autonomy.MAX_OUTCOME_FEATURE_BIAS)
            self.assertFalse(feedback["causality_claimed"])
            self.assertFalse(feedback["user_behavior_tracking"])

    def test_dedicated_screen_neural_is_bounded_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            state = autonomy.update_surface_memory(autonomy._default_state(), portfolio)
            model = autonomy.screen_neural._default_model(NOW)
            model["sample_count"] = autonomy.screen_neural.MIN_TRAINING_ROWS
            self.assertTrue(autonomy.screen_neural.validate_model(model, now=NOW))
            plan = autonomy.adaptive_layout_plan(
                root, portfolio, state["surface_memory"], NOW, allow_layout=True,
                base=upstream_fixture(), state=autonomy._default_state(),
                screen_model=model,
                screen_training={"status": "SCREEN_NEURAL_MODEL_SAVED", "written": True},
                screen_load_status="SCREEN_NEURAL_LOADED",
            )
            screen = plan["policy_learning"]["screen_neural"]
            self.assertTrue(screen["active"])
            self.assertEqual(set(autonomy.FEATURE_TARGETS), set(screen["feature_biases"]))
            self.assertLessEqual(screen["max_abs_bias"], autonomy.screen_neural.MAX_FEATURE_BIAS)
            self.assertLessEqual(plan["policy_learning"]["max_combined_bias"], autonomy.MAX_COMBINED_FEATURE_BIAS)
            self.assertFalse(plan["policy_learning"]["user_behavior_tracking"])

    def test_screen_neural_champion_challenger_constants_are_bounded(self):
        self.assertEqual(
            autonomy.screen_neural.MIN_TRAINING_ROWS + autonomy.screen_neural.MIN_HOLDOUT_ROWS,
            autonomy.screen_neural.MIN_PROMOTION_ROWS,
        )
        self.assertLess(0.0, autonomy.screen_neural.MIN_PROMOTION_IMPROVEMENT)
        self.assertLess(autonomy.screen_neural.MIN_PROMOTION_IMPROVEMENT, 0.1)
        self.assertLess(0.0, autonomy.screen_neural.MAX_INPUT_DRIFT)
        self.assertLess(autonomy.screen_neural.MAX_INPUT_DRIFT, 1.0)
        self.assertTrue(autonomy.screen_neural.SAFETY["champion_challenger_required"])
        self.assertTrue(autonomy.screen_neural.SAFETY["holdout_validation_required"])
        self.assertTrue(autonomy.screen_neural.SAFETY["backup_rollback_required"])

    def test_missing_release_evidence_becomes_revalidation_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root, releases=False)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            rows = {row["surface"]: row for row in portfolio["surfaces"]}
            self.assertEqual(0.0, rows["card_release"]["confidence"])
            self.assertEqual("attention", rows["card_release"]["status"])
            self.assertEqual("card_release", portfolio["selected_surface"])
            cap = autonomy.steering_capability(portfolio, now=NOW)
            self.assertIsNotNone(cap)
            self.assertEqual("REQUEST_FRESHNESS_REFRESH", cap["primitive"])
            self.assertTrue(autonomy._v373().validate_capability(cap, now=NOW))

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

    def test_current_runtime_verification_is_preferred_for_card_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            (root / "V109_FINAL_VERIFICATION_REPORT.json").write_text(json.dumps({
                "checked_at": "2026-08-31T00:00:00Z",
                "ok": True,
                "policy": {
                    "automatic_ocr_predictions_train": False,
                    "user_confirmation_required": True,
                    "raw_slab_grade_learning_isolated": True,
                },
            }), encoding="utf-8")
            (root / "CURRENT_RUNTIME_VERIFICATION_REPORT.json").write_text(json.dumps({
                "engine": "current-main-test",
                "finished_at": "2026-10-02T23:30:00Z",
                "ok": True,
                "passes": [{
                    "pass": 1,
                    "ok": True,
                    "checks": [
                        {"name": "active_tablet_runtime", "ok": True, "optional": False},
                        {"name": "card_core_static_regressions", "ok": True, "optional": False},
                        {"name": "current_runtime_regressions", "ok": True, "optional": False},
                    ],
                }],
            }), encoding="utf-8")
            row = autonomy.card_measurement_surface(root, NOW)
            ev = row["evidence"]
            self.assertEqual("CURRENT_RUNTIME_VERIFICATION_REPORT.json", ev["verification_report"])
            self.assertTrue(ev["current_runtime_verification_ok"])
            self.assertTrue(ev["current_runtime_contract_ok"])
            self.assertEqual([], ev["current_runtime_missing_checks"])
            self.assertGreaterEqual(row["confidence"], 0.90)

    def test_incomplete_current_runtime_report_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root)
            (root / "V109_FINAL_VERIFICATION_REPORT.json").write_text(json.dumps({
                "checked_at": "2026-10-02T00:00:00Z",
                "ok": True,
                "policy": {
                    "automatic_ocr_predictions_train": False,
                    "user_confirmation_required": True,
                    "raw_slab_grade_learning_isolated": True,
                },
            }), encoding="utf-8")
            (root / "CURRENT_RUNTIME_VERIFICATION_REPORT.json").write_text(json.dumps({
                "engine": "current-main-test",
                "finished_at": "2026-10-02T23:30:00Z",
                "ok": True,
                "passes": [{
                    "pass": 1,
                    "ok": True,
                    "checks": [
                        {"name": "active_tablet_runtime", "ok": True, "optional": False},
                        {"name": "card_core_static_regressions", "ok": True, "optional": False},
                    ],
                }],
            }), encoding="utf-8")
            row = autonomy.card_measurement_surface(root, NOW)
            ev = row["evidence"]
            self.assertFalse(ev["current_runtime_verification_ok"])
            self.assertFalse(ev["current_runtime_contract_ok"])
            self.assertIn("current_runtime_regressions", ev["current_runtime_missing_checks"])
            self.assertEqual("V109_FINAL_VERIFICATION_REPORT.json", ev["verification_report"])
            self.assertTrue(ev["verification_ok"])

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

    def test_needed_feature_selection_is_specific_but_never_runtime_generated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_assets(root, verification=False)
            portfolio = autonomy.surface_portfolio(root, upstream_fixture(), NOW)
            state = autonomy.update_surface_memory(autonomy._default_state(), portfolio)
            state2 = autonomy.update_surface_memory(state, portfolio)
            candidates = autonomy.needed_feature_candidates(portfolio, state2["surface_memory"])
            grading = next(row for row in candidates if row["surface"] == "card_measurement")
            self.assertEqual("grading_evidence_diagnostics", grading["feature_id"])
            self.assertEqual("protected_pr_candidate", grading["stage"])
            self.assertEqual("protected_pr_ci_only", grading["implementation_mode"])
            self.assertFalse(grading["auto_execute"])
            self.assertFalse(grading["runtime_generate_source"])
            self.assertFalse(grading["auto_rewrite_source"])
            self.assertFalse(grading["git_write"])
            self.assertFalse(grading["market_direction_inferred"])

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
