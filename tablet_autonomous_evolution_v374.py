#!/usr/bin/env python3
"""Closed-loop autonomous evolution for Tablet GPT / TCG Grader.

V374 extends v373 with a bounded self-evolution loop:
observe -> detect gaps -> generate candidates -> score benefit/risk/cost/history ->
select at most one runtime skill -> execute only existing verified safe-learning ->
verify next-cycle operational outcome -> keep/suspend/rollback declarative skills.

Runtime self-added functions are composable declarative skills built only from
v373 capability primitives. Source-code changes are never generated/executed
by the tablet runtime; persistent source-level gaps are emitted as evidence-
backed proposals for the normal branch/PR/CI path.

No card facts, grades, prices, market direction, trust, or verification state
are invented by this controller.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v373 as v373
from safe_runtime import atomic_write_json, atomic_write_text, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v374"
SCHEMA_VERSION = 4

SKILL_STATE_PATH = ROOT / "tablet_autonomy_skills_v374.json"
OUTCOMES_PATH = ROOT / "tablet_autonomy_verified_skill_outcomes_v374.jsonl"
SOURCE_PROPOSALS_PATH = ROOT / "tablet_autonomy_source_feature_proposals_v374.json"
REPORT_PATH = ROOT / "tablet_autonomy_v374_report.json"

MAX_ACTIVE_SKILLS = 16
MAX_PENDING_TRIALS = 8
MAX_OUTCOMES = 2_000
MAX_OUTCOME_BYTES = 4_000_000
MAX_SOURCE_PROPOSALS = 32
SKILL_TTL_SECONDS = 24 * 60 * 60
TRIAL_TTL_SECONDS = 24 * 60 * 60
MIN_HISTORY_TO_BLOCK = 3
NEGATIVE_MEAN_BLOCK = -0.25
MAX_REGRESSION_RATE = 0.34
MIN_SELECTION_SCORE = 20.0
MAX_SKILL_PRIORITY_DELTA = 15

SKILL_RECIPES: dict[str, dict[str, Any]] = {
    "RECOVER_FRESHNESS": {"risk": 0.08, "cost": 0.15, "gap_kinds": {"market_freshness"}},
    "EXPAND_REGION_COVERAGE": {"risk": 0.10, "cost": 0.18, "gap_kinds": {"region_coverage"}},
    "RECOVER_SOURCE_HEALTH": {"risk": 0.15, "cost": 0.22, "gap_kinds": {"source_health"}},
    "RECOVER_MODEL": {"risk": 0.12, "cost": 0.28, "gap_kinds": {"query_model", "job_model", "repair_model"}},
    "OBSERVE_ONLY": {"risk": 0.01, "cost": 0.04, "gap_kinds": {"sync_health", "state_integrity", "unknown_gap"}},
}

SAFETY = dict(v373.SAFETY)
SAFETY.update({
    "closed_loop_candidate_generation": True,
    "multi_candidate_scoring": True,
    "one_runtime_skill_per_cycle": True,
    "max_heavy_operations_per_cycle": 1,
    "operational_refresh_existing_updater_only": True,
    "verified_skill_outcome_learning_only": True,
    "objective_next_cycle_trial_evaluation": True,
    "negative_history_auto_suspends_skill": True,
    "declarative_skill_auto_composition": True,
    "declarative_skill_allowlisted_primitives_only": True,
    "source_level_gap_proposals_allowed": True,
    "source_level_gap_auto_implementation": False,
    "source_level_gap_requires_normal_pr_ci": True,
    "market_operational_regime_adaptation": True,
    "market_direction_inferred": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_generation": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "price_or_grade_invention": False,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    return v373._parse_time(value)


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _read_json(path: Path, *, max_bytes: int = 1_000_000) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.is_symlink():
            return None
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def operational_snapshot(plan: dict[str, Any]) -> dict[str, Any]:
    """Return bounded non-factual operational metrics for closed-loop trials."""
    market = plan.get("market_profile") if isinstance(plan.get("market_profile"), dict) else {}
    freshness = market.get("freshness") if isinstance(market.get("freshness"), dict) else {}
    signals = plan.get("signals") if isinstance(plan.get("signals"), dict) else {}
    runtime = signals.get("runtime_models") if isinstance(signals.get("runtime_models"), dict) else {}
    models = runtime.get("models") if isinstance(runtime.get("models"), dict) else {}
    repair = signals.get("repair_neural") if isinstance(signals.get("repair_neural"), dict) else {}

    def status(name: str) -> str:
        row = models.get(name) if isinstance(models.get(name), dict) else {}
        return str(row.get("status") or "unknown")[:32]

    ratio = _finite(market.get("degraded_source_ratio"))
    low = market.get("low_coverage_regions")
    return {
        "freshness": str(freshness.get("status") or "unknown")[:32],
        "low_coverage_regions": sorted(
            {str(x) for x in low if str(x) in {"KR", "JP", "US"}}
        ) if isinstance(low, list) else ["JP", "KR", "US"],
        "degraded_source_ratio": round(_clamp(ratio, 0.0, 1.0), 6) if ratio is not None else None,
        "query_model_status": status("query_strategy"),
        "job_model_status": status("job_strategy"),
        "repair_requires_attention": repair.get("requires_attention") is True,
        "resource_status": str((plan.get("resources") or {}).get("status") or "unknown")
        if isinstance(plan.get("resources"), dict) else "unknown",
        "state_corruption_hold": plan.get("state_corruption_hold") is True,
    }


def detect_gaps(plan: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = operational_snapshot(plan)
    gaps: list[dict[str, Any]] = []
    if snapshot["state_corruption_hold"]:
        gaps.append({"gap_id": "state_integrity", "kind": "state_integrity", "severity": 1.0,
                     "confidence": 1.0, "evidence": {"state_corruption_hold": True}})
    if snapshot["freshness"] != "fresh":
        gaps.append({"gap_id": "market_freshness", "kind": "market_freshness", "severity": 1.0,
                     "confidence": 1.0, "evidence": {"freshness": snapshot["freshness"]}})
    for region in snapshot["low_coverage_regions"]:
        gaps.append({"gap_id": f"region_coverage:{region}", "kind": "region_coverage", "region": region,
                     "severity": 0.72, "confidence": 0.95,
                     "evidence": {"region": region, "low_coverage": True}})
    ratio = snapshot["degraded_source_ratio"]
    if isinstance(ratio, (int, float)) and ratio > 0.35:
        gaps.append({"gap_id": "source_health", "kind": "source_health",
                     "severity": round(_clamp(0.55 + ratio * 0.45, 0.0, 1.0), 6),
                     "confidence": 0.95, "evidence": {"degraded_source_ratio": ratio}})
    for kind, key, action in (
        ("query_model", "query_model_status", "TRAIN_QUERY_STRATEGY"),
        ("job_model", "job_model_status", "TRAIN_JOB_STRATEGY"),
    ):
        if snapshot[key] in {"broken", "degraded"}:
            gaps.append({"gap_id": kind, "kind": kind, "safe_learning_action": action,
                         "severity": 0.85 if snapshot[key] == "broken" else 0.65,
                         "confidence": 1.0, "evidence": {"status": snapshot[key]}})
    if snapshot["repair_requires_attention"]:
        gaps.append({"gap_id": "repair_model", "kind": "repair_model",
                     "safe_learning_action": "TRAIN_REPAIR_PRIORITY", "severity": 0.75,
                     "confidence": 1.0, "evidence": {"requires_attention": True}})
    if not gaps:
        gaps.append({"gap_id": "sync_health", "kind": "sync_health", "severity": 0.10,
                     "confidence": 1.0, "evidence": {"reason": "healthy_observation"}})
    return gaps


def load_verified_skill_outcomes(*, path: Path = OUTCOMES_PATH) -> list[dict[str, Any]]:
    try:
        if not path.is_file() or path.is_symlink():
            return []
        text = safe_read_text(path, max_bytes=MAX_OUTCOME_BYTES)
    except (OSError, UnicodeError, ValueError, TypeError):
        return []
    rows: list[dict[str, Any]] = []
    for raw in text.splitlines()[-MAX_OUTCOMES:]:
        try:
            row = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("verified") is not True:
            continue
        recipe = str(row.get("recipe") or "")
        reward = _finite(row.get("reward"))
        evidence = str(row.get("evidence_ref") or "").strip()
        if recipe not in SKILL_RECIPES or reward is None or not evidence:
            continue
        rows.append({
            "recipe": recipe,
            "skill_id": str(row.get("skill_id") or "")[:128],
            "reward": _clamp(reward, -1.0, 1.0),
            "regression_detected": row.get("regression_detected") is True,
            "evidence_ref": evidence[:240],
            "verified_at": str(row.get("verified_at") or "")[:64],
        })
    return rows


def skill_history_stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in SKILL_RECIPES}
    for row in rows:
        if row.get("recipe") in grouped:
            grouped[str(row["recipe"])].append(row)
    result: dict[str, dict[str, Any]] = {}
    for recipe, group in grouped.items():
        rewards = [float(row["reward"]) for row in group]
        samples = len(rewards)
        mean = sum(rewards) / samples if samples else 0.0
        regressions = sum(1 for row in group if row.get("regression_detected") is True)
        rate = regressions / samples if samples else 0.0
        blocked = samples >= MIN_HISTORY_TO_BLOCK and (
            mean <= NEGATIVE_MEAN_BLOCK or rate >= MAX_REGRESSION_RATE
        )
        result[recipe] = {
            "samples": samples,
            "mean_reward": round(_clamp(mean, -1.0, 1.0), 6),
            "regression_count": regressions,
            "regression_rate": round(rate, 6),
            "blocked": blocked,
        }
    return result


def _recipe_for_gap(gap: dict[str, Any]) -> str:
    kind = str(gap.get("kind") or "")
    if kind == "market_freshness":
        return "RECOVER_FRESHNESS"
    if kind == "region_coverage":
        return "EXPAND_REGION_COVERAGE"
    if kind == "source_health":
        return "RECOVER_SOURCE_HEALTH"
    if kind in {"query_model", "job_model", "repair_model"}:
        return "RECOVER_MODEL"
    return "OBSERVE_ONLY"


def generate_candidates(
    plan: dict[str, Any],
    gaps: list[dict[str, Any]],
    history: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    resources = plan.get("resources") if isinstance(plan.get("resources"), dict) else {}
    normal_resource = resources.get("status") == "normal"
    candidates: list[dict[str, Any]] = []
    for gap in gaps:
        recipe = _recipe_for_gap(gap)
        spec = SKILL_RECIPES[recipe]
        severity = _clamp(float(_finite(gap.get("severity")) or 0.0), 0.0, 1.0)
        confidence = _clamp(float(_finite(gap.get("confidence")) or 0.0), 0.0, 1.0)
        stat = history.get(recipe) or {
            "samples": 0, "mean_reward": 0.0, "regression_rate": 0.0, "blocked": False
        }
        empirical = _clamp(float(_finite(stat.get("mean_reward")) or 0.0), -1.0, 1.0)
        risk = float(spec["risk"])
        cost = float(spec["cost"])
        benefit = severity * confidence
        score = 100.0 * (
            0.62 * benefit
            + 0.18 * max(-0.5, empirical)
            + 0.10 * (1.0 - risk)
            + 0.10 * (1.0 - cost)
        )
        if stat.get("samples", 0) == 0:
            score -= 4.0
        blocked = bool(stat.get("blocked"))
        if blocked:
            score = 0.0
        suffix = str(gap.get("region") or gap.get("safe_learning_action") or gap.get("gap_id") or "DEFAULT")
        suffix = "".join(ch for ch in suffix.upper() if ch.isalnum() or ch in "_-")[:64]
        candidate = {
            "skill_id": f"{recipe}:{suffix or 'DEFAULT'}",
            "recipe": recipe,
            "gap_id": str(gap.get("gap_id") or "")[:128],
            "kind": str(gap.get("kind") or "")[:64],
            "region": str(gap.get("region") or "")[:8] or None,
            "safe_learning_action": str(gap.get("safe_learning_action") or "")[:64] or None,
            "score": round(_clamp(score, 0.0, 100.0), 6),
            "severity": round(severity, 6),
            "confidence": round(confidence, 6),
            "risk": risk,
            "cost": cost,
            "history": stat,
            "resource_eligible": normal_resource or recipe == "OBSERVE_ONLY",
            "blocked_by_verified_history": blocked,
            "source_code_change": False,
            "arbitrary_command": False,
            "market_direction_inferred": False,
            "evidence": dict(gap.get("evidence") or {}),
        }
        candidates.append(candidate)
    candidates.sort(key=lambda row: (-float(row["score"]), float(row["risk"]), str(row["skill_id"])))
    return candidates


def select_candidate(
    plan: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    skill_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Choose one candidate without overlapping an unresolved trial.

    Pending trials are causal verification windows. Re-running the same recipe
    before its outcome is observable would contaminate attribution, so that
    recipe stays on hold until the trial resolves or expires.
    """
    state = skill_state if isinstance(skill_state, dict) else {}
    pending = state.get("pending_trials") if isinstance(state.get("pending_trials"), list) else []
    suspended = {
        str(item) for item in state.get("suspended_recipes", [])
        if str(item) in SKILL_RECIPES
    }
    pending_recipes = {
        str(row.get("recipe") or "") for row in pending
        if isinstance(row, dict) and str(row.get("recipe") or "") in SKILL_RECIPES
    }
    market_recipes = {"RECOVER_FRESHNESS", "EXPAND_REGION_COVERAGE", "RECOVER_SOURCE_HEALTH"}
    market_trial_pending = bool(pending_recipes & market_recipes)

    if plan.get("state_corruption_hold") is True:
        return next(
            (
                dict(row) for row in candidates
                if row["recipe"] == "OBSERVE_ONLY"
                and row["recipe"] not in suspended
                and row["recipe"] not in pending_recipes
            ),
            None,
        )
    for row in candidates:
        recipe = str(row.get("recipe") or "")
        if recipe in suspended or recipe in pending_recipes:
            continue
        if market_trial_pending and recipe in market_recipes:
            continue
        if row.get("blocked_by_verified_history") is True:
            continue
        if row.get("resource_eligible") is not True:
            continue
        if float(row.get("score") or 0.0) < MIN_SELECTION_SCORE:
            continue
        return dict(row)
    return None


