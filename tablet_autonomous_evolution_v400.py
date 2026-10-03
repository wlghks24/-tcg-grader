#!/usr/bin/env python3
"""V400 domain-aware self-evolution supervisor for Tablet GPT.

V400 preserves V399/V398 as mandatory upstream governors and adds explicit,
evidence-bounded autonomy across four user-facing surfaces:

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

SURFACES = ("ui", "card_measurement", "card_market", "card_release", "collab_event")

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
    checks = [
        ("dashboard_js_file", bool(js), True),
        ("dashboard_css_file", bool(css), True),
        ("index_dashboard_css", "tablet_autonomy_dashboard_v400.css" in index, True),
        ("index_dashboard_js", "tablet_autonomy_dashboard_v400.js" in index, True),
        ("dashboard_report_binding", "tablet_autonomy_v400_report.json" in js, True),
        ("dashboard_accessibility", "aria-live" in js and "prefers-reduced-motion" in css, False),
        ("pwa_dashboard_assets", "tablet_autonomy_dashboard_v400.js" in sw and "tablet_autonomy_dashboard_v400.css" in sw, True),
        ("static_report_exposure", "tablet_autonomy_v400_report.json" in updater, True),
        ("runtime_manifest_controller", "tablet_autonomous_evolution_v400.py" in manifest, True),
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


def surface_portfolio(root: Path, base: dict[str, Any], now: datetime) -> dict[str, Any]:
    rows = [
        ui_surface(root),
        card_measurement_surface(root, now),
        card_market_surface(root, now),
        card_release_surface(root, now),
        collab_event_surface(root, now),
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
                capability_removed: bool, now: datetime) -> dict[str, Any]:
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
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": result["cycle"],
        "selected_surface": portfolio.get("selected_surface"),
        "selected_urgency": portfolio.get("selected_urgency"),
        "active_capability": active.get("id") if isinstance(active, dict) else None,
        "active_surface": active.get("surface") if isinstance(active, dict) else None,
        "evaluation": evaluation.get("status"),
        "score_delta": evaluation.get("score_delta"),
    })
    result["history"] = history[-MAX_HISTORY:]
    return result


def _dashboard_summary(base: dict[str, Any], portfolio: dict[str, Any], evaluation: dict[str, Any],
                       candidates: list[dict[str, Any]]) -> dict[str, Any]:
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
    }


def run_cycle(*, domain: str = "tablet_gpt", execute: bool = False, apply_capabilities: bool = False,
              train_meta: bool = False, apply_skills: bool = False, root: Path = ROOT,
              now: datetime | None = None, state_path: Path | None = None,
              persist_outputs: bool = True, **upstream_paths: Any) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = state_path or (root / STATE_PATH.name)
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

        upstream_gate = preview.get("v399_autonomous_gate") if isinstance(preview.get("v399_autonomous_gate"), dict) else {}
        upstream_allow = upstream_gate.get("allow_execution") is True
        caps = _load_caps(cap_path, now=moment)
        cap_corrupt = caps.get("corruption_hold") is True
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

        next_state = _next_state(
            loaded["state"], memory_state, portfolio=portfolio, evaluation=evaluation,
            new_capability=new_cap, capability_removed=removed, now=moment,
        )

        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v400_status": status,
            "v400_surface_portfolio": portfolio,
            "v400_surface_feature_candidates": candidates,
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
            "v400_ui": _dashboard_summary(base, portfolio, evaluation, candidates),
            "evolution_contract_v400": {
                "core": "v399_cross_surface_plus_v398_verified_multi_candidate_self_evolution",
                "surfaces": list(SURFACES),
                "selection": "verified_operational_deficit_and_evidence_gap_only",
                "runtime_self_extension": "one_bounded_v400_owned_canonical_v373_capability_next_cycle_only",
                "runtime_self_extension_conflicts_with_v397_v398": True,
                "surface_canary": "score_delta_verified_release_or_exact_rollback",
                "source_level_extension": "non_executable_protected_pr_ci_candidate_only",
                "market_adaptation": "freshness_coverage_source_health_only_no_direction_prediction",
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
                     "portfolio": portfolio, "candidates": candidates, "auto_execute": False,
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
    print("Tablet domain-aware verified self-evolution supervisor v400: PASS")


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
