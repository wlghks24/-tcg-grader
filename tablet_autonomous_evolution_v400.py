#!/usr/bin/env python3
"""V400 domain-aware self-evolution supervisor for Tablet GPT.

V400 preserves V399/V398 as mandatory upstream governors and adds explicit,
evidence-bounded autonomy across seven user-facing surfaces:

- tablet UI/PWA/runtime composition,
- card measurement / grading verification,
- KR/JP/US market-price freshness and source health,
- official card/product issuance and release coverage,
- collaboration / promo / event coverage.

The controller never converts missing evidence into invented confidence. A
surface with stale or absent verification is prioritized for revalidation
rather than treated as successful. Runtime self-extension remains restricted
to canonical V373 declarative primitives; source-level feature work remains a
non-executable protected-PR/CI candidate with domain-specific validation.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v399 as v399
import screen_policy_neural_v401 as screen_neural
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v400"
CORE_CONTROLLER_VERSION = "v399"

STATE_PATH = ROOT / ".tablet_autonomy_v400_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v400_report.json"
SURFACE_CANDIDATE_PATH = ROOT / "tablet_autonomy_surface_feature_candidates_v400.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v400.lock"

MAX_STATE_BYTES = 1_500_000
MAX_HISTORY = 192
MAX_SURFACE_MEMORY = 16
PROTECTED_PR_RECURRENCE = 2
ROLLBACK_DROP = 0.06
VERIFIED_GAIN = 0.02
MAX_ACTIVE_CYCLES = 3
MIN_STEERING_URGENCY = 0.30
MAX_NEURAL_FEATURE_BIAS = 0.06
MAX_OUTCOME_FEATURE_BIAS = 0.04
MAX_COMBINED_FEATURE_BIAS = 0.08
MAX_MARKET_CONTEXT_BIAS = 0.04
MAX_POLICY_TRANSITIONS = 24

SURFACES = ("ui", "card_measurement", "card_market", "card_release", "collab_event", "purchase_availability", "tablet_ops")
CATEGORY_ORDER = ("grading", "market", "box", "news", "purchase", "learning", "tablet", "code")
FEATURE_SHORTCUT_ORDER = {
    "grading": ("auto-grade", "manual-photo", "precision-grade"),
    "market": ("market-search", "grading-economics", "trading-catalog"),
    "box": ("box-knowledge", "box-hit-analysis"),
    "news": ("release-info", "promo-event-info"),
    "purchase": ("purchase-finder", "purchase-distance"),
    "learning": ("card-ocr", "verified-grade", "learning-status"),
    "tablet": ("tablet-manager",),
    "code": ("code-audit", "code-validation"),
}
FEATURE_TARGETS = {
    "auto-grade": "simpleGradeV32",
    "manual-photo": "gradeStart",
    "precision-grade": "precisionHub",
    "market-search": "market12section",
    "grading-economics": "gradingEconomics",
    "trading-catalog": "tradingCatalogSection",
    "box-knowledge": "box12section",
    "box-hit-analysis": "v14section",
    "release-info": "releaseBoard",
    "promo-event-info": "releaseBoard",
    "purchase-finder": "releaseBoard",
    "purchase-distance": "releaseBoard",
    "card-ocr": "simpleGradeV32",
    "verified-grade": "v30validation",
    "learning-status": "v31testdashboard",
    "tablet-manager": "tabletManagerHub",
    "code-audit": "audit15",
    "code-validation": "v31testdashboard",
}
FEATURE_PANELS = {
    "release-info": "releasePanel",
    "promo-event-info": "promoPanel",
    "purchase-finder": "purchasePanel",
    "purchase-distance": "purchasePanel",
}
FEATURE_GAP_RECIPES = {
    "ui": "adaptive_ui_health_inspector",
    "card_measurement": "grading_evidence_diagnostics",
    "card_market": "market_source_freshness_inspector",
    "card_release": "release_verification_queue",
    "collab_event": "event_crosscheck_queue",
    "purchase_availability": "purchase_confirmation_queue",
    "tablet_ops": "tablet_self_repair_console",
}
VIDEO_EXPERIENCE_MODULES = {
    "home-market-pulse": ("market-search", "release-info", "promo-event-info", "purchase-finder"),
    "capture-quality-gate": ("auto-grade", "precision-grade", "card-ocr"),
    "purchase-split-view": ("purchase-distance", "purchase-finder", "release-info"),
    "hot-card-box-ranking": ("market-search", "box-hit-analysis", "trading-catalog"),
    "portfolio-summary": ("grading-economics", "verified-grade", "trading-catalog", "learning-status"),
}
MARKET_LENS_GAMES = ("Pokémon", "ONE PIECE", "NARUTO")
MARKET_LENS_REGIONS = ("KR", "JP", "US")
FEATURE_SURFACE = {
    "auto-grade": "card_measurement",
    "manual-photo": "card_measurement",
    "precision-grade": "card_measurement",
    "market-search": "card_market",
    "grading-economics": "card_market",
    "trading-catalog": "card_market",
    "box-knowledge": "card_release",
    "box-hit-analysis": "card_market",
    "release-info": "card_release",
    "promo-event-info": "collab_event",
    "purchase-finder": "purchase_availability",
    "purchase-distance": "purchase_availability",
    "card-ocr": "card_measurement",
    "verified-grade": "card_measurement",
    "learning-status": "card_measurement",
    "tablet-manager": "tablet_ops",
    "code-audit": "tablet_ops",
    "code-validation": "tablet_ops",
}
META_ACTION_FEATURE_WEIGHTS = {
    "TRAIN_QUERY_STRATEGY": {"market-search": 1.0, "card-ocr": 0.45, "trading-catalog": 0.35},
    "TRAIN_JOB_STRATEGY": {"learning-status": 0.90, "tablet-manager": 0.55, "code-validation": 0.40},
    "TRAIN_REPAIR_PRIORITY": {"code-audit": 1.0, "code-validation": 0.80, "tablet-manager": 0.55},
    "REFRESH_MARKET_DATA": {"market-search": 1.0, "trading-catalog": 0.80, "grading-economics": 0.45},
    "EXPAND_MARKET_COVERAGE": {"purchase-finder": 1.0, "market-search": 0.75, "purchase-distance": 0.55},
    "RECHECK_DEGRADED_SOURCES": {"code-validation": 0.70, "market-search": 0.65, "purchase-finder": 0.45},
}
MARKET_CONTEXT_FEATURE_WEIGHTS = {
    "trade_attention": {
        "market-search": 1.00, "trading-catalog": 0.85,
        "grading-economics": 0.55, "box-hit-analysis": 0.45,
    },
    "release_attention": {
        "release-info": 1.00, "box-knowledge": 0.75,
        "purchase-finder": 0.65, "box-hit-analysis": 0.45,
    },
    "event_attention": {
        "promo-event-info": 1.00, "purchase-finder": 0.75,
        "release-info": 0.50, "purchase-distance": 0.35,
    },
}

_HOLD_STATUSES = set(getattr(v399, "_HOLD_STATUSES", set())) | {
    "V400_STATE_CORRUPTION_HOLD",
    "V400_CONCURRENT_AUTONOMY_HOLD",
    "V400_UPSTREAM_HOLD",
    "V400_CAPABILITY_CORRUPTION_HOLD",
    "V400_CAPABILITY_WRITE_HOLD",
    "V400_CAPABILITY_ROLLBACK_HOLD",
    "V400_STATE_COMMIT_HOLD",
}

SAFETY = dict(v399.SAFETY)
SAFETY.update({
    "ui_card_measurement_market_event_governance_enabled": True,
    "ui_card_measurement_market_release_event_governance_enabled": True,
    "surface_evidence_only_required": True,
    "missing_surface_evidence_triggers_revalidation": True,
    "current_runtime_verification_preferred": True,
    "historical_v109_audit_fallback_only": True,
    "surface_goal_self_selection_enabled": True,
    "surface_verified_canary_learning_enabled": True,
    "surface_owned_capability_auto_rollback": True,
    "surface_runtime_self_extension_allowlisted_only": True,
    "surface_source_feature_candidates_non_executable": True,
    "surface_source_feature_protected_pr_ci_required": True,
    "card_measurement_grade_invention": False,
    "card_market_price_invention": False,
    "card_release_fact_invention": False,
    "event_fact_invention": False,
    "market_direction_inferred": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "runtime_ui_source_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "v399_gate_cannot_be_bypassed": True,
    "v398_gate_cannot_be_bypassed": True,
    "purchase_availability_surface_enabled": True,
    "tablet_ops_surface_enabled": True,
    "adaptive_ui_composition_enabled": True,
    "adaptive_ui_allowlisted_categories_only": True,
    "adaptive_ui_user_override_required": True,
    "adaptive_ui_reversible": True,
    "adaptive_ui_market_activity_non_directional_only": True,
    "adaptive_feature_shortcuts_enabled": True,
    "adaptive_feature_shortcuts_allowlisted_only": True,
    "adaptive_feature_shortcuts_existing_dom_only": True,
    "adaptive_feature_shortcuts_user_reversible": True,
    "adaptive_screen_modules_enabled": True,
    "adaptive_screen_modules_existing_targets_only": True,
    "adaptive_screen_modules_user_reversible": True,
    "adaptive_feature_priority_scoring_enabled": True,
    "autonomous_needed_feature_selection_enabled": True,
    "autonomous_needed_feature_runtime_generation": False,
    "meta_neural_screen_policy_enabled": True,
    "meta_neural_screen_policy_verified_outcomes_only": True,
    "meta_neural_screen_policy_advisory_only": True,
    "meta_neural_screen_policy_bias_bounded": True,
    "verified_surface_outcome_feedback_enabled": True,
    "verified_surface_outcome_feedback_bias_bounded": True,
    "verified_surface_outcome_feedback_no_user_behavior_tracking": True,
    "screen_policy_learning_fail_closed": True,
    "screen_policy_neural_adapter_enabled": True,
    "screen_policy_neural_verified_outcomes_only": True,
    "screen_policy_neural_allowlisted_features_only": True,
    "screen_policy_neural_advisory_only": True,
    "screen_policy_neural_bias_bounded": True,
    "screen_policy_neural_user_behavior_tracking": False,
    "screen_policy_neural_corruption_disables_adapter": True,
    "screen_policy_neural_champion_challenger_required": True,
    "screen_policy_neural_holdout_validation_required": True,
    "screen_policy_neural_challenger_must_improve": True,
    "screen_policy_neural_input_drift_hold_required": True,
    "screen_policy_neural_backup_rollback_required": True,
    "screen_policy_neural_transactional_promotion": True,
    "screen_policy_neural_source_generation": False,
    "video_reference_experience_enabled": True,
    "video_reference_experience_allowlisted_modules_only": True,
    "video_reference_experience_verified_data_only": True,
    "video_reference_experience_market_direction_invention": False,
    "video_reference_experience_stock_fact_invention": False,
    "video_reference_experience_user_reversible": True,
    "video_reference_experience_precise_location_persistence": False,
    "video_reference_experience_user_behavior_tracking": False,
    "video_reference_experience_module_confidence_required": True,
    "video_reference_experience_low_confidence_revalidation_required": True,
    "video_reference_experience_hot_evidence_confidence_required": True,
    "video_reference_experience_region_drilldown_strings_only": True,
    "video_reference_experience_capture_readiness_structured": True,
    "video_reference_experience_portfolio_economics_existing_results_only": True,
    "market_activity_dataset_freshness_weighted": True,
    "market_activity_expired_events_excluded": True,
    "market_activity_tracking_placeholders_excluded": True,
    "market_activity_claim_deadline_respected": True,
    "market_lens_filter_before_topk_required": True,
    "market_context_adapter_enabled": True,
    "market_context_adapter_verified_activity_only": True,
    "market_context_adapter_freshness_gated": True,
    "market_context_adapter_bias_bounded": True,
    "market_context_adapter_market_direction_invention": False,
    "market_lens_verified_rows_only": True,
    "market_lens_game_region_focus_bounded": True,
    "market_lens_user_reversible": True,
    "market_lens_price_direction_used": False,
    "stock_fact_invention": False,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _parse_time(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _age_days(value: Any, now: datetime) -> float | None:
    stamp = _parse_time(value)
    if stamp is None:
        return None
    return max(0.0, (now - stamp).total_seconds() / 86400.0)


def _freshness_score(age_days: float | None) -> float:
    if age_days is None:
        return 0.0
    if age_days <= 2:
        return 1.0
    if age_days <= 7:
        return 0.80
    if age_days <= 14:
        return 0.60
    if age_days <= 30:
        return 0.35
    if age_days <= 60:
        return 0.15
    return 0.0


def _default_memory_row() -> dict[str, Any]:
    return {
        "observations": 0,
        "score_ewma": 0.5,
        "confidence_ewma": 0.0,
        "consecutive_attention": 0,
        "last_status": "unknown",
        "last_seen_cycle": 0,
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "surface_memory": {},
        "active": None,
        "history": [],
    }


def _valid_memory_row(row: Any) -> bool:
    if not isinstance(row, dict) or set(row) != set(_default_memory_row()):
        return False
    for key in ("observations", "consecutive_attention", "last_seen_cycle"):
        if not isinstance(row[key], int) or isinstance(row[key], bool) or row[key] < 0:
            return False
    for key in ("score_ewma", "confidence_ewma"):
        value = _finite(row[key])
        if value is None or not 0.0 <= value <= 1.0:
            return False
    return row["last_status"] in {"healthy", "observe", "attention", "unknown"}


def _valid_active(row: Any) -> bool:
    if row is None:
        return True
    if not isinstance(row, dict) or set(row) != {
        "id", "surface", "primitive", "baseline_score", "activated_cycle",
    }:
        return False
    if not isinstance(row["id"], str) or not row["id"] or len(row["id"]) > 200:
        return False
    if row["surface"] not in SURFACES:
        return False
    if not isinstance(row["primitive"], str) or not row["primitive"]:
        return False
    score = _finite(row["baseline_score"])
    if score is None or not 0.0 <= score <= 1.0:
        return False
    return isinstance(row["activated_cycle"], int) and not isinstance(row["activated_cycle"], bool) and row["activated_cycle"] >= 0


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "schema_version", "controller_version", "cycle", "surface_memory", "active", "history",
    }:
        return False
    if value["schema_version"] != 1 or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["cycle"], int) or isinstance(value["cycle"], bool) or value["cycle"] < 0:
        return False
    memory = value["surface_memory"]
    if not isinstance(memory, dict) or len(memory) > MAX_SURFACE_MEMORY:
        return False
    for surface, row in memory.items():
        if surface not in SURFACES or not _valid_memory_row(row):
            return False
    if not _valid_active(value["active"]):
        return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V400_STATE_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_STATE_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": type(exc).__name__,
        }
    if not _valid_state(value):
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": "V400_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, *, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V400_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V400_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v400-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V400_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V400_STATE_SAVED", "written": True}


def _read_json(root: Path, relative: str, *, max_bytes: int = 20_000_000) -> dict[str, Any] | None:
    path = root / relative
    try:
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _file_ok(root: Path, relative: str) -> bool:
    path = root / relative
    try:
        return path.is_file() and not path.is_symlink() and path.stat().st_size > 0
    except OSError:
        return False


def _healthy_link(value: Any) -> bool:
    text = str(value or "")
    return bool(text) and ("정상" in text or "200" in text) and not any(token in text for token in ("404", "410", "깨진", "실패"))


def _surface_row(surface: str, score: float, confidence: float, evidence: dict[str, Any]) -> dict[str, Any]:
    score = _clamp(score)
    confidence = _clamp(confidence)
    urgency = _clamp(max(1.0 - score, 0.85 * (1.0 - confidence)))
    status = "attention" if urgency >= 0.45 else "observe" if urgency >= 0.20 else "healthy"
    return {
        "surface": surface,
        "score": round(score, 6),
        "confidence": round(confidence, 6),
        "urgency": round(urgency, 6),
        "status": status,
        "evidence": evidence,
        "market_direction_inferred": False,
        "invented_fact": False,
    }


def _read_text(root: Path, relative: str, *, max_bytes: int = 3_000_000) -> str:
    path = root / relative
    try:
        if not path.is_file() or path.is_symlink():
            return ""
        return safe_read_text(path, max_bytes=max_bytes)
    except (OSError, UnicodeError, ValueError, TypeError):
        return ""


def ui_runtime_health(root: Path) -> dict[str, Any]:
    index = _read_text(root, "index.html")
    css = _read_text(root, "tablet_autonomy_dashboard_v400.css")
    js = _read_text(root, "tablet_autonomy_dashboard_v400.js")
    sw = _read_text(root, "sw.js")
    updater = _read_text(root, "tcg_updater.py")
    manifest = _read_text(root, "tablet_runtime_manifest.py")
    main = _read_text(root, "main")
    category_identity_ok = (
        all(f'data-category-key="{key}"' in index for key in CATEGORY_ORDER)
        and "CATEGORY_KEYS" in js
        and '"grading"' in js
    )
    feature_keys = tuple(
        feature
        for category in CATEGORY_ORDER
        for feature in FEATURE_SHORTCUT_ORDER[category]
    )
    feature_identity_ok = (
        all(f'data-feature-key="{key}"' in index for key in feature_keys)
        and "FEATURE_KEYS" in js
        and "applyAdaptiveFeatures" in js
        and "restoreOriginalFeatures" in js
    )
    target_identity_ok = all(
        f'id="{target}"' in index
        for target in sorted(set(FEATURE_TARGETS.values()))
    )
    target_binding_ok = all(
        f'class="feature-shortcut" href="#{FEATURE_TARGETS[key]}" data-feature-key="{key}"' in index
        for key in feature_keys
    )
    module_runtime_ok = (
        "FEATURE_TARGETS" in js
        and "applyAdaptiveModules" in js
        and "restoreAdaptiveModules" in js
    )
    video_dom_ids = (
        "purchasePanel", "purchaseNearby", "purchaseRegionGrid",
        "cameraStatus", "glare", "agmRawPrice",
    )
    video_dom_ok = all(f'id="{target}"' in index for target in video_dom_ids)
    video_runtime_ok = all(token in js for token in (
        "EXPERIENCE_KEYS",
        "videoExperienceV403",
        "validExperiencePlan",
        "applyExperienceOrder",
        "restoreExperienceOrder",
        "market_watch.json",
        "market_prices.json",
        "releases.json",
        "promo_events.json",
        "MutationObserver",
        "PURCHASE_REGION_KEY",
        "REGION_SUBREGIONS",
        "purchaseVideoSubregion",
        "videoCaptureReadiness",
        "economicsValue",
        "video-hot-confidence",
        "module_confidence",
        "module_state",
    )) and all(token in css for token in (
        "V407 video-reference adaptive experience",
        "V404 video-reference refinement",
        "video-experience-evidence",
    ))
    checks = [
        ("dashboard_js_file", bool(js), True),
        ("dashboard_css_file", bool(css), True),
        ("index_dashboard_css", "tablet_autonomy_dashboard_v400.css" in index, True),
        ("index_dashboard_js", "tablet_autonomy_dashboard_v400.js" in index, True),
        ("dashboard_report_binding", "tablet_autonomy_v400_report.json" in js, True),
        ("adaptive_category_identity_contract", category_identity_ok, True),
        ("adaptive_feature_identity_contract", feature_identity_ok, True),
        ("adaptive_target_identity_contract", target_identity_ok, True),
        ("adaptive_target_binding_contract", target_binding_ok, True),
        ("adaptive_module_runtime_contract", module_runtime_ok, True),
        ("video_reference_dom_contract", video_dom_ok, True),
        ("video_reference_runtime_contract", video_runtime_ok, True),
        ("dashboard_accessibility", "aria-live" in js and "prefers-reduced-motion" in css, False),
        ("pwa_dashboard_assets", "tablet_autonomy_dashboard_v400.js" in sw and "tablet_autonomy_dashboard_v400.css" in sw, True),
        ("static_report_exposure", "tablet_autonomy_v400_report.json" in updater, True),
        ("runtime_manifest_controller", (
            "tablet_autonomous_evolution_v400.py" in manifest
            and "screen_policy_neural_v401.py" in manifest
        ), True),
        ("runtime_manifest_dashboard", "tablet_autonomy_dashboard_v400.js" in manifest and "tablet_autonomy_dashboard_v400.css" in manifest, True),
        ("main_v400_route", "tablet_autonomous_evolution_v400.py --domain tablet_gpt" in main, True),
        ("viewport_contract", 'name="viewport"' in index, False),
        ("tablet_manager_anchor", 'id="tabletManagerHub"' in index, False),
    ]
    rows = [
        {"check_id": check_id, "ok": bool(ok), "critical": bool(critical)}
        for check_id, ok, critical in checks
    ]
    passed = sum(1 for row in rows if row["ok"])
    critical_failed = sum(1 for row in rows if not row["ok"] and row["critical"])
    return {
        "score": round(passed / max(1, len(rows)), 6),
        "passed": passed,
        "total": len(rows),
        "failed": len(rows) - passed,
        "critical_failed": critical_failed,
        "checks": rows,
        "healthy": critical_failed == 0,
    }


def ui_surface(root: Path) -> dict[str, Any]:
    health = ui_runtime_health(root)
    score = float(health["score"])
    confidence = 1.0 if int(health["total"]) > 0 else 0.0
    if int(health["critical_failed"]) > 0:
        score = min(score, 0.45)
    return _surface_row("ui", score, confidence, {
        "source": "v400_ui_runtime_health",
        "passed": int(health["passed"]),
        "total": int(health["total"]),
        "critical_failed": int(health["critical_failed"]),
        "healthy": bool(health["healthy"]),
    })


def card_measurement_surface(root: Path, now: datetime) -> dict[str, Any]:
    required = [
        "grading_vision_engine.js",
        "grading_accuracy_v99.js",
        "grading_accuracy_v99.py",
        "card_identity_recognition.js",
        "card_identity_recognition.py",
        "image_quality_guard.js",
        "auto_validation_flow.js",
        "grade_market_flow.js",
    ]
    present = [name for name in required if _file_ok(root, name)]
    asset_score = len(present) / len(required)

    # CURRENT_RUNTIME_VERIFICATION_REPORT.json is the current-main/device evidence
    # produced by verify_current_runtime.py. V109 is historical audit evidence only
    # and is kept as a conservative fallback when no complete current report exists.
    current = _read_json(root, "CURRENT_RUNTIME_VERIFICATION_REPORT.json", max_bytes=5_000_000) or {}
    current_age = _age_days(
        current.get("finished_at") or current.get("updated_at") or current.get("started_at"),
        now,
    )
    current_freshness = _freshness_score(current_age)
    required_current_checks = {
        "active_tablet_runtime",
        "card_core_static_regressions",
        "current_runtime_regressions",
    }
    passed_current_checks: set[str] = set()
    passes = current.get("passes") if isinstance(current.get("passes"), list) else []
    for pass_row in passes:
        if not isinstance(pass_row, dict) or pass_row.get("ok") is not True:
            continue
        checks = pass_row.get("checks") if isinstance(pass_row.get("checks"), list) else []
        for check in checks:
            if not isinstance(check, dict) or check.get("ok") is not True:
                continue
            name = str(check.get("name") or "")
            if name:
                passed_current_checks.add(name)
    current_contract = required_current_checks.issubset(passed_current_checks)
    current_ok = (
        current.get("ok") is True
        and current_contract
        and current_freshness > 0.0
    )

    legacy = _read_json(root, "V109_FINAL_VERIFICATION_REPORT.json", max_bytes=2_000_000) or {}
    legacy_age = _age_days(legacy.get("checked_at"), now)
    legacy_freshness = _freshness_score(legacy_age)
    policy = legacy.get("policy") if isinstance(legacy.get("policy"), dict) else {}
    legacy_policy_contract = (
        policy.get("automatic_ocr_predictions_train") is False
        and policy.get("user_confirmation_required") is True
        and policy.get("raw_slab_grade_learning_isolated") is True
    )
    legacy_ok = legacy.get("ok") is True and legacy_policy_contract

    if current_ok:
        verification_source = "CURRENT_RUNTIME_VERIFICATION_REPORT.json"
        verification_ok = True
        verification_freshness = current_freshness
        verification_age = current_age
    elif legacy_ok:
        verification_source = "V109_FINAL_VERIFICATION_REPORT.json"
        verification_ok = True
        verification_freshness = legacy_freshness
        verification_age = legacy_age
    else:
        verification_source = None
        verification_ok = False
        verification_freshness = 0.0
        verification_age = None

    verification_confidence = (
        0.35 + 0.65 * verification_freshness
        if verification_ok
        else 0.0
    )
    confidence = min(asset_score, verification_confidence)
    score = 0.72 * asset_score + 0.28 * (1.0 if verification_ok else 0.0)
    return _surface_row("card_measurement", score, confidence, {
        "required_assets": len(required),
        "present_assets": len(present),
        "verification_report": verification_source,
        "verification_ok": verification_ok,
        "verification_age_days": round(verification_age, 3) if verification_age is not None else None,
        "verification_freshness": round(verification_freshness, 6),
        "current_report_present": bool(current),
        "current_runtime_verification_ok": current_ok,
        "current_runtime_contract_ok": current_contract,
        "current_runtime_required_checks": sorted(required_current_checks),
        "current_runtime_missing_checks": sorted(required_current_checks - passed_current_checks),
        "historical_v109_present": bool(legacy),
        "historical_v109_policy_ok": legacy_policy_contract,
        "historical_v109_audit_fallback_only": True,
        "automatic_unverified_training": False,
    })


def card_market_surface(root: Path, now: datetime) -> dict[str, Any]:
    payload = _read_json(root, "market_prices.json") or {}
    entries = payload.get("entries") if isinstance(payload.get("entries"), dict) else {}
    age = _age_days(payload.get("updated_at"), now)
    freshness = _freshness_score(age)
    link_rows = []
    source_fresh = []
    regions = set()
    for key, row in list(entries.items())[:5000]:
        if not isinstance(row, dict):
            continue
        region = str(key).split("|", 1)[0]
        if region in {"KR", "JP", "US"}:
            regions.add(region)
        link_rows.append(_healthy_link(row.get("link_status")))
        source_age = _age_days(row.get("source_date"), now)
        if source_age is not None:
            source_fresh.append(source_age <= 30.0)
    link_health = sum(link_rows) / len(link_rows) if link_rows else 0.0
    source_freshness = sum(source_fresh) / len(source_fresh) if source_fresh else 0.0
    coverage = len(regions) / 3.0
    score = 0.34 * freshness + 0.28 * link_health + 0.23 * source_freshness + 0.15 * coverage
    confidence = min(1.0, len(entries) / 12.0) * (0.55 + 0.45 * coverage)
    return _surface_row("card_market", score, confidence, {
        "source": "market_prices.json",
        "entry_count": len(entries),
        "updated_age_days": round(age, 3) if age is not None else None,
        "freshness": round(freshness, 6),
        "healthy_link_ratio": round(link_health, 6),
        "source_within_30d_ratio": round(source_freshness, 6),
        "regions": sorted(regions),
        "region_coverage": round(coverage, 6),
        "prices_invented": False,
    })


def card_release_surface(root: Path, now: datetime) -> dict[str, Any]:
    payload = _read_json(root, "releases.json") or {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    age = _age_days(payload.get("updated_at"), now)
    freshness = _freshness_score(age)
    links: list[bool] = []
    verified_recent: list[bool] = []
    release_precision: list[bool] = []
    official_rows: list[bool] = []
    regions = set()
    game_regions = set()
    games = set()

    def game_key(value: Any) -> str | None:
        raw = str(value or "").upper()
        if "POK" in raw or "포켓몬" in raw:
            return "POKEMON"
        if "ONE PIECE" in raw or "원피스" in raw:
            return "ONE_PIECE"
        if "NARUTO" in raw or "나루토" in raw:
            return "NARUTO"
        return None

    for item in items[:5000]:
        if not isinstance(item, dict):
            continue
        region = str(item.get("region") or "").upper()
        game = game_key(item.get("game"))
        if region in {"KR", "JP", "US"}:
            regions.add(region)
            if game:
                game_regions.add((game, region))
        if game:
            games.add(game)
        links.append(_healthy_link(item.get("link_status")))
        verified_age = _age_days(item.get("last_verified_at") or item.get("link_checked_at"), now)
        if verified_age is not None:
            verified_recent.append(verified_age <= 30.0)
        release_precision.append(bool(item.get("release_date") or item.get("release_window")))
        status = str(item.get("status") or "").lower()
        source = str(item.get("source") or "")
        official_rows.append(
            source.startswith("https://")
            and bool(status)
            and any(token in status for token in ("공식", "official", "출시", "release"))
        )

    link_health = sum(links) / len(links) if links else 0.0
    verified_ratio = sum(verified_recent) / len(verified_recent) if verified_recent else 0.0
    precision_ratio = sum(release_precision) / len(release_precision) if release_precision else 0.0
    official_ratio = sum(official_rows) / len(official_rows) if official_rows else 0.0
    region_coverage = len(regions) / 3.0
    game_coverage = len(games & {"POKEMON", "ONE_PIECE", "NARUTO"}) / 3.0
    pair_coverage = min(1.0, len(game_regions) / 9.0)
    coverage = 0.35 * region_coverage + 0.25 * game_coverage + 0.40 * pair_coverage
    score = (
        0.22 * freshness
        + 0.20 * link_health
        + 0.20 * verified_ratio
        + 0.15 * precision_ratio
        + 0.08 * official_ratio
        + 0.15 * coverage
    )
    confidence = min(1.0, len(items) / 9.0) * (0.45 + 0.55 * coverage)
    return _surface_row("card_release", score, confidence, {
        "source": "releases.json",
        "item_count": len(items),
        "updated_age_days": round(age, 3) if age is not None else None,
        "freshness": round(freshness, 6),
        "healthy_link_ratio": round(link_health, 6),
        "verified_within_30d_ratio": round(verified_ratio, 6),
        "release_date_or_window_ratio": round(precision_ratio, 6),
        "official_status_ratio": round(official_ratio, 6),
        "regions": sorted(regions),
        "games": sorted(games),
        "game_region_pair_coverage": round(pair_coverage, 6),
        "release_facts_invented": False,
    })


def collab_event_surface(root: Path, now: datetime) -> dict[str, Any]:
    payload = _read_json(root, "promo_events.json") or {}
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    coverage_row = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
    age = _age_days(payload.get("updated_at"), now)
    freshness = _freshness_score(age)
    official = []
    links = []
    collaborations = 0
    regions = set()
    for item in items[:5000]:
        if not isinstance(item, dict):
            continue
        region = str(item.get("region") or "")
        if region in {"KR", "JP", "US"}:
            regions.add(region)
        if str(item.get("category") or "") == "collaboration":
            collaborations += 1
        official.append(str(item.get("source_grade") or "") in {"official", "official-social", "cross"})
        links.append(_healthy_link(item.get("link_status")))
    official_ratio = sum(official) / len(official) if official else 0.0
    link_health = sum(links) / len(links) if links else 0.0
    expected = max(1, int(coverage_row.get("expected_game_region_pairs") or 9))
    watched = _clamp(int(coverage_row.get("watched_game_region_pairs") or 0) / expected)
    covered = _clamp(int(coverage_row.get("covered_game_region_pairs") or 0) / expected)
    movie = _clamp(int(coverage_row.get("movie_game_region_pairs") or 0) / expected)
    coverage = 0.45 * watched + 0.40 * covered + 0.15 * movie
    score = 0.28 * freshness + 0.25 * link_health + 0.22 * official_ratio + 0.25 * coverage
    confidence = min(1.0, len(items) / 9.0) * (0.45 + 0.55 * watched)
    return _surface_row("collab_event", score, confidence, {
        "source": "promo_events.json",
        "item_count": len(items),
        "collaboration_count": collaborations,
        "updated_age_days": round(age, 3) if age is not None else None,
        "freshness": round(freshness, 6),
        "official_or_cross_ratio": round(official_ratio, 6),
        "healthy_link_ratio": round(link_health, 6),
        "watched_game_region_ratio": round(watched, 6),
        "covered_game_region_ratio": round(covered, 6),
        "movie_game_region_ratio": round(movie, 6),
        "regions": sorted(regions),
        "event_facts_invented": False,
    })



def purchase_availability_surface(root: Path, now: datetime) -> dict[str, Any]:
    payload = _read_json(root, "purchase_sources.json") or {}
    sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
    signals = _read_json(root, "purchase_signals.json") or {}
    age = _age_days(payload.get("updated_at"), now)
    freshness = _freshness_score(age)
    link_rows: list[bool] = []
    regions = set()
    games = set()
    channel_types = set()
    checked_recent: list[bool] = []
    for row in sources[:5000]:
        if not isinstance(row, dict):
            continue
        region = str(row.get("region") or "").upper()
        if region in {"KR", "JP", "US"}:
            regions.add(region)
        for game in row.get("games") if isinstance(row.get("games"), list) else []:
            raw = str(game or "").upper()
            if "POK" in raw or "포켓몬" in raw:
                games.add("POKEMON")
            elif "ONE PIECE" in raw or "원피스" in raw:
                games.add("ONE_PIECE")
            elif "NARUTO" in raw or "나루토" in raw:
                games.add("NARUTO")
        channel_types.add(str(row.get("type") or "unknown"))
        link_rows.append(_healthy_link(row.get("link_status")))
        checked_age = _age_days(row.get("last_checked_at") or row.get("link_checked_at"), now)
        if checked_age is not None:
            checked_recent.append(checked_age <= 30.0)
    link_health = sum(link_rows) / len(link_rows) if link_rows else 0.0
    checked_ratio = sum(checked_recent) / len(checked_recent) if checked_recent else 0.0
    region_coverage = len(regions) / 3.0
    game_coverage = len(games & {"POKEMON", "ONE_PIECE", "NARUTO"}) / 3.0
    source_diversity = min(1.0, len(channel_types) / 5.0)
    coverage = 0.45 * region_coverage + 0.35 * game_coverage + 0.20 * source_diversity
    score = 0.30 * freshness + 0.25 * link_health + 0.20 * checked_ratio + 0.25 * coverage
    confidence = min(1.0, len(sources) / 12.0) * (0.45 + 0.55 * coverage)
    signal_items = signals.get("items") if isinstance(signals.get("items"), list) else []
    return _surface_row("purchase_availability", score, confidence, {
        "source": "purchase_sources.json",
        "source_count": len(sources),
        "signal_count": len(signal_items),
        "updated_age_days": round(age, 3) if age is not None else None,
        "freshness": round(freshness, 6),
        "healthy_link_ratio": round(link_health, 6),
        "checked_within_30d_ratio": round(checked_ratio, 6),
        "regions": sorted(regions),
        "games": sorted(games),
        "channel_type_count": len(channel_types),
        "stock_facts_invented": False,
        "actual_stock_confirmation_required": True,
    })


def tablet_ops_surface(root: Path, now: datetime) -> dict[str, Any]:
    manifest_loaded = False
    control_required = (
        "main",
        "ANDROID_RECOVER_UPDATE.sh",
        "ANDROID_UPDATE_AND_START.sh",
        "TABLET_SCHEDULED_UPDATE.sh",
        "ANDROID_AUTO_START_INSTALL.sh",
        "START_TCG_UPDATER_ANDROID.sh",
        "VERIFY_TABLET_FINAL.sh",
        "VERIFY_TABLET_RUNTIME.sh",
        "tablet_runtime_probe.py",
        "tablet_runtime_qa.py",
        "TABLET_GDRIVE_SYNC.sh",
        "TABLET_GDRIVE_SYNC_INSTALL.sh",
        "TABLET_COLLECT_AND_SEND.sh",
        "tablet_runtime_manifest.py",
    )
    all_required = control_required
    pwa_required: tuple[str, ...] = ()
    try:
        import tablet_runtime_manifest as runtime_manifest
        manifest_loaded = True
        control_required = tuple(runtime_manifest.TABLET_CONTROL_PLANE_FILES)
        pwa_required = tuple(runtime_manifest.TABLET_PWA_ENTRY_FILES)
        all_required = tuple(runtime_manifest.ACTIVE_RUNTIME_FILES)
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    control_present = [name for name in control_required if _file_ok(root, name)]
    pwa_present = [name for name in pwa_required if _file_ok(root, name)]
    all_present = [name for name in all_required if _file_ok(root, name)]
    control_score = len(control_present) / max(1, len(control_required))
    full_runtime_score = len(all_present) / max(1, len(all_required))
    pwa_score = len(pwa_present) / max(1, len(pwa_required)) if pwa_required else control_score

    current = _read_json(root, "CURRENT_RUNTIME_VERIFICATION_REPORT.json", max_bytes=5_000_000) or {}
    age = _age_days(current.get("finished_at") or current.get("updated_at") or current.get("started_at"), now)
    freshness = _freshness_score(age)
    current_ok = current.get("ok") is True and freshness > 0.0
    score = (
        0.34 * control_score
        + 0.28 * full_runtime_score
        + 0.18 * pwa_score
        + 0.20 * (1.0 if current_ok else freshness)
    )
    confidence = min(
        control_score,
        full_runtime_score,
        0.55 * full_runtime_score + 0.45 * freshness,
    )
    return _surface_row("tablet_ops", score, confidence, {
        "manifest_loaded": manifest_loaded,
        "control_plane_schema_version": (
            getattr(runtime_manifest, "CONTROL_PLANE_SCHEMA_VERSION", None)
            if manifest_loaded else None
        ),
        "required_control_plane_assets": len(control_required),
        "present_control_plane_assets": len(control_present),
        "missing_control_plane_assets": sorted(set(control_required) - set(control_present)),
        "required_pwa_assets": len(pwa_required),
        "present_pwa_assets": len(pwa_present),
        "required_runtime_assets": len(all_required),
        "present_runtime_assets": len(all_present),
        "missing_runtime_assets": sorted(set(all_required) - set(all_present))[:32],
        "full_runtime_coverage": round(full_runtime_score, 6),
        "current_runtime_report_present": bool(current),
        "current_runtime_report_ok": current_ok,
        "verification_age_days": round(age, 3) if age is not None else None,
        "verification_freshness": round(freshness, 6),
        "physical_tablet_runtime_verified": False,
        "runtime_commands_auto_generated": False,
    })


def surface_portfolio(root: Path, base: dict[str, Any], now: datetime) -> dict[str, Any]:
    rows = [
        ui_surface(root),
        card_measurement_surface(root, now),
        card_market_surface(root, now),
        card_release_surface(root, now),
        collab_event_surface(root, now),
        purchase_availability_surface(root, now),
        tablet_ops_surface(root, now),
    ]
    rows.sort(key=lambda row: (-float(row["urgency"]), float(row["score"]), row["surface"]))
    selected = rows[0] if rows else None
    return {
        "surfaces": rows,
        "selected_surface": selected["surface"] if selected else None,
        "selected_urgency": selected["urgency"] if selected else None,
        "selected_status": selected["status"] if selected else None,
        "selected_score": selected["score"] if selected else None,
        "selected_confidence": selected["confidence"] if selected else None,
        "selection_basis": "largest_verified_operational_deficit_or_evidence_gap",
        "market_direction_inferred": False,
    }


def _surface_map(portfolio: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("surface")): row
        for row in portfolio.get("surfaces", [])
        if isinstance(row, dict) and str(row.get("surface")) in SURFACES
    }


def update_surface_memory(state: dict[str, Any], portfolio: dict[str, Any]) -> dict[str, Any]:
    cycle = int(state.get("cycle") or 0) + 1
    memory = deepcopy(state.get("surface_memory") or {})
    for surface, current in _surface_map(portfolio).items():
        previous = memory.get(surface) if isinstance(memory.get(surface), dict) else _default_memory_row()
        observations = min(1_000_000, int(previous["observations"]) + 1)
        score = float(current["score"])
        confidence = float(current["confidence"])
        score_ewma = score if observations == 1 else 0.30 * score + 0.70 * float(previous["score_ewma"])
        conf_ewma = confidence if observations == 1 else 0.30 * confidence + 0.70 * float(previous["confidence_ewma"])
        attention = int(previous["consecutive_attention"]) + 1 if current["status"] == "attention" else 0
        memory[surface] = {
            "observations": observations,
            "score_ewma": round(_clamp(score_ewma), 6),
            "confidence_ewma": round(_clamp(conf_ewma), 6),
            "consecutive_attention": min(1_000_000, attention),
            "last_status": str(current["status"]),
            "last_seen_cycle": cycle,
        }
    return {
        "schema_version": 1,
        "controller_version": CONTROLLER_VERSION,
        "cycle": cycle,
        "surface_memory": dict(sorted(memory.items())[:MAX_SURFACE_MEMORY]),
        "active": deepcopy(state.get("active")) if isinstance(state.get("active"), dict) else None,
        "history": list(state.get("history") or []),
    }


def source_feature_candidates(portfolio: dict[str, Any], memory: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    validation = {
        "ui": [
            "targeted_ui_test", "browser_runtime_check", "pwa_cache_check",
            "tablet_runtime_manifest_check", "repository_integrity",
            "tablet_gpt_tcg_grader_alignment", "actual_tablet_output_validation",
        ],
        "card_measurement": [
            "camera_front_back_validation", "image_quality_guard_regression",
            "centering_surface_edge_corner_regression", "certified_grade_holdout_validation",
            "psa_bgs_cgc_tag_brg_company_isolation", "full_grading_regression",
            "repository_integrity", "actual_tablet_output_validation",
        ],
        "card_market": [
            "kr_jp_us_market_freshness_check", "source_link_health_check",
            "price_provenance_validation", "currency_conversion_regression",
            "market_collection_regression", "repository_integrity",
            "actual_tablet_output_validation",
        ],
        "card_release": [
            "kr_jp_us_release_coverage_check", "official_release_source_validation",
            "release_date_window_precision_regression", "release_lifecycle_archive_regression",
            "release_duplicate_supersession_regression", "repository_integrity",
            "actual_tablet_output_validation",
        ],
        "collab_event": [
            "kr_jp_us_event_coverage_check", "official_source_validation",
            "collaboration_category_regression", "promo_lifecycle_regression",
            "event_duplicate_supersession_regression", "repository_integrity",
            "actual_tablet_output_validation",
        ],
        "purchase_availability": [
            "purchase_source_freshness_check", "purchase_link_health_check",
            "purchase_region_game_coverage_check", "stock_claim_confirmation_regression",
            "purchase_collection_regression", "repository_integrity",
            "actual_tablet_output_validation",
        ],
        "tablet_ops": [
            "tablet_runtime_manifest_check", "scheduled_update_guard",
            "current_runtime_verification", "repository_integrity",
            "actual_tablet_output_validation",
        ],
    }
    rows = _surface_map(portfolio)
    for surface in SURFACES:
        row = rows.get(surface)
        mem = memory.get(surface) if isinstance(memory.get(surface), dict) else _default_memory_row()
        if not row or row.get("status") == "healthy":
            continue
        recurrence = int(mem.get("consecutive_attention") or 0)
        result.append({
            "candidate_id": "SURFACE_GAP:" + surface.upper(),
            "surface": surface,
            "score": row.get("score"),
            "confidence": row.get("confidence"),
            "urgency": row.get("urgency"),
            "recurrence": recurrence,
            "stage": "protected_pr_candidate" if recurrence >= PROTECTED_PR_RECURRENCE else "observe",
            "auto_execute": False,
            "auto_generate_source": False,
            "auto_rewrite_source": False,
            "git_write": False,
            "protected_pr_ci_required": True,
            "validation_required": validation[surface],
        })
    result.sort(key=lambda row: (-float(row["urgency"]), -int(row["recurrence"]), row["surface"]))
    return result


def needed_feature_candidates(portfolio: dict[str, Any], memory: dict[str, Any]) -> list[dict[str, Any]]:
    rows = _surface_map(portfolio)
    result: list[dict[str, Any]] = []
    for surface in SURFACES:
        row = rows.get(surface)
        mem = memory.get(surface) if isinstance(memory.get(surface), dict) else _default_memory_row()
        if not row or row.get("status") == "healthy":
            continue
        recurrence = int(mem.get("consecutive_attention") or 0)
        feature_id = FEATURE_GAP_RECIPES[surface]
        result.append({
            "feature_id": feature_id,
            "surface": surface,
            "reason": "repeated_verified_surface_deficit" if recurrence >= PROTECTED_PR_RECURRENCE else "verified_surface_deficit_observation",
            "urgency": row.get("urgency"),
            "confidence": row.get("confidence"),
            "recurrence": recurrence,
            "stage": "protected_pr_candidate" if recurrence >= PROTECTED_PR_RECURRENCE else "observe",
            "implementation_mode": "protected_pr_ci_only",
            "auto_execute": False,
            "runtime_generate_source": False,
            "auto_rewrite_source": False,
            "git_write": False,
            "market_direction_inferred": False,
            "validation_required": [
                "targeted_surface_regression",
                "tablet_runtime_manifest_check",
                "repository_integrity",
                "tablet_gpt_tcg_grader_alignment",
                "actual_tablet_output_validation",
            ],
        })
    result.sort(key=lambda row: (-float(row["urgency"]), -int(row["recurrence"]), row["surface"]))
    return result


def _v373():
    return v399.v398.v397.v391.v390.v373


def _cap_owner(capability: dict[str, Any]) -> str:
    evidence = capability.get("evidence") if isinstance(capability.get("evidence"), dict) else {}
    return str(evidence.get("owner_controller") or "")


def steering_capability(portfolio: dict[str, Any], *, now: datetime) -> dict[str, Any] | None:
    selected = str(portfolio.get("selected_surface") or "")
    urgency = float(_finite(portfolio.get("selected_urgency")) or 0.0)
    if selected not in SURFACES or urgency < MIN_STEERING_URGENCY:
        return None
    v373 = _v373()
    rows = _surface_map(portfolio)
    evidence = {
        "owner_controller": CONTROLLER_VERSION,
        "reason": "v400_surface_verified_deficit_steering",
        "surface": selected,
        "urgency": round(urgency, 6),
        "market_direction_inferred": False,
    }
    if selected in {"ui", "card_measurement"}:
        cap = v373._capability(
            "INCREASE_OBSERVATION", "V400_" + selected.upper(),
            {"scope": "runtime_models", "factor": 1.5 if selected == "card_measurement" else 1.25},
            evidence, now=now,
        )
        return cap if v373.validate_capability(cap, now=now) else None
    if selected == "card_market":
        row = rows.get("card_market") or {}
        ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        if float(_finite(ev.get("freshness")) or 0.0) < 0.80:
            cap = v373._capability(
                "REQUEST_FRESHNESS_REFRESH", "V400_MARKET", {"max_runs": 1}, evidence, now=now
            )
            return cap if v373.validate_capability(cap, now=now) else None
        if float(_finite(ev.get("healthy_link_ratio")) or 0.0) < 0.80:
            cap = v373._capability(
                "RETRY_DEGRADED_SOURCES", "V400_MARKET",
                {"max_retry": 2, "backoff_seconds": 120}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
        missing = [region for region in ("KR", "JP", "US") if region not in set(ev.get("regions") or [])]
        if missing:
            cap = v373._capability(
                "PRIORITIZE_REGION", "V400_" + missing[0],
                {"region": missing[0], "boost": min(0.12, 0.05 + 0.07 * urgency)}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
    if selected == "card_release":
        row = rows.get("card_release") or {}
        ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        if float(_finite(ev.get("freshness")) or 0.0) < 0.80:
            cap = v373._capability(
                "REQUEST_FRESHNESS_REFRESH", "V400_RELEASES", {"max_runs": 1}, evidence, now=now
            )
            return cap if v373.validate_capability(cap, now=now) else None
        if float(_finite(ev.get("healthy_link_ratio")) or 0.0) < 0.85:
            cap = v373._capability(
                "RETRY_DEGRADED_SOURCES", "V400_RELEASES",
                {"max_retry": 2, "backoff_seconds": 120}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
        missing = [region for region in ("KR", "JP", "US") if region not in set(ev.get("regions") or [])]
        if missing:
            cap = v373._capability(
                "PRIORITIZE_REGION", "V400_RELEASE_" + missing[0],
                {"region": missing[0], "boost": min(0.12, 0.05 + 0.07 * urgency)}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
        cap = v373._capability(
            "INCREASE_OBSERVATION", "V400_RELEASES",
            {"scope": "market_health", "factor": 1.25}, evidence, now=now,
        )
        return cap if v373.validate_capability(cap, now=now) else None
    if selected == "collab_event":
        row = rows.get("collab_event") or {}
        ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        if float(_finite(ev.get("healthy_link_ratio")) or 0.0) < 0.85:
            cap = v373._capability(
                "RETRY_DEGRADED_SOURCES", "V400_EVENTS",
                {"max_retry": 2, "backoff_seconds": 120}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
        missing = [region for region in ("KR", "JP", "US") if region not in set(ev.get("regions") or [])]
        if missing:
            cap = v373._capability(
                "PRIORITIZE_REGION", "V400_EVENT_" + missing[0],
                {"region": missing[0], "boost": min(0.12, 0.05 + 0.07 * urgency)}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
        cap = v373._capability(
            "INCREASE_OBSERVATION", "V400_EVENTS",
            {"scope": "market_health", "factor": 1.25}, evidence, now=now,
        )
        return cap if v373.validate_capability(cap, now=now) else None

    if selected == "purchase_availability":
        row = rows.get("purchase_availability") or {}
        ev = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
        if float(_finite(ev.get("freshness")) or 0.0) < 0.80:
            cap = v373._capability(
                "REQUEST_FRESHNESS_REFRESH", "V400_PURCHASE", {"max_runs": 1}, evidence, now=now
            )
            return cap if v373.validate_capability(cap, now=now) else None
        if float(_finite(ev.get("healthy_link_ratio")) or 0.0) < 0.80:
            cap = v373._capability(
                "RETRY_DEGRADED_SOURCES", "V400_PURCHASE",
                {"max_retry": 2, "backoff_seconds": 120}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
        missing = [region for region in ("KR", "JP", "US") if region not in set(ev.get("regions") or [])]
        if missing:
            cap = v373._capability(
                "PRIORITIZE_REGION", "V400_PURCHASE_" + missing[0],
                {"region": missing[0], "boost": min(0.12, 0.05 + 0.07 * urgency)}, evidence, now=now,
            )
            return cap if v373.validate_capability(cap, now=now) else None
        cap = v373._capability(
            "INCREASE_OBSERVATION", "V400_PURCHASE",
            {"scope": "market_health", "factor": 1.20}, evidence, now=now,
        )
        return cap if v373.validate_capability(cap, now=now) else None
    if selected == "tablet_ops":
        cap = v373._capability(
            "INCREASE_OBSERVATION", "V400_TABLET_OPS",
            {"scope": "runtime_models", "factor": 1.20}, evidence, now=now,
        )
        return cap if v373.validate_capability(cap, now=now) else None
    return None


def _load_caps(path: Path, *, now: datetime) -> dict[str, Any]:
    return _v373().load_capabilities(path=path, now=now)


def _persist_capability(capability: dict[str, Any], path: Path, *, now: datetime) -> dict[str, Any]:
    v373 = _v373()
    if not v373.validate_capability(capability, now=now) or _cap_owner(capability) != CONTROLLER_VERSION:
        return {"status": "V400_INVALID_CAPABILITY", "written": False}
    loaded = _load_caps(path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V400_CAPABILITY_CORRUPTION_HOLD", "written": False}
    rows = list(loaded.get("capabilities") or [])
    owner = next((_cap_owner(row) for row in rows if _cap_owner(row) in {"v397", "v398", "v400"}), None)
    if owner:
        return {"status": "V400_EXPERIMENTAL_CAPABILITY_CONFLICT", "written": False, "owner": owner}
    write = v373.save_capabilities(
        v373.merge_capabilities(rows, [capability], now=now),
        path=path, corruption_hold=False, now=now,
    )
    return write


def _remove_active(active: dict[str, Any], path: Path, *, now: datetime, reason: str) -> dict[str, Any]:
    v373 = _v373()
    loaded = _load_caps(path, now=now)
    if loaded.get("corruption_hold") is True:
        return {"status": "V400_CAPABILITY_CORRUPTION_HOLD", "written": False, "removed": False}
    rows = list(loaded.get("capabilities") or [])
    target = next((row for row in rows if str(row.get("id") or "") == active["id"]), None)
    if target is None:
        return {"status": "V400_CAPABILITY_ALREADY_ABSENT", "written": False, "removed": True, "reason": reason}
    if _cap_owner(target) != CONTROLLER_VERSION:
        return {"status": "V400_CAPABILITY_OWNERSHIP_HOLD", "written": False, "removed": False}
    kept = [row for row in rows if str(row.get("id") or "") != active["id"]]
    write = v373.save_capabilities(kept, path=path, corruption_hold=False, now=now)
    return {**write, "removed": write.get("written") is True, "reason": reason, "capability_id": active["id"]}


def evaluate_active(state: dict[str, Any], portfolio: dict[str, Any], cap_ids: set[str], *, upstream_allow: bool) -> dict[str, Any]:
    active = state.get("active")
    if not isinstance(active, dict):
        return {"status": "NO_ACTIVE_V400_CAPABILITY", "rollback": False, "release": False, "score_delta": None}
    if active["id"] not in cap_ids:
        return {"status": "ACTIVE_CAPABILITY_EXPIRED_OR_ABSENT", "rollback": False, "release": True, "score_delta": None}
    if not upstream_allow:
        return {"status": "UPSTREAM_HARD_HOLD", "rollback": True, "release": False, "score_delta": None}
    row = _surface_map(portfolio).get(active["surface"])
    if not row:
        return {"status": "SURFACE_EVIDENCE_MISSING", "rollback": True, "release": False, "score_delta": None}
    current = float(row["score"])
    baseline = float(active["baseline_score"])
    cycle = int(state.get("cycle") or 0) + 1
    if cycle <= int(active["activated_cycle"]):
        return {"status": "CANARY_OBSERVE", "rollback": False, "release": False, "score_delta": None}
    delta = current - baseline
    if delta <= -ROLLBACK_DROP:
        return {"status": "MATERIAL_SURFACE_REGRESSION", "rollback": True, "release": False, "score_delta": round(delta, 6)}
    if delta >= VERIFIED_GAIN:
        return {"status": "VERIFIED_POSITIVE_SURFACE_CANARY", "rollback": False, "release": True, "score_delta": round(delta, 6)}
    if cycle - int(active["activated_cycle"]) >= MAX_ACTIVE_CYCLES:
        return {"status": "NEUTRAL_CANARY_RELEASE", "rollback": False, "release": True, "score_delta": round(delta, 6)}
    return {"status": "CANARY_OBSERVE", "rollback": False, "release": False, "score_delta": round(delta, 6)}


def _next_state(state: dict[str, Any], memory_state: dict[str, Any], *, portfolio: dict[str, Any],
                evaluation: dict[str, Any], new_capability: dict[str, Any] | None,
                capability_removed: bool, adaptive_layout: dict[str, Any], now: datetime) -> dict[str, Any]:
    result = deepcopy(memory_state)
    active = deepcopy(state.get("active")) if isinstance(state.get("active"), dict) else None
    if capability_removed:
        active = None
    if new_capability is not None:
        surface = str(portfolio.get("selected_surface") or "")
        selected = _surface_map(portfolio).get(surface) or {}
        active = {
            "id": str(new_capability["id"]),
            "surface": surface,
            "primitive": str(new_capability["primitive"]),
            "baseline_score": round(float(selected.get("score") or 0.0), 6),
            "activated_cycle": int(result["cycle"]),
        }
    result["active"] = active
    history = list(result.get("history") or [])
    module_plan = adaptive_layout.get("screen_module_plan") if isinstance(adaptive_layout.get("screen_module_plan"), dict) else {}
    experience_plan = adaptive_layout.get("video_experience_plan") if isinstance(adaptive_layout.get("video_experience_plan"), dict) else {}
    policy_learning = adaptive_layout.get("policy_learning") if isinstance(adaptive_layout.get("policy_learning"), dict) else {}
    meta_learning = policy_learning.get("meta_neural") if isinstance(policy_learning.get("meta_neural"), dict) else {}
    screen_learning = policy_learning.get("screen_neural") if isinstance(policy_learning.get("screen_neural"), dict) else {}
    policy_features = policy_learning.get("policy_features") if isinstance(policy_learning.get("policy_features"), list) else []
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": result["cycle"],
        "selected_surface": portfolio.get("selected_surface"),
        "selected_urgency": portfolio.get("selected_urgency"),
        "active_capability": active.get("id") if isinstance(active, dict) else None,
        "active_surface": active.get("surface") if isinstance(active, dict) else None,
        "evaluation": evaluation.get("status"),
        "score_delta": evaluation.get("score_delta"),
        "adaptive_applied": adaptive_layout.get("apply_layout") is True,
        "top_features": list(module_plan.get("top_features") or [])[:5],
        "top_experiences": list(experience_plan.get("order") or [])[:3],
        "experience_confidence": {
            key: float(value)
            for key, value in dict(experience_plan.get("module_confidence") or {}).items()
            if key in VIDEO_EXPERIENCE_MODULES and _finite(value) is not None
        },
        "surface_scores": _surface_scores(portfolio),
        "surface_confidences": _surface_confidences(portfolio),
        "meta_neural_active": meta_learning.get("active") is True,
        "meta_neural_sample_count": int(meta_learning.get("sample_count") or 0),
        "screen_neural_active": screen_learning.get("active") is True,
        "screen_neural_sample_count": int(screen_learning.get("sample_count") or 0),
        "policy_features": list(policy_features)[:screen_neural.INPUT_DIM],
    })
    result["history"] = history[-MAX_HISTORY:]
    return result



def _recent_window(value: Any, now: datetime, days: float = 14.0) -> bool:
    age = _age_days(value, now)
    return age is not None and 0.0 <= age <= days


def market_activity(root: Path, now: datetime) -> dict[str, Any]:
    """Summarize verified market attention without treating stale rows as live market direction."""
    releases = _read_json(root, "releases.json") or {}
    events = _read_json(root, "promo_events.json") or {}
    watch = _read_json(root, "market_watch.json") or {}
    release_items = releases.get("items") if isinstance(releases.get("items"), list) else []
    event_items = events.get("items") if isinstance(events.get("items"), list) else []
    watch_items = watch.get("items") if isinstance(watch.get("items"), list) else []

    def dataset_freshness(payload: dict[str, Any]) -> float:
        return round(_freshness_score(_age_days(payload.get("updated_at"), now)), 6)

    release_freshness = dataset_freshness(releases)
    event_freshness = dataset_freshness(events)
    watch_freshness = dataset_freshness(watch)

    recent_release_rows = [
        row for row in release_items[:5000]
        if isinstance(row, dict) and (
            _recent_window(row.get("release_date"), now, 21.0)
            or _recent_window(row.get("last_verified_at"), now, 7.0)
        )
    ]

    def event_is_current(row: dict[str, Any]) -> bool:
        if str(row.get("lifecycle") or "").lower() != "current":
            return False
        if row.get("tracking_only") is True:
            return False
        # An event can finish before its reward/claim window closes. Treat the
        # row as current while either verified operational deadline is still
        # active instead of letting an older end_date mask claim_deadline.
        deadlines = [
            stamp
            for stamp in (
                _parse_time(row.get("end_date")),
                _parse_time(row.get("claim_deadline")),
            )
            if stamp is not None
        ]
        return not deadlines or max(stamp.date() for stamp in deadlines) >= now.date()

    active_event_rows = [
        row for row in event_items[:5000]
        if isinstance(row, dict) and event_is_current(row)
    ]
    current_market_rows = [
        row for row in watch_items[:5000]
        if isinstance(row, dict) and str(row.get("sale_status") or "").strip()
    ]

    def canonical_game(value: Any) -> str | None:
        text = str(value or "").strip().lower()
        if "pok" in text or "포켓몬" in text:
            return "Pokémon"
        if "one piece" in text or "원피스" in text:
            return "ONE PIECE"
        if "naruto" in text or "나루토" in text:
            return "NARUTO"
        return None

    game_counts = {
        key: {"market": 0, "release": 0, "event": 0}
        for key in MARKET_LENS_GAMES
    }
    region_counts = {
        key: {"market": 0, "release": 0, "event": 0}
        for key in MARKET_LENS_REGIONS
    }

    def observe(rows: list[dict[str, Any]], bucket: str) -> None:
        for row in rows:
            game = canonical_game(row.get("game"))
            region = str(row.get("region") or "").upper()
            if game in game_counts:
                game_counts[game][bucket] += 1
            if region in region_counts:
                region_counts[region][bucket] += 1

    observe(current_market_rows, "market")
    observe(recent_release_rows, "release")
    observe(active_event_rows, "event")

    def context_scores(counts: dict[str, dict[str, int]]) -> dict[str, float]:
        return {
            key: round(_clamp(
                0.45 * min(1.0, float(value["market"]) / 6.0) * watch_freshness
                + 0.35 * min(1.0, float(value["release"]) / 4.0) * release_freshness
                + 0.20 * min(1.0, float(value["event"]) / 4.0) * event_freshness
            ), 6)
            for key, value in counts.items()
        }

    def bounded_focus(scores: dict[str, float]) -> tuple[str, float, float]:
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        if not ranked:
            return "ALL", 0.0, 0.0
        top_key, top_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0
        margin = max(0.0, top_score - second_score)
        confidence = _clamp(0.60 * top_score + 0.40 * min(1.0, margin * 2.5))
        focus = top_key if top_score >= 0.28 and margin >= 0.08 else "ALL"
        return focus, round(confidence, 6), round(margin, 6)

    game_scores = context_scores(game_counts)
    region_scores = context_scores(region_counts)
    focus_game, game_confidence, game_margin = bounded_focus(game_scores)
    focus_region, region_confidence, region_margin = bounded_focus(region_scores)
    freshness = {
        "market_watch": watch_freshness,
        "releases": release_freshness,
        "promo_events": event_freshness,
    }
    stale_datasets = sorted(key for key, value in freshness.items() if value < 0.60)

    recent_releases = len(recent_release_rows)
    active_events = len(active_event_rows)
    current_market = len(current_market_rows)
    return {
        "recent_release_count": recent_releases,
        "current_event_count": active_events,
        "market_watch_count": current_market,
        "release_activity": round(min(1.0, recent_releases / 12.0) * release_freshness, 6),
        "event_activity": round(min(1.0, active_events / 18.0) * event_freshness, 6),
        "market_activity": round(min(1.0, current_market / 24.0) * watch_freshness, 6),
        "dataset_freshness": freshness,
        "stale_datasets": stale_datasets,
        "expired_or_tracking_events_excluded": max(0, len([
            row for row in event_items[:5000]
            if isinstance(row, dict) and str(row.get("lifecycle") or "").lower() == "current"
        ]) - active_events),
        "market_lens": {
            "focus_game": focus_game,
            "focus_region": focus_region,
            "game_scores": game_scores,
            "region_scores": region_scores,
            "game_confidence": game_confidence,
            "region_confidence": region_confidence,
            "game_margin": game_margin,
            "region_margin": region_margin,
            "verified_attention_rows": recent_releases + active_events + current_market,
            "verified_data_only": True,
            "user_reversible": True,
            "market_direction_inferred": False,
            "price_direction_used": False,
        },
        "market_direction_inferred": False,
        "activity_is_attention_signal_only": True,
        "dataset_freshness_weighted": True,
    }


def market_context_feature_bias(activity: dict[str, Any]) -> dict[str, Any]:
    """Translate verified non-directional market attention into a small UI-only bias."""
    freshness_raw = activity.get("dataset_freshness") if isinstance(activity.get("dataset_freshness"), dict) else {}
    freshness = {
        key: _clamp(float(_finite(freshness_raw.get(key)) or 0.0))
        for key in ("market_watch", "releases", "promo_events")
    }
    average_freshness = sum(freshness.values()) / 3.0
    stale = activity.get("stale_datasets") if isinstance(activity.get("stale_datasets"), list) else []
    stale_ratio = min(1.0, len({str(key) for key in stale}) / 3.0)
    reliability = _clamp(average_freshness * (1.0 - 0.35 * stale_ratio))

    signals = {
        "trade_attention": _clamp(float(_finite(activity.get("market_activity")) or 0.0)),
        "release_attention": _clamp(float(_finite(activity.get("release_activity")) or 0.0)),
        "event_attention": _clamp(float(_finite(activity.get("event_activity")) or 0.0)),
    }
    ranked = sorted(signals.items(), key=lambda item: (-item[1], item[0]))
    top_key, top_value = ranked[0]
    second_value = ranked[1][1] if len(ranked) > 1 else 0.0
    dominance_margin = max(0.0, top_value - second_value)
    if top_value < 0.12:
        state = "quiet"
    elif reliability < 0.45:
        state = "revalidate"
    elif dominance_margin < 0.08:
        state = "mixed_attention"
    else:
        state = top_key
    active = state not in {"quiet", "revalidate"}

    biases = {key: 0.0 for key in FEATURE_TARGETS}
    if active:
        for signal_key, weights in MARKET_CONTEXT_FEATURE_WEIGHTS.items():
            strength = signals[signal_key]
            for feature, weight in weights.items():
                biases[feature] += strength * float(weight)
        biases = {
            key: round(
                _clamp(value, 0.0, 1.0) * reliability * MAX_MARKET_CONTEXT_BIAS,
                6,
            )
            for key, value in biases.items()
        }
    else:
        biases = {key: 0.0 for key in FEATURE_TARGETS}

    lens = activity.get("market_lens") if isinstance(activity.get("market_lens"), dict) else {}
    return {
        "active": active,
        "state": state,
        "signals": signals,
        "dataset_freshness": freshness,
        "reliability": round(reliability, 6),
        "dominance_margin": round(dominance_margin, 6),
        "focus_game": str(lens.get("focus_game") or "ALL"),
        "focus_region": str(lens.get("focus_region") or "ALL"),
        "feature_biases": biases,
        "max_abs_bias": round(max((abs(value) for value in biases.values()), default=0.0), 6),
        "verified_activity_only": True,
        "freshness_gated": True,
        "advisory_only": True,
        "market_direction_inferred": False,
        "price_direction_used": False,
        "user_behavior_tracking": False,
    }


def neural_feature_bias(base: dict[str, Any]) -> dict[str, Any]:
    """Map the existing verified-outcome meta neural policy into tiny UI feature biases."""
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    raw_scores = plan.get("meta_scores") if isinstance(plan.get("meta_scores"), dict) else {}
    meta = base.get("meta_neural") if isinstance(base.get("meta_neural"), dict) else {}
    sample_count = int(meta.get("sample_count") or 0) if not isinstance(meta.get("sample_count"), bool) else 0
    minimum = int(getattr(_v373(), "MIN_META_OUTCOMES", 8))
    active = meta.get("active") is True and sample_count >= minimum
    action_scores: dict[str, float] = {}
    for action in getattr(_v373(), "META_ACTIONS", ()):
        value = _finite(raw_scores.get(action))
        action_scores[action] = round(_clamp(float(value or 0.0), -1.0, 1.0), 6)
    biases = {key: 0.0 for key in FEATURE_TARGETS}
    if active:
        for action, weights in META_ACTION_FEATURE_WEIGHTS.items():
            score = action_scores.get(action, 0.0)
            for feature, weight in weights.items():
                biases[feature] += score * float(weight) * MAX_NEURAL_FEATURE_BIAS
    biases = {
        key: round(_clamp(value, -MAX_NEURAL_FEATURE_BIAS, MAX_NEURAL_FEATURE_BIAS), 6)
        for key, value in biases.items()
    }
    return {
        "active": active,
        "sample_count": sample_count,
        "minimum_verified_outcomes": minimum,
        "action_scores": action_scores,
        "feature_biases": biases,
        "max_abs_bias": round(max((abs(value) for value in biases.values()), default=0.0), 6),
        "verified_outcomes_only": True,
        "advisory_only": True,
    }


def _surface_scores(portfolio: dict[str, Any]) -> dict[str, float]:
    return {
        surface: round(float(row.get("score") or 0.0), 6)
        for surface, row in _surface_map(portfolio).items()
    }


def _surface_confidences(portfolio: dict[str, Any]) -> dict[str, float]:
    return {
        surface: round(float(row.get("confidence") or 0.0), 6)
        for surface, row in _surface_map(portfolio).items()
    }


def verified_outcome_feature_feedback(state: dict[str, Any], portfolio: dict[str, Any]) -> dict[str, Any]:
    """Learn a weak correlation signal only from prior applied plans and later verified surface scores."""
    history = [row for row in list(state.get("history") or []) if isinstance(row, dict)][-MAX_POLICY_TRANSITIONS:]
    current_scores = _surface_scores(portfolio)
    rewards: dict[str, list[float]] = {key: [] for key in FEATURE_TARGETS}
    transitions = 0
    for index, row in enumerate(history):
        if row.get("adaptive_applied") is not True:
            continue
        before = row.get("surface_scores") if isinstance(row.get("surface_scores"), dict) else {}
        top = row.get("top_features") if isinstance(row.get("top_features"), list) else []
        if not before or not top:
            continue
        after: dict[str, Any] | None = None
        for later in history[index + 1:]:
            candidate = later.get("surface_scores") if isinstance(later.get("surface_scores"), dict) else None
            if candidate:
                after = candidate
                break
        if after is None:
            after = current_scores
        used = False
        for feature in top[:5]:
            feature = str(feature)
            surface = FEATURE_SURFACE.get(feature)
            if not surface:
                continue
            a = _finite(before.get(surface))
            b = _finite(after.get(surface))
            if a is None or b is None:
                continue
            delta = _clamp(float(b) - float(a), -0.20, 0.20)
            rewards[feature].append(delta)
            used = True
        transitions += 1 if used else 0

    biases = {}
    observations = {}
    for feature in FEATURE_TARGETS:
        values = rewards[feature]
        observations[feature] = len(values)
        average = sum(values) / len(values) if values else 0.0
        biases[feature] = round(
            _clamp(average * 0.35, -MAX_OUTCOME_FEATURE_BIAS, MAX_OUTCOME_FEATURE_BIAS),
            6,
        )
    return {
        "transitions_used": transitions,
        "feature_observations": observations,
        "feature_biases": biases,
        "max_abs_bias": round(max((abs(value) for value in biases.values()), default=0.0), 6),
        "verified_surface_scores_only": True,
        "causality_claimed": False,
        "user_behavior_tracking": False,
    }


def _combined_policy_bias(
    neural: dict[str, Any],
    outcome: dict[str, Any],
    screen_adapter: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
) -> dict[str, float]:
    n = neural.get("feature_biases") if isinstance(neural.get("feature_biases"), dict) else {}
    o = outcome.get("feature_biases") if isinstance(outcome.get("feature_biases"), dict) else {}
    a = (
        screen_adapter.get("feature_biases")
        if isinstance(screen_adapter, dict) and isinstance(screen_adapter.get("feature_biases"), dict)
        else {}
    )
    m = (
        market_context.get("feature_biases")
        if isinstance(market_context, dict) and isinstance(market_context.get("feature_biases"), dict)
        else {}
    )
    return {
        key: round(
            _clamp(
                float(n.get(key) or 0.0)
                + float(o.get(key) or 0.0)
                + float(a.get(key) or 0.0)
                + float(m.get(key) or 0.0),
                -MAX_COMBINED_FEATURE_BIAS,
                MAX_COMBINED_FEATURE_BIAS,
            ),
            6,
        )
        for key in FEATURE_TARGETS
    }


def adaptive_layout_plan(root: Path, portfolio: dict[str, Any], memory: dict[str, Any],
                         now: datetime, *, allow_layout: bool,
                         base: dict[str, Any] | None = None,
                         state: dict[str, Any] | None = None,
                         screen_model: dict[str, Any] | None = None,
                         screen_training: dict[str, Any] | None = None,
                         screen_load_status: str | None = None) -> dict[str, Any]:
    rows = _surface_map(portfolio)
    activity = market_activity(root, now)
    neural_feedback = neural_feature_bias(base or {})
    outcome_feedback = verified_outcome_feature_feedback(state or {}, portfolio)
    screen_policy_features = screen_neural.policy_features(portfolio, activity)
    screen_feedback = screen_neural.feature_bias(screen_model, screen_policy_features, now=now)
    market_context = market_context_feature_bias(activity)
    policy_bias = _combined_policy_bias(neural_feedback, outcome_feedback, screen_feedback, market_context)

    def attention(surface: str) -> float:
        row = rows.get(surface) or {}
        current = float(_finite(row.get("urgency")) or 0.0)
        mem = memory.get(surface) if isinstance(memory.get(surface), dict) else {}
        score_ewma = float(_finite(mem.get("score_ewma")) or 0.5)
        conf_ewma = float(_finite(mem.get("confidence_ewma")) or 0.0)
        historical = _clamp(max(1.0 - score_ewma, 0.85 * (1.0 - conf_ewma)))
        return _clamp(0.65 * current + 0.35 * historical)

    priorities = {
        "grading": 0.72 * attention("card_measurement") + 0.18 * attention("ui") + 0.10,
        "market": 0.72 * attention("card_market") + 0.18 * float(activity["market_activity"]) + 0.10,
        "box": 0.46 * attention("card_market") + 0.34 * attention("card_release") + 0.12 * float(activity["market_activity"]) + 0.08,
        "news": 0.48 * attention("card_release") + 0.32 * attention("collab_event") + 0.12 * max(float(activity["release_activity"]), float(activity["event_activity"])) + 0.08,
        "purchase": 0.68 * attention("purchase_availability") + 0.16 * attention("card_release") + 0.08 * float(activity["market_activity"]) + 0.08,
        "learning": 0.54 * attention("card_measurement") + 0.26 * attention("ui") + 0.20,
        "tablet": 0.70 * attention("tablet_ops") + 0.20 * attention("ui") + 0.10,
        "code": 0.56 * attention("tablet_ops") + 0.24 * attention("ui") + 0.20,
    }
    for category, features in FEATURE_SHORTCUT_ORDER.items():
        learned = sum(policy_bias[key] for key in features) / max(1, len(features))
        priorities[category] = _clamp(priorities[category] + 0.45 * learned)
    original_index = {key: idx for idx, key in enumerate(CATEGORY_ORDER)}
    order = sorted(
        CATEGORY_ORDER,
        key=lambda key: (-round(_clamp(priorities[key]) / 0.07) * 0.07, original_index[key]),
    )
    grade_attention = attention("card_measurement")
    market_attention = attention("card_market")
    release_attention = attention("card_release")
    event_attention = attention("collab_event")
    purchase_attention = attention("purchase_availability")
    tablet_attention = attention("tablet_ops")
    ui_attention = attention("ui")
    release_activity = float(activity["release_activity"])
    event_activity = float(activity["event_activity"])
    trade_activity = float(activity["market_activity"])

    feature_priorities = {
        "auto-grade": 0.58 * grade_attention + 0.22 * ui_attention + 0.20,
        "manual-photo": 0.42 * grade_attention + 0.20 * ui_attention + 0.38,
        "precision-grade": 0.72 * grade_attention + 0.18 * ui_attention + 0.10,
        "market-search": 0.66 * market_attention + 0.24 * trade_activity + 0.10,
        "grading-economics": 0.38 * market_attention + 0.34 * grade_attention + 0.18 * trade_activity + 0.10,
        "trading-catalog": 0.54 * market_attention + 0.34 * trade_activity + 0.12,
        "box-knowledge": 0.36 * market_attention + 0.42 * release_attention + 0.14 * release_activity + 0.08,
        "box-hit-analysis": 0.52 * market_attention + 0.28 * release_attention + 0.12 * trade_activity + 0.08,
        "release-info": 0.62 * release_attention + 0.28 * release_activity + 0.10,
        "promo-event-info": 0.58 * event_attention + 0.30 * event_activity + 0.12,
        "purchase-finder": 0.62 * purchase_attention + 0.18 * release_attention + 0.12 * trade_activity + 0.08,
        "purchase-distance": 0.54 * purchase_attention + 0.16 * ui_attention + 0.10 * release_activity + 0.20,
        "card-ocr": 0.52 * grade_attention + 0.28 * ui_attention + 0.20,
        "verified-grade": 0.64 * grade_attention + 0.20 * ui_attention + 0.16,
        "learning-status": 0.38 * grade_attention + 0.34 * ui_attention + 0.28,
        "tablet-manager": 0.72 * tablet_attention + 0.18 * ui_attention + 0.10,
        "code-audit": 0.48 * tablet_attention + 0.32 * ui_attention + 0.20,
        "code-validation": 0.54 * tablet_attention + 0.28 * ui_attention + 0.18,
    }
    feature_priorities = {
        key: round(_clamp(value + policy_bias[key]), 6)
        for key, value in feature_priorities.items()
    }
    feature_orders = {}
    for category, allowed in FEATURE_SHORTCUT_ORDER.items():
        original_feature_index = {key: idx for idx, key in enumerate(allowed)}
        feature_orders[category] = sorted(
            allowed,
            key=lambda key: (
                -round(feature_priorities[key] / 0.07) * 0.07,
                original_feature_index[key],
            ),
        )

    ranked_features = sorted(
        FEATURE_TARGETS,
        key=lambda key: (
            -round(feature_priorities[key] / 0.07) * 0.07,
            list(FEATURE_TARGETS).index(key),
        ),
    )
    module_rankings = [
        {
            "feature_key": key,
            "category": next(category for category, values in FEATURE_SHORTCUT_ORDER.items() if key in values),
            "target_id": FEATURE_TARGETS[key],
            "panel": FEATURE_PANELS.get(key),
            "priority": feature_priorities[key],
        }
        for key in ranked_features
    ]

    experience_confidence = {
        "home-market-pulse": round(_clamp(
            0.45 * float(_finite((rows.get("card_market") or {}).get("confidence")) or 0.0)
            + 0.30 * float(_finite((rows.get("card_release") or {}).get("confidence")) or 0.0)
            + 0.25 * float(_finite((rows.get("collab_event") or {}).get("confidence")) or 0.0)
        ), 6),
        "capture-quality-gate": round(_clamp(
            0.75 * float(_finite((rows.get("card_measurement") or {}).get("confidence")) or 0.0)
            + 0.25 * float(_finite((rows.get("ui") or {}).get("confidence")) or 0.0)
        ), 6),
        "purchase-split-view": round(_clamp(
            0.80 * float(_finite((rows.get("purchase_availability") or {}).get("confidence")) or 0.0)
            + 0.20 * float(_finite((rows.get("ui") or {}).get("confidence")) or 0.0)
        ), 6),
        "hot-card-box-ranking": round(_clamp(
            0.70 * float(_finite((rows.get("card_market") or {}).get("confidence")) or 0.0)
            + 0.30 * float(_finite((rows.get("card_release") or {}).get("confidence")) or 0.0)
        ), 6),
        "portfolio-summary": round(_clamp(
            0.60 * float(_finite((rows.get("card_measurement") or {}).get("confidence")) or 0.0)
            + 0.40 * float(_finite((rows.get("card_market") or {}).get("confidence")) or 0.0)
        ), 6),
    }
    experience_priorities: dict[str, float] = {}
    for module_key, features in VIDEO_EXPERIENCE_MODULES.items():
        base_priority = sum(feature_priorities[key] for key in features) / max(1, len(features))
        activity_bonus = 0.0
        if module_key in {"home-market-pulse", "hot-card-box-ranking"}:
            activity_bonus = 0.08 * max(trade_activity, release_activity, event_activity)
        elif module_key == "purchase-split-view":
            activity_bonus = 0.06 * max(purchase_attention, release_activity)
        elif module_key == "capture-quality-gate":
            activity_bonus = 0.05 * grade_attention
        confidence_bonus = 0.05 * experience_confidence[module_key]
        low_confidence_revalidation = 0.04 if experience_confidence[module_key] < 0.35 else 0.0
        experience_priorities[module_key] = round(
            _clamp(base_priority + activity_bonus + confidence_bonus + low_confidence_revalidation),
            6,
        )
    experience_order = sorted(
        VIDEO_EXPERIENCE_MODULES,
        key=lambda key: (
            -round(experience_priorities[key] / 0.07) * 0.07,
            list(VIDEO_EXPERIENCE_MODULES).index(key),
        ),
    )

    confidence_rows = [
        float(_finite(row.get("confidence")) or 0.0)
        for row in rows.values() if isinstance(row, dict)
    ]
    evidence_confidence = sum(confidence_rows) / len(confidence_rows) if confidence_rows else 0.0
    category_contract_ok = set(order) == set(CATEGORY_ORDER)
    feature_contract_ok = (
        set(feature_orders) == set(FEATURE_SHORTCUT_ORDER)
        and all(set(feature_orders[key]) == set(FEATURE_SHORTCUT_ORDER[key]) for key in FEATURE_SHORTCUT_ORDER)
    )
    apply_layout = bool(
        allow_layout and evidence_confidence >= 0.30 and category_contract_ok and feature_contract_ok
    )
    return {
        "schema_version": 2,
        "mode": "verified_adaptive_ui_composition",
        "order": order,
        "original_order": list(CATEGORY_ORDER),
        "priorities": {key: round(_clamp(value), 6) for key, value in priorities.items()},
        "feature_orders": feature_orders,
        "feature_priorities": feature_priorities,
        "feature_allowlist": {key: list(values) for key, values in FEATURE_SHORTCUT_ORDER.items()},
        "feature_adaptation": "verified_priority_scoring_existing_dom_shortcuts_only",
        "policy_learning": {
            "meta_neural": neural_feedback,
            "verified_outcome_feedback": outcome_feedback,
            "market_context": market_context,
            "screen_neural": {
                **screen_feedback,
                "load_status": screen_load_status,
                "training": screen_training or {
                    "status": "SCREEN_NEURAL_TRAINING_NOT_REQUESTED",
                    "written": False,
                },
            },
            "policy_features": screen_policy_features,
            "combined_feature_bias": policy_bias,
            "max_combined_bias": round(max((abs(value) for value in policy_bias.values()), default=0.0), 6),
            "neural_source": "existing_v373_meta_neural_plus_v401_verified_screen_policy_neural_plus_verified_market_context_adapter",
            "next_cycle_learning": True,
            "user_behavior_tracking": False,
        },
        "screen_module_plan": {
            "rankings": module_rankings,
            "top_features": [row["feature_key"] for row in module_rankings[:5]],
            "targets": dict(FEATURE_TARGETS),
            "panels": dict(FEATURE_PANELS),
            "apply_focus": apply_layout,
            "existing_targets_only": True,
            "user_reversible": True,
            "dom_reorder": False,
        },
        "video_experience_plan": {
            "order": experience_order,
            "priorities": experience_priorities,
            "module_confidence": experience_confidence,
            "module_state": {
                key: ("verified" if experience_confidence[key] >= 0.55 else "revalidate")
                for key in VIDEO_EXPERIENCE_MODULES
            },
            "allowlist": list(VIDEO_EXPERIENCE_MODULES),
            "feature_dependencies": {
                key: list(values) for key, values in VIDEO_EXPERIENCE_MODULES.items()
            },
            "market_lens": dict(activity.get("market_lens") or {}),
            "dataset_freshness": dict(activity.get("dataset_freshness") or {}),
            "stale_datasets": list(activity.get("stale_datasets") or []),
            "apply_layout": apply_layout,
            "user_reversible": True,
            "verified_data_only": True,
            "market_direction_inferred": False,
            "stock_fact_invented": False,
            "precise_location_persisted": False,
            "user_behavior_tracking": False,
        },
        "evidence_confidence": round(_clamp(evidence_confidence), 6),
        "apply_layout": apply_layout,
        "allowlisted_categories": list(CATEGORY_ORDER),
        "user_override_required": True,
        "reversible": True,
        "auto_open_forbidden": True,
        "source_code_rewrite": False,
        "new_ui_feature_generation": False,
        "video_reference_source_level_modules_predeclared": True,
        "market_activity": activity,
        "market_direction_inferred": False,
    }


def _dashboard_summary(base: dict[str, Any], portfolio: dict[str, Any], evaluation: dict[str, Any],
                       candidates: list[dict[str, Any]], adaptive_layout: dict[str, Any]) -> dict[str, Any]:
    return {
        "controller_version": CONTROLLER_VERSION,
        "core_controller": CORE_CONTROLLER_VERSION,
        "selected_surface": portfolio.get("selected_surface"),
        "selected_urgency": portfolio.get("selected_urgency"),
        "selected_status": portfolio.get("selected_status"),
        "surfaces": portfolio.get("surfaces", []),
        "active_evaluation": evaluation.get("status"),
        "rollback_required": bool(evaluation.get("rollback")),
        "source_candidates": len(candidates),
        "protected_pr_candidates": sum(row.get("stage") == "protected_pr_candidate" for row in candidates),
        "upstream_gate_status": (base.get("v399_autonomous_gate") or {}).get("status")
        if isinstance(base.get("v399_autonomous_gate"), dict) else None,
        "physical_tablet_runtime_verified": False,
        "adaptive_layout": adaptive_layout,
    }


def run_cycle(*, domain: str = "tablet_gpt", execute: bool = False, apply_capabilities: bool = False,
              train_meta: bool = False, apply_skills: bool = False, root: Path = ROOT,
              now: datetime | None = None, state_path: Path | None = None,
              screen_policy_model_path: Path | None = None,
              persist_outputs: bool = True, **upstream_paths: Any) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = state_path or (root / STATE_PATH.name)
    screen_model_path = screen_policy_model_path or (root / screen_neural.MODEL_PATH.name)
    cap_raw = upstream_paths.get("capability_path")
    cap_path = Path(cap_raw) if cap_raw is not None else (root / _v373().CAPABILITY_PATH.name)

    lock_api = v399.v398.v397.v391.v390.v388.v387.v386.v385
    fd = None
    if mutating:
        fd, _ = lock_api._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v400_status": "V400_CONCURRENT_AUTONOMY_HOLD",
                "execution": {"status": "V400_CONCURRENT_AUTONOMY_HOLD", "executed": False,
                              "git_write": False, "source_code_modified": False},
                "safety": SAFETY,
            }
    try:
        preview = v399.run_cycle(
            domain=domain, execute=False, apply_capabilities=False, train_meta=False, apply_skills=False,
            root=root, now=moment, persist_outputs=False, **upstream_paths,
        )
        loaded = load_state(state_file)
        portfolio = surface_portfolio(root, preview, moment)
        memory_state = update_surface_memory(loaded["state"], portfolio)
        candidates = source_feature_candidates(portfolio, memory_state["surface_memory"])
        needed_features = needed_feature_candidates(portfolio, memory_state["surface_memory"])

        upstream_gate = preview.get("v399_autonomous_gate") if isinstance(preview.get("v399_autonomous_gate"), dict) else {}
        upstream_allow = upstream_gate.get("allow_execution") is True
        caps = _load_caps(cap_path, now=moment)
        cap_corrupt = caps.get("corruption_hold") is True

        screen_backup_path = screen_neural.backup_path_for(screen_model_path)
        screen_load = screen_neural.load_model(
            screen_model_path,
            backup_path=screen_backup_path,
            now=moment,
        )
        screen_model = screen_load.get("model") if isinstance(screen_load.get("model"), dict) else None
        screen_recovery = {
            "status": "SCREEN_NEURAL_RECOVERY_NOT_REQUIRED",
            "written": False,
        }
        screen_evaluation = {
            "status": "SCREEN_NEURAL_EVALUATION_NOT_REQUESTED",
            "promote": False,
        }
        screen_training = {
            "status": (
                "SCREEN_NEURAL_CORRUPTION_HOLD"
                if screen_load.get("corruption_hold") is True
                else "SCREEN_NEURAL_TRAINING_NOT_REQUESTED"
            ),
            "written": False,
            "verified_rows": 0,
        }
        screen_rows: list[dict[str, Any]] = []
        cap_rows = list(caps.get("capabilities") or []) if not cap_corrupt else []
        cap_ids = {str(row.get("id") or "") for row in cap_rows if isinstance(row, dict)}
        evaluation = evaluate_active(loaded["state"], portfolio, cap_ids, upstream_allow=upstream_allow)

        allow = upstream_allow and not loaded.get("corruption_hold") and not cap_corrupt
        status = "PLAN_ONLY" if not mutating else (
            "V400_VERIFIED_ALLOW" if allow
            else "V400_STATE_CORRUPTION_HOLD" if loaded.get("corruption_hold")
            else "V400_CAPABILITY_CORRUPTION_HOLD" if cap_corrupt
            else "V400_UPSTREAM_HOLD"
        )

        remove_write = {"status": "V400_CAPABILITY_REMOVE_NOT_REQUESTED", "written": False, "removed": False}
        removed = False
        active = loaded["state"].get("active")
        if (mutating and apply_capabilities and allow and isinstance(active, dict)
                and (evaluation.get("rollback") is True or evaluation.get("release") is True)):
            reason = "rollback" if evaluation.get("rollback") is True else "verified_release"
            remove_write = _remove_active(active, cap_path, now=moment, reason=reason)
            removed = remove_write.get("removed") is True
            if not removed:
                allow = False
                status = "V400_CAPABILITY_ROLLBACK_HOLD"

        base = preview
        if mutating and allow:
            base = v399.run_cycle(
                domain=domain, execute=execute, apply_capabilities=apply_capabilities,
                train_meta=train_meta, apply_skills=apply_skills,
                root=root, now=moment, persist_outputs=False, **upstream_paths,
            )
            if str(base.get("v399_status") or "") in getattr(v399, "_HOLD_STATUSES", set()):
                allow = False
                status = "V400_UPSTREAM_HOLD"

        steering = steering_capability(portfolio, now=moment)
        write = {"status": "V400_CAPABILITY_NOT_REQUESTED", "written": False}
        new_cap = None
        upstream_new = ((base.get("v398_self_extension") or {}).get("new_capability")
                        if isinstance(base.get("v398_self_extension"), dict) else None)
        active_after_remove = None if removed else loaded["state"].get("active")
        if (mutating and apply_capabilities and allow and not isinstance(active_after_remove, dict)
                and upstream_new is None and isinstance(steering, dict)):
            write = _persist_capability(steering, cap_path, now=moment)
            if write.get("written") is True:
                new_cap = steering
            elif write.get("status") not in {"V400_EXPERIMENTAL_CAPABILITY_CONFLICT"}:
                allow = False
                status = "V400_CAPABILITY_WRITE_HOLD"

        if allow and screen_load.get("rollback_required") is True:
            screen_recovery = screen_neural.restore_backup(
                screen_model_path,
                backup_path=screen_backup_path,
                now=moment,
            )

        if train_meta and screen_load.get("corruption_hold") is not True:
            if allow:
                screen_rows = screen_neural.training_rows(
                    list(loaded["state"].get("history") or []),
                    current_surface_scores=_surface_scores(portfolio),
                    current_surface_confidences=_surface_confidences(portfolio),
                )
                train_rows, holdout_rows = screen_neural.split_train_holdout(screen_rows)
                candidate_model = screen_neural.train_model(
                    train_rows,
                    now=moment,
                    existing=screen_model,
                )
                if candidate_model is None:
                    screen_training = {
                        "status": "SCREEN_NEURAL_TRAINING_GATE_HELD",
                        "written": False,
                        "verified_rows": len(screen_rows),
                        "training_rows": len(train_rows),
                        "holdout_rows": len(holdout_rows),
                        "minimum_rows": screen_neural.MIN_PROMOTION_ROWS,
                    }
                else:
                    screen_evaluation = screen_neural.evaluate_challenger(
                        screen_model,
                        candidate_model,
                        train_rows,
                        holdout_rows,
                        now=moment,
                    )
                    if screen_evaluation.get("promote") is True:
                        screen_training = screen_neural.promote_challenger(
                            screen_model,
                            candidate_model,
                            screen_evaluation,
                            path=screen_model_path,
                            backup_path=screen_backup_path,
                            now=moment,
                        )
                        screen_training["verified_rows"] = len(screen_rows)
                        screen_training["training_rows"] = len(train_rows)
                        screen_training["holdout_rows"] = len(holdout_rows)
                        if screen_training.get("written") is True:
                            screen_model = candidate_model
                    else:
                        screen_training = {
                            "status": str(screen_evaluation.get("status") or "SCREEN_NEURAL_CHALLENGER_REJECT"),
                            "written": False,
                            "verified_rows": len(screen_rows),
                            "training_rows": len(train_rows),
                            "holdout_rows": len(holdout_rows),
                            "evaluation": screen_evaluation,
                        }
            else:
                screen_training = {
                    "status": "SCREEN_NEURAL_UPSTREAM_HOLD",
                    "written": False,
                    "verified_rows": 0,
                    "training_rows": 0,
                    "holdout_rows": 0,
                }

        adaptive_layout = adaptive_layout_plan(
            root, portfolio, memory_state["surface_memory"], moment,
            allow_layout=bool(allow),
            base=base,
            state=loaded["state"],
            screen_model=screen_model,
            screen_training=screen_training,
            screen_load_status=str(screen_load.get("status") or ""),
        )

        if not allow:
            adaptive_layout = {
                **adaptive_layout,
                "apply_layout": False,
                "screen_module_plan": {
                    **(adaptive_layout.get("screen_module_plan") or {}),
                    "apply_focus": False,
                },
            }

        next_state = _next_state(
            loaded["state"], memory_state, portfolio=portfolio, evaluation=evaluation,
            new_capability=new_cap, capability_removed=removed,
            adaptive_layout=adaptive_layout, now=moment,
        )

        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v400_status": status,
            "v400_surface_portfolio": portfolio,
            "v400_surface_feature_candidates": candidates,
            "v400_needed_feature_candidates": needed_features,
            "v400_surface_steering": {
                "candidate": steering, "write": write, "remove": remove_write, "new_capability": new_cap,
                "canonical_v373_allowlist_only": True, "next_cycle_only": True,
                "source_code_generated": False, "git_write": False,
            },
            "v400_active_evaluation": evaluation,
            "v400_autonomous_gate": {
                "status": status, "allow_execution": allow, "v399_gate_required": True,
                "v398_gate_required": True, "hard_blocker_override": False,
            },
            "v400_adaptive_layout": adaptive_layout,
            "v400_screen_neural": {
                "load_status": screen_load.get("status"),
                "corruption_hold": screen_load.get("corruption_hold") is True,
                "training": screen_training,
                "evaluation": screen_evaluation,
                "recovery": screen_recovery,
                "verified_training_rows": len(screen_rows),
                "champion_challenger": True,
                "holdout_validation": True,
                "challenger_must_improve": True,
                "input_drift_hold": True,
                "backup_path": screen_backup_path.name,
                "active": bool(
                    ((adaptive_layout.get("policy_learning") or {}).get("screen_neural") or {}).get("active")
                    if isinstance(adaptive_layout.get("policy_learning"), dict)
                    else False
                ),
                "model_path": screen_model_path.name,
                "user_behavior_tracking": False,
                "source_code_generated": False,
                "git_write": False,
            },
            "v400_ui": {
                **_dashboard_summary(base, portfolio, evaluation, candidates, adaptive_layout),
                "needed_feature_candidates": needed_features,
                "protected_needed_feature_candidates": sum(
                    row.get("stage") == "protected_pr_candidate" for row in needed_features
                ),
            },
            "evolution_contract_v400": {
                "core": "v399_cross_surface_plus_v398_verified_multi_candidate_self_evolution",
                "surfaces": list(SURFACES),
                "selection": "verified_operational_deficit_and_evidence_gap_only",
                "runtime_self_extension": "one_bounded_v400_owned_canonical_v373_capability_next_cycle_only",
                "runtime_self_extension_conflicts_with_v397_v398": True,
                "surface_canary": "score_delta_verified_release_or_exact_rollback",
                "source_level_extension": "non_executable_protected_pr_ci_candidate_only",
                "market_adaptation": "freshness_coverage_source_health_and_non_directional_activity_only",
                "adaptive_ui_composition": "verified_scored_category_shortcut_and_existing_screen_target_focus_with_user_override_and_restore",
                "autonomous_needed_feature_selection": "verified_surface_gap_to_protected_pr_candidate_only",
                "meta_neural_screen_policy": "existing_v373_verified_outcome_neural_scores_bounded_advisory_bias_only",
                "screen_policy_neural_adapter": "v401_17_input_12_hidden_18_output_verified_surface_outcomes_only_bounded_advisory",
                "screen_policy_neural_training": "confidence_qualified_verified_outcomes_with_champion_challenger_holdout_validation_and_drift_hold",
                "screen_policy_neural_promotion": "challenger_must_beat_champion_or_zero_baseline_before_transactional_promotion",
                "screen_policy_neural_rollback": "last_valid_champion_backup_recovery_without_source_or_git_mutation",
                "video_reference_v404": "two_stage_region_capture_readiness_hot_evidence_confidence_portfolio_economics_existing_results_only",
                "verified_outcome_screen_learning": "prior_applied_plan_to_later_surface_score_weak_feedback_next_cycle_only",
                "purchase_availability": "source_freshness_link_health_coverage_only_stock_confirmation_required",
                "tablet_ops": "runtime_assets_and_current_verification_only_physical_device_unverified",
                "source_code_auto_generation": False, "source_code_auto_rewrite": False,
                "direct_git_or_main_write": False, "price_or_grade_invention": False,
                "release_fact_invention": False, "event_fact_invention": False, "v399_v398_and_prior_gate_bypass": False,
            },
            "safety": SAFETY,
        })

        if mutating and not allow:
            result["execution"] = {"status": status, "executed": False, "git_write": False,
                                   "source_code_modified": False, "proposals_executed": False}

        state_write = {"status": "V400_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            state_write = save_state(next_state, state_file, corruption_hold=bool(loaded.get("corruption_hold")))
            if not state_write.get("written"):
                if new_cap is not None:
                    _remove_active({
                        "id": new_cap["id"],
                        "surface": str(portfolio.get("selected_surface") or "ui"),
                        "primitive": new_cap["primitive"],
                        "baseline_score": float(portfolio.get("selected_score") or 0.0),
                        "activated_cycle": int(next_state["cycle"]),
                    }, cap_path, now=moment, reason="state_commit_rollback")
                result["v400_status"] = "V400_STATE_COMMIT_HOLD"
                result["v400_autonomous_gate"] = {
                    **result["v400_autonomous_gate"], "status": "V400_STATE_COMMIT_HOLD", "allow_execution": False,
                }
                result["execution"] = {"status": "V400_STATE_COMMIT_HOLD", "executed": False,
                                       "git_write": False, "source_code_modified": False,
                                       "proposals_executed": False}
        result["v400_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(
                    root / SURFACE_CANDIDATE_PATH.name,
                    {"schema_version": 1, "controller_version": CONTROLLER_VERSION,
                     "generated_at": moment.isoformat(timespec="seconds"),
                     "portfolio": portfolio, "candidates": candidates,
                     "needed_features": needed_features, "auto_execute": False,
                     "auto_generate_source": False, "auto_rewrite_source": False,
                     "git_write": False, "protected_pr_ci_required": True},
                    suffix=".v400-surface-candidates.tmp",
                )
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v400-report.tmp")
                result["v400_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v400_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result
    finally:
        if fd is not None:
            lock_api._release_lock(fd)


def self_test() -> None:
    assert _valid_state(_default_state())
    assert SAFETY["ui_card_measurement_market_event_governance_enabled"] is True
    assert SAFETY["missing_surface_evidence_triggers_revalidation"] is True
    assert SAFETY["current_runtime_verification_preferred"] is True
    assert SAFETY["historical_v109_audit_fallback_only"] is True
    assert SAFETY["surface_runtime_self_extension_allowlisted_only"] is True
    assert SAFETY["surface_source_feature_candidates_non_executable"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["card_measurement_grade_invention"] is False
    assert SAFETY["card_market_price_invention"] is False
    assert SAFETY["card_release_fact_invention"] is False
    assert SAFETY["event_fact_invention"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["adaptive_ui_composition_enabled"] is True
    assert SAFETY["adaptive_ui_user_override_required"] is True
    assert SAFETY["adaptive_feature_shortcuts_enabled"] is True
    assert SAFETY["adaptive_feature_shortcuts_existing_dom_only"] is True
    assert SAFETY["adaptive_screen_modules_existing_targets_only"] is True
    assert SAFETY["adaptive_feature_priority_scoring_enabled"] is True
    assert SAFETY["autonomous_needed_feature_selection_enabled"] is True
    assert SAFETY["autonomous_needed_feature_runtime_generation"] is False
    assert SAFETY["meta_neural_screen_policy_enabled"] is True
    assert SAFETY["meta_neural_screen_policy_verified_outcomes_only"] is True
    assert SAFETY["meta_neural_screen_policy_advisory_only"] is True
    assert SAFETY["verified_surface_outcome_feedback_enabled"] is True
    assert SAFETY["verified_surface_outcome_feedback_no_user_behavior_tracking"] is True
    assert SAFETY["screen_policy_neural_adapter_enabled"] is True
    assert SAFETY["screen_policy_neural_verified_outcomes_only"] is True
    assert SAFETY["screen_policy_neural_allowlisted_features_only"] is True
    assert SAFETY["screen_policy_neural_advisory_only"] is True
    assert SAFETY["screen_policy_neural_user_behavior_tracking"] is False
    assert SAFETY["screen_policy_neural_champion_challenger_required"] is True
    assert SAFETY["screen_policy_neural_holdout_validation_required"] is True
    assert SAFETY["screen_policy_neural_challenger_must_improve"] is True
    assert SAFETY["screen_policy_neural_input_drift_hold_required"] is True
    assert SAFETY["screen_policy_neural_backup_rollback_required"] is True
    assert SAFETY["screen_policy_neural_transactional_promotion"] is True
    assert SAFETY["video_reference_experience_module_confidence_required"] is True
    assert SAFETY["video_reference_experience_low_confidence_revalidation_required"] is True
    assert SAFETY["video_reference_experience_region_drilldown_strings_only"] is True
    assert SAFETY["video_reference_experience_capture_readiness_structured"] is True
    assert SAFETY["video_reference_experience_portfolio_economics_existing_results_only"] is True
    assert SAFETY["screen_policy_neural_source_generation"] is False
    assert SAFETY["video_reference_experience_enabled"] is True
    assert SAFETY["video_reference_experience_allowlisted_modules_only"] is True
    assert SAFETY["video_reference_experience_verified_data_only"] is True
    assert SAFETY["video_reference_experience_market_direction_invention"] is False
    assert SAFETY["video_reference_experience_stock_fact_invention"] is False
    assert SAFETY["video_reference_experience_precise_location_persistence"] is False
    assert SAFETY["video_reference_experience_user_behavior_tracking"] is False
    assert len(VIDEO_EXPERIENCE_MODULES) == 5
    assert set(screen_neural.FEATURE_KEYS) == set(FEATURE_TARGETS)
    assert set(screen_neural.FEATURE_SURFACE) == set(FEATURE_TARGETS)
    assert CATEGORY_ORDER[0] == "grading"
    assert SAFETY["stock_fact_invention"] is False
    print("Tablet domain-aware verified self-evolution supervisor v400 adaptive UI: PASS")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--domain", choices=sorted(v399.v398.v397.v391.v390.v388.v387.v386.DOMAINS), default="tablet_gpt")
    p.add_argument("--execute-safe-learning", action="store_true")
    p.add_argument("--apply-capabilities", action="store_true")
    p.add_argument("--train-meta", action="store_true")
    p.add_argument("--apply-skills", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(
        domain=args.domain, execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities, train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v400_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