def skill_capabilities(skill: dict[str, Any] | None, *, now: datetime | None = None) -> list[dict[str, Any]]:
    if not isinstance(skill, dict):
        return []
    moment = (now or _now()).astimezone(timezone.utc)
    recipe = str(skill.get("recipe") or "")
    rows: list[dict[str, Any]] = []
    evidence = {"reason": "v374_selected_skill", "skill_id": skill["skill_id"]}

    if recipe == "RECOVER_FRESHNESS":
        rows.extend([
            v373._capability("REQUEST_FRESHNESS_REFRESH", "V374", {"max_runs": 1}, evidence, now=moment),
            v373._capability("INCREASE_OBSERVATION", "V374_FRESHNESS",
                             {"scope": "market_health", "factor": 1.35}, evidence, now=moment),
        ])
    elif recipe == "EXPAND_REGION_COVERAGE":
        region = str(skill.get("region") or "")
        if region in {"KR", "JP", "US"}:
            rows.extend([
                v373._capability("PRIORITIZE_REGION", region,
                                 {"region": region, "boost": 0.13}, evidence, now=moment),
                v373._capability("INCREASE_OBSERVATION", f"V374_{region}",
                                 {"scope": "market_health", "factor": 1.25}, evidence, now=moment),
            ])
    elif recipe == "RECOVER_SOURCE_HEALTH":
        rows.extend([
            v373._capability("RETRY_DEGRADED_SOURCES", "V374",
                             {"max_retry": 2, "backoff_seconds": 120}, evidence, now=moment),
            v373._capability("INCREASE_OBSERVATION", "V374_SOURCE_HEALTH",
                             {"scope": "market_health", "factor": 1.25}, evidence, now=moment),
        ])
    elif recipe == "RECOVER_MODEL":
        action = str(skill.get("safe_learning_action") or "")
        if action in v373.v372.SAFE_LEARNING_ACTIONS:
            rows.extend([
                v373._capability("PRIORITIZE_SAFE_LEARNING", action,
                                 {"action_id": action, "boost": 0.12}, evidence, now=moment),
                v373._capability("INCREASE_OBSERVATION", "V374_RUNTIME_MODEL",
                                 {"scope": "runtime_models", "factor": 1.25}, evidence, now=moment),
            ])
    elif recipe == "OBSERVE_ONLY":
        rows.append(v373._capability("INCREASE_OBSERVATION", "V374_OBSERVE_ONLY",
                                     {"scope": "sync_health", "factor": 1.20}, evidence, now=moment))
    return [row for row in rows if v373.validate_capability(row, now=moment)]


