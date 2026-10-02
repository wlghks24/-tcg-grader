#!/usr/bin/env python3
"""TCG Grader V397 local mutual-sync autonomous evolution.

No cloud execution or cloud learning is used here.

V397 keeps V396's verified TCG Grader <-> Tablet GPT mutual MLP and adds:
1) persistent operational self-diagnosis and fault-streak learning,
2) deterministic multi-view counterfactual action stress testing,
3) verified regression blocking for non-recovery actions,
4) source-feature lifecycle planning,
5) bounded remediation selection from existing allowlisted actions.

Existing declarative runtime capabilities may still be selected/applied through
upstream V395/V396 after all gates pass. New source-level functionality remains
proposal-only and must pass protected PR/CI and the existing regression chain.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tcg_grader_autonomous_evolution_v396 as v396
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "tcg-grader-v397"
CORE_CONTROLLER_VERSION = "tcg-grader-v396"
STATE_PATH = ROOT / ".tcg_grader_autonomy_v397_state.json"
REPORT_PATH = ROOT / "tcg_grader_autonomy_v397_report.json"
PLAN_PATH = ROOT / "tcg_grader_autonomy_v397_plan.json"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_000_000
MAX_HISTORY = 192
MAX_FAULTS = 32
MAX_FEATURES = 48
MIN_VERIFIED_SAMPLES = 6
HIGH_STRESS_HOLD = 0.58
REGRESSION_REWARD_FLOOR = -0.18

RECOVERY_ACTIONS = {
    "RETRY_DEGRADED_SOURCES",
    "PRIORITIZE_REPAIR_LEARNING",
    "REVALIDATE_ONLY",
    "REFRESH_MARKET_DATA",
}

_HOLD_STATUSES = {
    "V397_STATE_CORRUPTION_HOLD",
    "V397_UPSTREAM_HOLD",
    "V397_VERIFIED_REGRESSION_HOLD",
    "V397_COUNTERFACTUAL_INSTABILITY_HOLD",
    "V397_CRITICAL_SELF_DIAGNOSTIC_HOLD",
    "V397_STATE_COMMIT_HOLD",
}

SAFETY = dict(v396.SAFETY)
SAFETY.update({
    "cloud_learning_used": False,
    "cloud_parallel_learning_used": False,
    "self_diagnosis_enabled": True,
    "fault_streak_learning_enabled": True,
    "counterfactual_decision_stress_test_enabled": True,
    "verified_regression_guard_enabled": True,
    "feature_lifecycle_planner_enabled": True,
    "bounded_remediation_planner_enabled": True,
    "v396_mutual_mlp_preserved": True,
    "v395_resource_protection_preserved": True,
    "runtime_allowlist_self_extension_preserved": True,
    "source_feature_auto_generation": False,
    "source_feature_protected_pr_ci_required": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "direct_main_write": False,
    "git_write": False,
    "verification_bypass": False,
    "market_direction_inferred": False,
    "price_or_grade_invention": False,
})


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "fault_streaks": {},
        "feature_lifecycle": {},
        "history": [],
    }


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {
        "schema_version", "controller_version", "cycle",
        "fault_streaks", "feature_lifecycle", "history",
    }:
        return False
    if value.get("schema_version") != STATE_SCHEMA_VERSION:
        return False
    if value.get("controller_version") != CONTROLLER_VERSION:
        return False
    if not isinstance(value.get("cycle"), int) or not 0 <= value["cycle"] <= 10_000_000:
        return False
    faults = value.get("fault_streaks")
    features = value.get("feature_lifecycle")
    history = value.get("history")
    if not isinstance(faults, dict) or len(faults) > MAX_FAULTS:
        return False
    if not isinstance(features, dict) or len(features) > MAX_FEATURES:
        return False
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        return False
    for key, count in faults.items():
        if not isinstance(key, str) or not key or len(key) > 120:
            return False
        if not isinstance(count, int) or isinstance(count, bool) or not 0 <= count <= 1_000_000:
            return False
    for key, row in features.items():
        if not isinstance(key, str) or not key or len(key) > 220 or not isinstance(row, dict):
            return False
        if set(row) != {"seen_cycles", "last_priority", "last_stage", "last_seen_cycle"}:
            return False
        if not isinstance(row["seen_cycles"], int) or row["seen_cycles"] < 0:
            return False
        p = _finite(row["last_priority"])
        if p is None or not 0 <= p <= 1:
            return False
        if not isinstance(row["last_stage"], str) or len(row["last_stage"]) > 80:
            return False
        if not isinstance(row["last_seen_cycle"], int) or row["last_seen_cycle"] < 0:
            return False
    return True


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("V397_UNSAFE_STATE_PATH")
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
            "error_code": "V397_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V397_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V397_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v397-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "V397_STATE_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {"status": "V397_STATE_SAVED", "written": True}


def _payload(core: dict[str, Any]) -> dict[str, Any]:
    value = core.get("tcg_grader_autonomy_v396")
    return value if isinstance(value, dict) else {}


def _v395(core: dict[str, Any]) -> dict[str, Any]:
    value = core.get("tcg_grader_autonomy_v395")
    return value if isinstance(value, dict) else {}


def _v392(core: dict[str, Any]) -> dict[str, Any]:
    value = core.get("tcg_grader_autonomy_v392")
    return value if isinstance(value, dict) else {}


def self_diagnose(core: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(core)
    sync = payload.get("mutual_sync")
    sync = sync if isinstance(sync, dict) else {}
    v395 = _v395(core)
    schedule = v395.get("resource_schedule")
    schedule = schedule if isinstance(schedule, dict) else {}
    source = v395.get("source_reliability")
    source = source if isinstance(source, dict) else {}
    v392 = _v392(core)
    obs = v392.get("observation")
    obs = obs if isinstance(obs, dict) else {}
    dims = obs.get("dimensions")
    dims = dims if isinstance(dims, dict) else {}

    quality = _clamp(float(_finite(v392.get("quality_score")) or 0.5))
    drift = _clamp(float(_finite(obs.get("drift")) or 0.0))
    coverage = _clamp(float(_finite(dims.get("market_coverage")) or 0.5))
    source_health = _clamp(float(_finite(dims.get("source_health")) or 0.5))
    neural_consensus = _clamp(float(_finite(dims.get("neural_consensus")) or 0.5))
    headroom = _clamp(float(
        _finite(schedule.get("resource_headroom"))
        or _finite(dims.get("resource_headroom"))
        or 0.5
    ))
    degraded = _clamp(float(_finite(source.get("degraded_or_cooldown_ratio")) or 0.0))
    loss = _finite(sync.get("training_loss"))
    training_examples = max(0, int(sync.get("training_examples") or 0))
    peer_status = str(sync.get("peer_status") or "")
    strong_divergence = sync.get("strong_divergence") is True

    raw: list[tuple[str, float, str]] = []
    if peer_status == "PEER_SUMMARY_REJECTED":
        raw.append(("PEER_SUMMARY_INVALID", 0.98, "hold_peer_mutation_and_revalidate_summary"))
    if strong_divergence:
        raw.append(("VERIFIED_PEER_DIVERGENCE", 0.90, "hold_and_collect_more_verified_outcomes"))
    if peer_status == "PEER_SUMMARY_VERIFIED" and training_examples == 0:
        raw.append(("MUTUAL_TRAINING_EVIDENCE_THIN", 0.34, "collect_matching_verified_action_outcomes"))
    if loss is not None and loss > 0.20:
        raw.append(("MUTUAL_NEURAL_LOSS_HIGH", min(0.85, 0.35 + loss), "increase_verified_matching_samples_before_promotion"))
    if coverage < 0.65:
        raw.append(("MARKET_COVERAGE_DEFICIT", 1.0 - coverage, "prioritize_low_coverage_regions"))
    source_stress = max(1.0 - source_health, degraded)
    if source_stress >= 0.25:
        raw.append(("SOURCE_RELIABILITY_DEFICIT", source_stress, "retry_or_replace_degraded_sources"))
    if drift >= 0.40:
        raw.append(("OPERATIONAL_DRIFT_HIGH", drift, "revalidate_before_non_recovery_actions"))
    if headroom < 0.55:
        raw.append(("RESOURCE_PRESSURE", 1.0 - headroom, "defer_optional_learning_and_keep_runtime_light"))
    if quality < 0.70:
        raw.append(("QUALITY_SCORE_DEFICIT", 1.0 - quality, "prioritize_verified_learning_and_revalidation"))
    if neural_consensus < 0.60:
        raw.append(("NEURAL_CONSENSUS_LOW", 1.0 - neural_consensus, "hold_aggressive_changes_until_consensus_recovers"))

    old = state.get("fault_streaks")
    old = old if isinstance(old, dict) else {}
    faults = []
    active = set()
    for fault_id, severity, remediation in raw:
        active.add(fault_id)
        streak = int(old.get(fault_id, 0) or 0)
        effective = _clamp(severity + min(0.18, 0.03 * streak))
        faults.append({
            "fault_id": fault_id,
            "severity": round(_clamp(severity), 6),
            "effective_severity": round(effective, 6),
            "prior_streak": streak,
            "remediation_hint": remediation,
        })
    faults.sort(key=lambda row: (-float(row["effective_severity"]), row["fault_id"]))
    top = faults[0] if faults else None
    top_id = str((top or {}).get("fault_id") or "")
    if top_id in {"PEER_SUMMARY_INVALID", "VERIFIED_PEER_DIVERGENCE"}:
        regime = "MUTUAL_SYNC_RECOVERY"
    elif top_id == "RESOURCE_PRESSURE":
        regime = "RESOURCE_CONSTRAINED"
    elif top_id in {"MARKET_COVERAGE_DEFICIT", "SOURCE_RELIABILITY_DEFICIT"}:
        regime = "MARKET_EVIDENCE_RECOVERY"
    elif top_id in {"OPERATIONAL_DRIFT_HIGH", "QUALITY_SCORE_DEFICIT", "NEURAL_CONSENSUS_LOW"}:
        regime = "REVALIDATION"
    else:
        regime = "STEADY_VERIFIED_OPTIMIZATION"

    return {
        "faults": faults,
        "active_fault_ids": sorted(active),
        "top_fault": top,
        "stress_score": round(max((float(x["effective_severity"]) for x in faults), default=0.0), 6),
        "operational_regime": regime,
        "metrics": {
            "quality_score": round(quality, 6),
            "drift": round(drift, 6),
            "market_coverage": round(coverage, 6),
            "source_health": round(source_health, 6),
            "neural_consensus": round(neural_consensus, 6),
            "resource_headroom": round(headroom, 6),
            "degraded_source_ratio": round(degraded, 6),
            "mutual_training_examples": training_examples,
            "mutual_training_loss": loss,
        },
        "market_direction_inferred": False,
    }


def counterfactual_stress_test(core: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(core)
    actions = payload.get("shared_verified_actions")
    actions = actions if isinstance(actions, list) else []
    sync = payload.get("mutual_sync")
    sync = sync if isinstance(sync, dict) else {}
    selected = str(sync.get("selected_action") or "") or None
    stress = _clamp(float(_finite(diagnosis.get("stress_score")) or 0.0))

    scenarios = {
        "balanced": (0.56, 0.24, 0.20),
        "verified_reward_heavy": (0.38, 0.46, 0.16),
        "sample_confidence_heavy": (0.40, 0.18, 0.42),
        "conservative": (0.46, 0.18, 0.36),
    }
    winners: dict[str, str | None] = {}
    score_rows: dict[str, list[dict[str, Any]]] = {}
    for scenario, weights in scenarios.items():
        ranked = []
        for row in actions:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action_id") or "")[:160]
            score = _finite(row.get("score"))
            reward = _finite(row.get("reward_mean"))
            samples = row.get("verified_samples")
            if not action or score is None or reward is None or not isinstance(samples, int):
                continue
            reward01 = _clamp((reward + 1.0) / 2.0)
            sample_conf = _clamp(samples / 36.0)
            value = weights[0] * _clamp(score) + weights[1] * reward01 + weights[2] * sample_conf
            if action not in RECOVERY_ACTIONS:
                value -= stress * 0.08
            ranked.append({
                "action_id": action,
                "score": round(value, 6),
                "recovery_action": action in RECOVERY_ACTIONS,
            })
        ranked.sort(key=lambda x: (-float(x["score"]), not bool(x["recovery_action"]), x["action_id"]))
        winners[scenario] = ranked[0]["action_id"] if ranked else None
        score_rows[scenario] = ranked

    consensus = sum(1 for action in winners.values() if selected and action == selected)
    stable = selected is None or consensus >= 3
    return {
        "selected_action": selected,
        "scenario_winners": winners,
        "selected_consensus": consensus,
        "scenario_count": len(scenarios),
        "stable": stable,
        "stress_score": round(stress, 6),
        "score_rows": score_rows,
        "deterministic": True,
        "advisory_only": True,
        "market_direction_inferred": False,
    }


def verified_regression_guard(core: dict[str, Any]) -> dict[str, Any]:
    payload = _payload(core)
    sync = payload.get("mutual_sync")
    sync = sync if isinstance(sync, dict) else {}
    selected = str(sync.get("selected_action") or "") or None
    actions = payload.get("shared_verified_actions")
    actions = actions if isinstance(actions, list) else []
    row = next(
        (x for x in actions if isinstance(x, dict) and str(x.get("action_id") or "") == selected),
        None,
    )
    if row is None:
        return {
            "status": "NO_SELECTED_VERIFIED_ACTION",
            "block": False,
            "selected_action": selected,
            "recovery_action": selected in RECOVERY_ACTIONS if selected else False,
        }
    reward = _finite(row.get("reward_mean"))
    samples = row.get("verified_samples")
    recovery = selected in RECOVERY_ACTIONS
    regressed = bool(
        isinstance(samples, int)
        and samples >= MIN_VERIFIED_SAMPLES
        and reward is not None
        and reward <= REGRESSION_REWARD_FLOOR
    )
    return {
        "status": (
            "VERIFIED_REGRESSION_BLOCK"
            if regressed and not recovery
            else "RECOVERY_REGRESSION_OBSERVE_ONLY"
            if regressed
            else "VERIFIED_REGRESSION_CLEAR"
        ),
        "block": bool(regressed and not recovery),
        "selected_action": selected,
        "recovery_action": recovery,
        "verified_samples": samples if isinstance(samples, int) else 0,
        "reward_mean": reward,
        "reward_floor": REGRESSION_REWARD_FLOOR,
    }


def _priority(row: dict[str, Any]) -> float:
    value = _finite(row.get("priority"))
    if value is not None:
        return _clamp(value)
    text = str(row.get("priority") or "").upper()
    return {"CRITICAL": 0.95, "HIGH": 0.82, "MEDIUM": 0.58, "LOW": 0.32}.get(text, 0.45)


def feature_lifecycle_plan(
    core: dict[str, Any],
    state: dict[str, Any],
    *,
    next_cycle: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _payload(core)
    rows = payload.get("source_feature_plan")
    rows = rows if isinstance(rows, list) else []
    previous = state.get("feature_lifecycle")
    previous = previous if isinstance(previous, dict) else {}
    result: list[dict[str, Any]] = []
    memory: dict[str, Any] = {}

    for row in rows[:MAX_FEATURES]:
        if not isinstance(row, dict):
            continue
        proposal_id = str(
            row.get("proposal_id")
            or row.get("upstream_contract_id")
            or ""
        )[:220]
        if not proposal_id:
            continue
        priority = _priority(row)
        old = previous.get(proposal_id) if isinstance(previous.get(proposal_id), dict) else {}
        seen = min(1_000_000, int(old.get("seen_cycles") or 0) + 1)
        old_priority = _finite(old.get("last_priority"))
        trend = priority - old_priority if old_priority is not None else 0.0
        old_stage = str(old.get("last_stage") or "observe")
        if old_stage == "protected_pr_candidate" and trend >= 0.12:
            stage = "rework_required"
        elif priority >= 0.78 and seen >= 2:
            stage = "protected_pr_candidate"
        elif priority >= 0.58:
            stage = "canary_spec_candidate"
        elif priority >= 0.38:
            stage = "shadow_spec"
        else:
            stage = "observe"
        item = deepcopy(row)
        item.update({
            "v397_stage": stage,
            "v397_seen_cycles": seen,
            "v397_priority": round(priority, 6),
            "v397_priority_trend": round(trend, 6),
            "execution_mode": "non_executable_source_feature_contract",
            "runtime_allowlist_self_extension_only": True,
            "auto_execute": False,
            "auto_generate_source": False,
            "git_write": False,
            "protected_pr_ci_required": True,
            "promotion_requires": [
                "shadow_spec",
                "targeted_tests",
                "related_regression",
                "canary_validation",
                "full_current_runtime",
                "repository_integrity",
                "tablet_gpt_alignment",
                "actual_output_validation",
                "protected_pr_ci",
            ],
        })
        result.append(item)
        memory[proposal_id] = {
            "seen_cycles": seen,
            "last_priority": round(priority, 6),
            "last_stage": stage,
            "last_seen_cycle": next_cycle,
        }

    for proposal_id, old in previous.items():
        if proposal_id in memory or not isinstance(old, dict) or len(memory) >= MAX_FEATURES:
            continue
        memory[proposal_id] = {
            "seen_cycles": int(old.get("seen_cycles") or 0),
            "last_priority": round(_clamp(float(_finite(old.get("last_priority")) or 0.0)), 6),
            "last_stage": str(old.get("last_stage") or "observe")[:80],
            "last_seen_cycle": int(old.get("last_seen_cycle") or 0),
        }
    result.sort(key=lambda row: (-float(row.get("v397_priority") or 0.0), str(row.get("proposal_id") or "")))
    return result, memory


def remediation_plan(core: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    top = diagnosis.get("top_fault")
    top = top if isinstance(top, dict) else {}
    fault_id = str(top.get("fault_id") or "")
    mapping = {
        "PEER_SUMMARY_INVALID": "REVALIDATE_ONLY",
        "VERIFIED_PEER_DIVERGENCE": "REVALIDATE_ONLY",
        "MUTUAL_TRAINING_EVIDENCE_THIN": "PRIORITIZE_REPAIR_LEARNING",
        "MUTUAL_NEURAL_LOSS_HIGH": "PRIORITIZE_REPAIR_LEARNING",
        "MARKET_COVERAGE_DEFICIT": "EXPAND_MARKET_COVERAGE",
        "SOURCE_RELIABILITY_DEFICIT": "RETRY_DEGRADED_SOURCES",
        "OPERATIONAL_DRIFT_HIGH": "REVALIDATE_ONLY",
        "QUALITY_SCORE_DEFICIT": "PRIORITIZE_REPAIR_LEARNING",
        "NEURAL_CONSENSUS_LOW": "REVALIDATE_ONLY",
        "RESOURCE_PRESSURE": "REVALIDATE_ONLY",
    }
    action = mapping.get(fault_id)
    available = {
        str(row.get("action_id") or "")
        for row in (_payload(core).get("shared_verified_actions") or [])
        if isinstance(row, dict)
    }
    return {
        "status": "BOUNDED_REMEDIATION_SELECTED" if action else "NO_REMEDIATION_REQUIRED",
        "fault_id": fault_id or None,
        "recommended_action": action,
        "present_in_verified_action_set": bool(action and action in available),
        "auto_generate_source": False,
        "git_write": False,
        "runtime_allowlist_only": True,
        "next_cycle_advisory": True,
    }


def autonomous_gate(
    core: dict[str, Any],
    diagnosis: dict[str, Any],
    stress_test: dict[str, Any],
    regression: dict[str, Any],
    *,
    corruption_hold: bool,
) -> dict[str, Any]:
    sync = _payload(core).get("mutual_sync")
    sync = sync if isinstance(sync, dict) else {}
    upstream = sync.get("gate")
    upstream = upstream if isinstance(upstream, dict) else {}
    allow = upstream.get("allow_execution") is True
    reasons: list[str] = []

    if not allow:
        reasons.append(str(upstream.get("status") or "V396_UPSTREAM_HOLD"))
    if corruption_hold:
        allow = False
        reasons.append("V397_STATE_CORRUPTION")
    if regression.get("block") is True:
        allow = False
        reasons.append("VERIFIED_NON_RECOVERY_REGRESSION")

    stress = _clamp(float(_finite(diagnosis.get("stress_score")) or 0.0))
    selected = str(stress_test.get("selected_action") or "")
    if (
        allow
        and stress_test.get("stable") is not True
        and stress >= HIGH_STRESS_HOLD
        and selected
        and selected not in RECOVERY_ACTIONS
    ):
        allow = False
        reasons.append("COUNTERFACTUAL_DECISION_INSTABILITY")

    top = diagnosis.get("top_fault")
    top = top if isinstance(top, dict) else {}
    if (
        allow
        and str(top.get("fault_id") or "") == "PEER_SUMMARY_INVALID"
        and float(_finite(top.get("effective_severity")) or 0.0) >= 0.90
    ):
        allow = False
        reasons.append("CRITICAL_MUTUAL_SYNC_DIAGNOSTIC")

    if "V397_STATE_CORRUPTION" in reasons:
        status = "V397_STATE_CORRUPTION_HOLD"
    elif "VERIFIED_NON_RECOVERY_REGRESSION" in reasons:
        status = "V397_VERIFIED_REGRESSION_HOLD"
    elif "COUNTERFACTUAL_DECISION_INSTABILITY" in reasons:
        status = "V397_COUNTERFACTUAL_INSTABILITY_HOLD"
    elif "CRITICAL_MUTUAL_SYNC_DIAGNOSTIC" in reasons:
        status = "V397_CRITICAL_SELF_DIAGNOSTIC_HOLD"
    elif not allow:
        status = "V397_UPSTREAM_HOLD"
    else:
        status = "V397_VERIFIED_ALLOW"
    return {
        "status": status,
        "allow_execution": allow,
        "reasons": reasons,
        "upstream_gate": upstream.get("status"),
        "selected_action": stress_test.get("selected_action"),
        "counterfactual_stable": stress_test.get("stable") is True,
        "verified_regression_block": regression.get("block") is True,
        "hard_blocker_override": False,
        "market_direction_inferred": False,
    }


def _next_state(
    state: dict[str, Any],
    diagnosis: dict[str, Any],
    lifecycle: dict[str, Any],
    gate: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    cycle = min(10_000_000, int(state.get("cycle") or 0) + 1)
    active = set(str(x) for x in diagnosis.get("active_fault_ids", []) if str(x))
    old = state.get("fault_streaks")
    old = old if isinstance(old, dict) else {}
    streaks: dict[str, int] = {}
    for fault_id in sorted(set(old) | active):
        if fault_id in active:
            streaks[fault_id] = min(1_000_000, int(old.get(fault_id, 0) or 0) + 1)
        else:
            decayed = max(0, int(old.get(fault_id, 0) or 0) - 1)
            if decayed:
                streaks[fault_id] = decayed
    streaks = dict(sorted(streaks.items(), key=lambda x: (-x[1], x[0]))[:MAX_FAULTS])
    history = list(state.get("history") or [])
    top = diagnosis.get("top_fault")
    top = top if isinstance(top, dict) else {}
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": cycle,
        "operational_regime": diagnosis.get("operational_regime"),
        "top_fault": top.get("fault_id"),
        "stress_score": diagnosis.get("stress_score"),
        "gate_status": gate.get("status"),
        "allow_execution": gate.get("allow_execution") is True,
    })
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": cycle,
        "fault_streaks": streaks,
        "feature_lifecycle": lifecycle,
        "history": history[-MAX_HISTORY:],
    }


def run_cycle(
    *,
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    state_path: Path | None = None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = state_path or (root / STATE_PATH.name)

    preview = v396.run_cycle(
        execute=False,
        apply_capabilities=False,
        train_meta=False,
        apply_skills=False,
        root=root,
        now=moment,
        persist_outputs=False,
    )
    loaded = load_state(state_file)
    diagnosis = self_diagnose(preview, loaded["state"])
    stress_test = counterfactual_stress_test(preview, diagnosis)
    regression = verified_regression_guard(preview)
    next_cycle = min(10_000_000, int(loaded["state"].get("cycle") or 0) + 1)
    lifecycle, lifecycle_memory = feature_lifecycle_plan(
        preview,
        loaded["state"],
        next_cycle=next_cycle,
    )
    remediation = remediation_plan(preview, diagnosis)
    gate = autonomous_gate(
        preview,
        diagnosis,
        stress_test,
        regression,
        corruption_hold=bool(loaded.get("corruption_hold")),
    )

    core = preview
    if mutating and gate.get("allow_execution") is True:
        core = v396.run_cycle(
            execute=execute,
            apply_capabilities=apply_capabilities,
            train_meta=train_meta,
            apply_skills=apply_skills,
            root=root,
            now=moment,
            persist_outputs=False,
        )
        live_sync = _payload(core).get("mutual_sync")
        live_sync = live_sync if isinstance(live_sync, dict) else {}
        live_gate = live_sync.get("gate")
        live_gate = live_gate if isinstance(live_gate, dict) else {}
        if live_gate.get("allow_execution") is not True:
            gate = {
                **gate,
                "status": "V397_UPSTREAM_HOLD",
                "allow_execution": False,
                "reasons": list(gate.get("reasons") or []) + [
                    str(live_gate.get("status") or "V396_LIVE_HOLD")
                ],
            }

    result = deepcopy(core)
    result.update({
        "core_controller_version": str(core.get("controller_version") or CORE_CONTROLLER_VERSION),
        "controller_version": CONTROLLER_VERSION,
        "tcg_grader_autonomy_v397": {
            "status": gate.get("status") if mutating else "PLAN_ONLY",
            "self_diagnosis": diagnosis,
            "counterfactual_stress_test": stress_test,
            "verified_regression_guard": regression,
            "feature_lifecycle": lifecycle,
            "remediation_plan": remediation,
            "autonomous_gate": gate,
            "mutual_sync_neural_network": "V396 verified matching-outcome MLP preserved and governed by V397",
            "closed_loop": (
                "V396-mutual-verified-MLP->self-diagnosis->fault-streak-learning->"
                "counterfactual-stress-test->verified-regression-guard->"
                "feature-lifecycle/remediation-plan->V396/V395 safe execution->reobserve"
            ),
            "self_extension": (
                "existing allowlisted declarative runtime capabilities may be selected/applied automatically; "
                "new source-level functions remain lifecycle proposals requiring protected PR/CI"
            ),
            "market_adaptation": (
                "freshness/coverage/source-health/drift/quality/neural-consensus evidence only; "
                "no market-direction, price, or grade invention"
            ),
            "cloud_used": False,
        },
        "safety": SAFETY,
    })

    if mutating and gate.get("allow_execution") is not True:
        result["execution"] = {
            "status": gate.get("status"),
            "executed": False,
            "git_write": False,
            "source_code_modified": False,
            "proposals_executed": False,
        }

    state_write = {"status": "V397_STATE_WRITE_NOT_REQUESTED", "written": False}
    if mutating:
        nxt = _next_state(
            loaded["state"],
            diagnosis,
            lifecycle_memory,
            gate,
            now=moment,
        )
        state_write = save_state(nxt, state_file, bool(loaded.get("corruption_hold")))
        if not state_write.get("written") and gate.get("allow_execution") is True:
            result["tcg_grader_autonomy_v397"]["status"] = "V397_STATE_COMMIT_HOLD"
            result["tcg_grader_autonomy_v397"]["autonomous_gate"] = {
                **gate,
                "status": "V397_STATE_COMMIT_HOLD",
                "allow_execution": False,
                "reasons": list(gate.get("reasons") or []) + ["V397_STATE_WRITE_FAILED"],
            }
    result["tcg_grader_autonomy_v397"]["state_write"] = state_write

    if persist_outputs:
        try:
            atomic_write_json(
                root / PLAN_PATH.name,
                {
                    "schema_version": 1,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "self_diagnosis": diagnosis,
                    "counterfactual_stress_test": stress_test,
                    "verified_regression_guard": regression,
                    "feature_lifecycle": lifecycle,
                    "remediation_plan": remediation,
                    "cloud_used": False,
                    "runtime_allowlist_self_extension_only": True,
                    "source_code_auto_generation": False,
                    "protected_pr_ci_required": True,
                },
                suffix=".v397-plan.tmp",
            )
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".v397-report.tmp")
            result["tcg_grader_v397_runtime_output"] = {"status": "SAVED"}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            result["tcg_grader_v397_runtime_output"] = {
                "status": "WRITE_FAILED",
                "error_code": type(exc).__name__,
            }
    return result


def self_test() -> None:
    assert _valid_state(_default_state())
    assert SAFETY["cloud_learning_used"] is False
    assert SAFETY["cloud_parallel_learning_used"] is False
    assert SAFETY["self_diagnosis_enabled"] is True
    assert SAFETY["fault_streak_learning_enabled"] is True
    assert SAFETY["counterfactual_decision_stress_test_enabled"] is True
    assert SAFETY["verified_regression_guard_enabled"] is True
    assert SAFETY["feature_lifecycle_planner_enabled"] is True
    assert SAFETY["v396_mutual_mlp_preserved"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("TCG Grader local mutual-sync autonomous evolution v397: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCG Grader V397 local mutual-sync autonomous evolution")
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
    payload = result.get("tcg_grader_autonomy_v397") or {}
    if not args.quiet:
        gate = payload.get("autonomous_gate") or {}
        print(json.dumps({
            "controller_version": result.get("controller_version"),
            "status": payload.get("status"),
            "cloud_used": payload.get("cloud_used"),
            "regime": (payload.get("self_diagnosis") or {}).get("operational_regime"),
            "top_fault": ((payload.get("self_diagnosis") or {}).get("top_fault") or {}).get("fault_id"),
            "selected_action": gate.get("selected_action"),
            "gate": gate.get("status"),
            "remediation": (payload.get("remediation_plan") or {}).get("recommended_action"),
        }, ensure_ascii=False, sort_keys=True))
    requested = bool(
        args.execute_safe_learning
        or args.apply_capabilities
        or args.train_meta
        or args.apply_skills
    )
    gate = payload.get("autonomous_gate") or {}
    return 2 if requested and gate.get("allow_execution") is not True else 0


if __name__ == "__main__":
    raise SystemExit(main())