def evolve_plan(
    plan: dict[str, Any],
    selected_skill: dict[str, Any] | None,
    capabilities: list[dict[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(plan)
    actions = [dict(row) for row in result.get("actions", []) if isinstance(row, dict)]
    boosts = v373.capability_priority_boosts(capabilities)
    for row in actions:
        action_id = str(row.get("id") or "")
        base = int(row.get("adaptive_priority", row.get("priority", 0)) or 0)
        delta = int(round(_clamp(boosts.get(action_id, 0.0), 0.0, v373.MAX_OPERATIONAL_BOOST) * 100))
        row["v374_skill_priority_delta"] = min(MAX_SKILL_PRIORITY_DELTA, max(0, delta))
        row["v374_priority"] = base + row["v374_skill_priority_delta"]
    actions.sort(key=lambda row: (-int(row.get("v374_priority", 0)), str(row.get("id") or "")))
    result["actions"] = actions
    result["v374_selected_skill"] = deepcopy(selected_skill)
    result["v374_active_capabilities"] = deepcopy(capabilities)

    budget = int(result.get("training_budget") or 0)
    eligible = set(result.get("safe_learning_candidates") or []) & set(v373.v372.SAFE_LEARNING_ACTIONS)
    if budget > 0 and eligible and selected_skill and selected_skill.get("recipe") == "RECOVER_MODEL":
        requested = str(selected_skill.get("safe_learning_action") or "")
        result["selected_safe_learning_actions"] = [requested] if requested in eligible else []
    elif selected_skill and selected_skill.get("recipe") in {
        "RECOVER_FRESHNESS", "EXPAND_REGION_COVERAGE", "RECOVER_SOURCE_HEALTH", "OBSERVE_ONLY"
    }:
        # One heavy operation per cycle: market/observation skills suppress model training.
        result["selected_safe_learning_actions"] = []
    elif budget <= 0:
        result["selected_safe_learning_actions"] = []
    else:
        existing = result.get("selected_safe_learning_actions")
        result["selected_safe_learning_actions"] = (
            [str(x) for x in existing if str(x) in v373.v372.SAFE_LEARNING_ACTIONS][:1]
            if isinstance(existing, list) else []
        )
    return result


def execute_operational_skill(
    skill: dict[str, Any] | None,
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Execute at most one existing bounded operational updater; never shell/Git/code."""
    if not isinstance(skill, dict):
        return {"status": "NO_OPERATIONAL_SKILL", "executed": False}
    recipe = str(skill.get("recipe") or "")
    if recipe in {"RECOVER_MODEL", "OBSERVE_ONLY"}:
        return {"status": "NO_OPERATIONAL_MUTATION", "executed": False, "recipe": recipe}
    resources = plan.get("resources") if isinstance(plan.get("resources"), dict) else {}
    if resources.get("status") != "normal":
        return {"status": "RESOURCE_HOLD", "executed": False, "recipe": recipe}
    if recipe not in {"RECOVER_FRESHNESS", "EXPAND_REGION_COVERAGE", "RECOVER_SOURCE_HEALTH"}:
        return {"status": "UNSUPPORTED_OPERATIONAL_SKILL", "executed": False, "recipe": recipe}
    try:
        import tcg_updater
        result = tcg_updater.update_cycle("tablet-v374-autonomous-refresh")
    except Exception as exc:
        return {
            "status": "OPERATIONAL_REFRESH_FAILED",
            "executed": True,
            "recipe": recipe,
            "error_code": type(exc).__name__,
            "git_write": False,
            "source_code_modified": False,
        }
    return {
        "status": "OPERATIONAL_REFRESH_EXECUTED",
        "executed": True,
        "recipe": recipe,
        "result": result if isinstance(result, dict) else {"status": "invalid_updater_result"},
        "git_write": False,
        "source_code_modified": False,
    }


def _default_skill_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "updated_at": None,
        "active_skills": [],
        "pending_trials": [],
        "suspended_recipes": [],
    }


def validate_skill_state(value: Any, *, now: datetime | None = None) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != SCHEMA_VERSION or value.get("controller_version") != CONTROLLER_VERSION:
        return False
    active = value.get("active_skills")
    pending = value.get("pending_trials")
    suspended = value.get("suspended_recipes")
    if not isinstance(active, list) or len(active) > MAX_ACTIVE_SKILLS:
        return False
    if not isinstance(pending, list) or len(pending) > MAX_PENDING_TRIALS:
        return False
    if not isinstance(suspended, list) or any(str(x) not in SKILL_RECIPES for x in suspended):
        return False
    moment = (now or _now()).astimezone(timezone.utc)
    for row in active:
        if not isinstance(row, dict) or str(row.get("recipe") or "") not in SKILL_RECIPES:
            return False
        created = _parse_time(row.get("created_at"))
        expires = _parse_time(row.get("expires_at"))
        if created is None or expires is None or created > moment + timedelta(minutes=5):
            return False
        if expires <= created or expires - created > timedelta(seconds=SKILL_TTL_SECONDS):
            return False
    for row in pending:
        if not isinstance(row, dict) or str(row.get("recipe") or "") not in SKILL_RECIPES:
            return False
        created = _parse_time(row.get("created_at"))
        expires = _parse_time(row.get("expires_at"))
        if created is None or expires is None or created > moment + timedelta(minutes=5):
            return False
        if expires <= created or expires - created > timedelta(seconds=TRIAL_TTL_SECONDS):
            return False
        if not isinstance(row.get("before"), dict):
            return False
    return True


def load_skill_state(*, path: Path = SKILL_STATE_PATH, now: datetime | None = None) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    raw = _read_json(path, max_bytes=1_000_000)
    if raw is None:
        existed = path.exists() and not path.is_symlink()
        return {
            "state": _default_skill_state(),
            "status": "corrupt" if existed else "fresh",
            "corruption_hold": existed,
        }
    if not validate_skill_state(raw, now=moment):
        return {"state": _default_skill_state(), "status": "corrupt", "corruption_hold": True}
    clean = deepcopy(raw)
    clean["active_skills"] = [
        row for row in clean["active_skills"]
        if (_parse_time(row["expires_at"]) or moment) > moment
    ]
    return {"state": clean, "status": "loaded", "corruption_hold": False}


def save_skill_state(
    state: dict[str, Any],
    *,
    path: Path = SKILL_STATE_PATH,
    corruption_hold: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    if corruption_hold:
        return {"status": "SKILL_STATE_CORRUPTION_HOLD", "written": False}
    payload = deepcopy(state)
    payload["schema_version"] = SCHEMA_VERSION
    payload["controller_version"] = CONTROLLER_VERSION
    payload["updated_at"] = moment.isoformat(timespec="seconds")
    if not validate_skill_state(payload, now=moment):
        return {"status": "INVALID_SKILL_STATE", "written": False}
    try:
        atomic_write_json(path, payload, suffix=".v374-skill-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "SKILL_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "SKILL_STATE_SAVED", "written": True}


def _trial_for_skill(skill: dict[str, Any], plan: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    return {
        "skill_id": str(skill["skill_id"]),
        "recipe": str(skill["recipe"]),
        "gap_id": str(skill.get("gap_id") or "")[:128],
        "region": skill.get("region"),
        "safe_learning_action": skill.get("safe_learning_action"),
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(seconds=TRIAL_TTL_SECONDS)).isoformat(timespec="seconds"),
        "before": operational_snapshot(plan),
    }


def evaluate_trial(
    trial: dict[str, Any],
    plan: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    moment = (now or _now()).astimezone(timezone.utc)
    recipe = str(trial.get("recipe") or "")
    before = trial.get("before") if isinstance(trial.get("before"), dict) else {}
    after = operational_snapshot(plan)
    expires = _parse_time(trial.get("expires_at"))
    expired = expires is not None and expires <= moment
    reward: float | None = None
    regression = False
    reason = ""

    if after.get("state_corruption_hold") is True:
        reward, regression, reason = -1.0, True, "state_corruption_hold"
    elif recipe == "RECOVER_FRESHNESS":
        if before.get("freshness") != "fresh" and after.get("freshness") == "fresh":
            reward, reason = 1.0, "freshness_recovered"
        elif expired:
            reward, reason = -0.20, "freshness_not_recovered_before_ttl"
    elif recipe == "EXPAND_REGION_COVERAGE":
        region = str(trial.get("region") or "")
        before_low = set(before.get("low_coverage_regions") or [])
        after_low = set(after.get("low_coverage_regions") or [])
        if region and region in before_low and region not in after_low:
            reward, reason = 1.0, "region_coverage_recovered"
        elif expired:
            reward, reason = -0.15, "region_coverage_not_recovered_before_ttl"
    elif recipe == "RECOVER_SOURCE_HEALTH":
        b = _finite(before.get("degraded_source_ratio"))
        a = _finite(after.get("degraded_source_ratio"))
        if b is not None and a is not None and a <= max(0.0, b - 0.10):
            reward, reason = 0.9, "source_health_improved"
        elif b is not None and a is not None and a >= min(1.0, b + 0.15):
            reward, regression, reason = -0.8, True, "source_health_regressed"
        elif expired:
            reward, reason = -0.10, "source_health_unchanged_before_ttl"
    elif recipe == "RECOVER_MODEL":
        action = str(trial.get("safe_learning_action") or "")
        key = {
            "TRAIN_QUERY_STRATEGY": "query_model_status",
            "TRAIN_JOB_STRATEGY": "job_model_status",
            "TRAIN_REPAIR_PRIORITY": "repair_requires_attention",
        }.get(action)
        if key == "repair_requires_attention":
            if before.get(key) is True and after.get(key) is False:
                reward, reason = 1.0, "repair_model_recovered"
            elif expired:
                reward, reason = -0.15, "repair_model_not_recovered_before_ttl"
        elif key:
            good = {"active", "healthy", "ok", "ready", "verified"}
            if str(before.get(key)) in {"broken", "degraded"} and str(after.get(key)) in good:
                reward, reason = 1.0, "runtime_model_recovered"
            elif str(after.get(key)) == "broken" and str(before.get(key)) != "broken":
                reward, regression, reason = -1.0, True, "runtime_model_regressed"
            elif expired:
                reward, reason = -0.15, "runtime_model_not_recovered_before_ttl"
    elif recipe == "OBSERVE_ONLY" and expired:
        reward, reason = 0.0, "observation_completed"

    if reward is None:
        return None
    return {
        "verified": True,
        "verification_kind": "objective_operational_state_transition",
        "controller_version": CONTROLLER_VERSION,
        "skill_id": str(trial.get("skill_id") or "")[:128],
        "recipe": recipe,
        "reward": round(_clamp(reward, -1.0, 1.0), 6),
        "regression_detected": regression,
        "reason": reason,
        "evidence_ref": (
            f"v374:{reason}:{str(trial.get('created_at') or '')}:"
            f"{moment.isoformat(timespec='seconds')}"
        )[:240],
        "verified_at": moment.isoformat(timespec="seconds"),
        "before": before,
        "after": after,
        "market_direction_inferred": False,
    }


def persist_verified_outcomes(
    new_rows: list[dict[str, Any]],
    *,
    path: Path = OUTCOMES_PATH,
) -> dict[str, Any]:
    if not new_rows:
        return {"status": "NO_NEW_VERIFIED_OUTCOMES", "written": False, "count": 0}
    existing = load_verified_skill_outcomes(path=path)
    merged: list[dict[str, Any]] = []
    for row in existing[-(MAX_OUTCOMES - len(new_rows)):]:
        merged.append({
            "verified": True,
            "recipe": row["recipe"],
            "skill_id": row["skill_id"],
            "reward": row["reward"],
            "regression_detected": row["regression_detected"],
            "evidence_ref": row["evidence_ref"],
            "verified_at": row["verified_at"],
        })
    accepted = 0
    seen_evidence = {str(row.get("evidence_ref") or "") for row in merged}
    for row in new_rows:
        evidence = str(row.get("evidence_ref") or "").strip() if isinstance(row, dict) else ""
        if (
            isinstance(row, dict)
            and row.get("verified") is True
            and str(row.get("recipe") or "") in SKILL_RECIPES
            and _finite(row.get("reward")) is not None
            and evidence
            and evidence not in seen_evidence
        ):
            merged.append(row)
            seen_evidence.add(evidence)
            accepted += 1
    if accepted == 0:
        return {"status": "NO_VALID_VERIFIED_OUTCOMES", "written": False, "count": 0}
    merged = merged[-MAX_OUTCOMES:]
    text = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in merged) + "\n"
    try:
        atomic_write_text(path, text, suffix=".v374-outcomes.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "OUTCOME_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "VERIFIED_OUTCOMES_SAVED", "written": True, "count": accepted}


def _active_skill_row(skill: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    return {
        "skill_id": str(skill["skill_id"]),
        "recipe": str(skill["recipe"]),
        "gap_id": str(skill.get("gap_id") or "")[:128],
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(seconds=SKILL_TTL_SECONDS)).isoformat(timespec="seconds"),
        "source_code_change": False,
        "arbitrary_command": False,
    }


def reconcile_skill_state(
    loaded_state: dict[str, Any],
    *,
    plan: dict[str, Any],
    selected_skill: dict[str, Any] | None,
    history: dict[str, dict[str, Any]],
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    moment = (now or _now()).astimezone(timezone.utc)
    state = deepcopy(loaded_state)
    verified: list[dict[str, Any]] = []
    still_pending: list[dict[str, Any]] = []
    for trial in state.get("pending_trials", []):
        result = evaluate_trial(trial, plan, now=moment)
        if result is None:
            still_pending.append(trial)
        else:
            verified.append(result)
    state["pending_trials"] = still_pending[:MAX_PENDING_TRIALS]

    blocked = {recipe for recipe, stat in history.items() if stat.get("blocked") is True}
    blocked.update(
        str(row.get("recipe") or "")
        for row in verified
        if row.get("regression_detected") is True
    )
    state["suspended_recipes"] = sorted(x for x in blocked if x in SKILL_RECIPES)
    state["active_skills"] = [
        row for row in state.get("active_skills", [])
        if str(row.get("recipe") or "") not in blocked
    ][:MAX_ACTIVE_SKILLS]

    if selected_skill and selected_skill["recipe"] not in blocked:
        active = _active_skill_row(selected_skill, now=moment)
        by_id = {str(row.get("skill_id") or ""): row for row in state["active_skills"]}
        by_id[active["skill_id"]] = active
        state["active_skills"] = sorted(by_id.values(), key=lambda row: str(row["skill_id"]))[:MAX_ACTIVE_SKILLS]
        if selected_skill["recipe"] != "OBSERVE_ONLY":
            trial = _trial_for_skill(selected_skill, plan, now=moment)
            pending_by_id = {str(row.get("skill_id") or ""): row for row in state["pending_trials"]}
            pending_by_id[trial["skill_id"]] = trial
            state["pending_trials"] = sorted(
                pending_by_id.values(), key=lambda row: str(row["skill_id"])
            )[:MAX_PENDING_TRIALS]
    return state, verified


def source_feature_proposals(
    gaps: list[dict[str, Any]],
    history: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Escalate persistent runtime gaps to non-executable source proposals."""
    proposals: list[dict[str, Any]] = []
    for gap in gaps:
        recipe = _recipe_for_gap(gap)
        stat = history.get(recipe) or {}
        samples = int(stat.get("samples") or 0)
        mean = float(_finite(stat.get("mean_reward")) or 0.0)
        blocked = stat.get("blocked") is True
        if not blocked and not (samples >= 3 and mean < 0.20):
            continue
        proposals.append({
            "proposal_id": f"V374_SOURCE_GAP:{str(gap.get('gap_id') or '')[:96]}",
            "gap_id": str(gap.get("gap_id") or "")[:128],
            "gap_kind": str(gap.get("kind") or "")[:64],
            "current_runtime_recipe": recipe,
            "verified_history_samples": samples,
            "verified_mean_reward": round(mean, 6),
            "reason": "declarative_runtime_skill_insufficient",
            "normal_pr_pipeline_required": True,
            "auto_implementation": False,
            "source_code_generation": False,
            "git_write": False,
            "required_validation": [
                "targeted_tests",
                "related_regression",
                "full_current_runtime",
                "repository_integrity",
                "tablet_gpt_alignment",
                "actual_output_validation",
            ],
            "evidence": dict(gap.get("evidence") or {}),
        })
    return proposals[:MAX_SOURCE_PROPOSALS]


def run_cycle(
    *,
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    proc_root: Path = Path("/proc"),
    state_path: Path | None = None,
    capability_path: Path | None = None,
    meta_model_path: Path | None = None,
    meta_outcomes_path: Path | None = None,
    skill_state_path: Path | None = None,
    skill_outcomes_path: Path | None = None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    state = state_path or (root / v373.v372.STATE_PATH.name)
    cap_path = capability_path or (root / v373.CAPABILITY_PATH.name)
    meta_path = meta_model_path or (root / v373.META_MODEL_PATH.name)
    meta_outcomes = meta_outcomes_path or (root / v373.OUTCOMES_PATH.name)
    skill_state_file = skill_state_path or (root / SKILL_STATE_PATH.name)
    skill_outcomes_file = skill_outcomes_path or (root / OUTCOMES_PATH.name)

    # Observation always precedes action. V373 remains the bounded neural/capability
    # planner; V374 adds causal trial verification and candidate competition.
    base_report = v373.run_cycle(
        execute=False,
        apply_capabilities=False,
        train_meta=train_meta,
        root=root,
        now=moment,
        proc_root=proc_root,
        state_path=state,
        capability_path=cap_path,
        meta_model_path=meta_path,
        outcomes_path=meta_outcomes,
        persist_outputs=False,
    )
    plan = base_report["plan"]
    gaps = detect_gaps(plan)

    prior_outcomes = load_verified_skill_outcomes(path=skill_outcomes_file)
    prior_history = skill_history_stats(prior_outcomes)
    loaded_skills = load_skill_state(path=skill_state_file, now=moment)

    # First close any prior verification windows. A regression is therefore
    # learned/suspended before the next candidate can be chosen.
    evaluated_state, verified_now = reconcile_skill_state(
        loaded_skills["state"],
        plan=plan,
        selected_skill=None,
        history=prior_history,
        now=moment,
    )
    outcome_write = (
        persist_verified_outcomes(verified_now, path=skill_outcomes_file)
        if apply_skills
        else {"status": "OUTCOME_APPLY_NOT_REQUESTED", "written": False, "count": 0}
    )
    verified_for_history = [
        {
            "recipe": row["recipe"],
            "skill_id": row["skill_id"],
            "reward": row["reward"],
            "regression_detected": row["regression_detected"],
            "evidence_ref": row["evidence_ref"],
            "verified_at": row["verified_at"],
        }
        for row in verified_now
    ]
    combined_history = skill_history_stats(prior_outcomes + verified_for_history)

    candidates = generate_candidates(plan, gaps, combined_history)
    selected = (
        None
        if loaded_skills["corruption_hold"]
        else select_candidate(plan, candidates, skill_state=evaluated_state)
    )

    skill_caps = skill_capabilities(selected, now=moment)
    existing_caps = [
        row for row in plan.get("active_capabilities", [])
        if isinstance(row, dict) and v373.validate_capability(row, now=moment)
    ]
    merged_caps = v373.merge_capabilities(existing_caps, skill_caps, now=moment)
    evolved_plan = evolve_plan(plan, selected, merged_caps)

    if execute:
        operational_execution = execute_operational_skill(selected, evolved_plan)
        safe_learning_execution = v373.v372.execute_safe_learning(
            evolved_plan, state_path=state, now=moment
        )
        execution = {
            "status": "V374_EXECUTED",
            "operational": operational_execution,
            "safe_learning": safe_learning_execution,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        }
    else:
        execution = {
            "status": "PLAN_ONLY",
            "operational": {"status": "PLAN_ONLY", "executed": False},
            "safe_learning": {"status": "PLAN_ONLY", "results": {}},
            "proposals_executed": False,
            "git_write": False,
            "source_code_modified": False,
        }

    # A trial represents an action that actually ran. Plan-only/apply-only modes
    # must never create evidence windows for actions that did not execute.
    selected_for_state = selected if (apply_skills and execute) else None
    next_skill_state, unexpected_verified = reconcile_skill_state(
        evaluated_state,
        plan=plan,
        selected_skill=selected_for_state,
        history=combined_history,
        now=moment,
    )
    # The first reconciliation already evaluated all pre-existing trials.
    # This guard is fail-closed if future code changes accidentally make the
    # second pass produce an additional outcome in the same observation.
    if unexpected_verified:
        execution = dict(execution)
        execution["status"] = "TRIAL_RECONCILIATION_HOLD"
        execution["unexpected_verified_outcomes"] = len(unexpected_verified)
        next_skill_state = evaluated_state

    capability_write = {"status": "CAPABILITY_APPLY_NOT_REQUESTED", "written": False}
    if apply_capabilities:
        corruption_hold = bool(base_report.get("capability_state", {}).get("corruption_hold"))
        capability_write = v373.save_capabilities(
            merged_caps,
            path=cap_path,
            corruption_hold=corruption_hold,
            now=moment,
        )

    skill_write = {"status": "SKILL_APPLY_NOT_REQUESTED", "written": False}
    if apply_skills:
        skill_write = save_skill_state(
            next_skill_state,
            path=skill_state_file,
            corruption_hold=bool(loaded_skills["corruption_hold"]),
            now=moment,
        )

    proposals = source_feature_proposals(gaps, combined_history)
    result = {
        "controller_version": CONTROLLER_VERSION,
        "plan": evolved_plan,
        "gaps": gaps,
        "candidates": candidates,
        "selected_skill": selected,
        "execution": execution,
        "capability_write": capability_write,
        "skill_state": {
            "load_status": loaded_skills["status"],
            "corruption_hold": loaded_skills["corruption_hold"],
            "write": skill_write,
            "active_count": len(next_skill_state.get("active_skills", [])),
            "pending_trial_count": len(next_skill_state.get("pending_trials", [])),
            "suspended_recipes": list(next_skill_state.get("suspended_recipes", [])),
        },
        "verified_trial_outcomes": verified_now,
        "verified_outcome_write": outcome_write,
        "skill_history": combined_history,
        "source_feature_proposals": proposals,
        "meta_neural": base_report.get("meta_neural", {}),
        "safety": SAFETY,
    }

    if persist_outputs:
        runtime_output = {"status": "SAVED", "report": True, "proposals": True}
        try:
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".v374-report.tmp")
            atomic_write_json(
                root / SOURCE_PROPOSALS_PATH.name,
                {
                    "schema_version": SCHEMA_VERSION,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "normal_pr_pipeline_required": True,
                    "auto_implementation": False,
                    "proposals": proposals,
                },
                suffix=".v374-source-proposals.tmp",
            )
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            runtime_output = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        result["runtime_output"] = runtime_output
    return result


def self_test() -> None:
    assert SAFETY["closed_loop_candidate_generation"] is True
    assert SAFETY["one_runtime_skill_per_cycle"] is True
    assert SAFETY["max_heavy_operations_per_cycle"] == 1
    assert SAFETY["operational_refresh_existing_updater_only"] is True
    assert SAFETY["verified_skill_outcome_learning_only"] is True
    assert SAFETY["declarative_skill_auto_composition"] is True
    assert SAFETY["source_level_gap_auto_implementation"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["arbitrary_command_execution"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["price_or_grade_invention"] is False
    assert SAFETY["market_direction_inferred"] is False
    assert set(SKILL_RECIPES) == {
        "RECOVER_FRESHNESS",
        "EXPAND_REGION_COVERAGE",
        "RECOVER_SOURCE_HEALTH",
        "RECOVER_MODEL",
        "OBSERVE_ONLY",
    }
    print("Tablet closed-loop autonomous evolution v374: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-safe-learning", action="store_true")
    parser.add_argument("--apply-capabilities", action="store_true")
    parser.add_argument("--train-meta", action="store_true")
    parser.add_argument("--apply-skills", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run_cycle(
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
