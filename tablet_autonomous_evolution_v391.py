#!/usr/bin/env python3
"""V391: self-diagnosing verified adaptive evolution governor for Tablet GPT.

V391 sits above V390. It keeps the V390 verified meta-critic and operational
goal planner, then adds three bounded autonomy layers:

1. evidence-only self diagnosis with persistent fault streaks,
2. deterministic counterfactual decision stress testing,
3. verified regression blocking plus a source-feature lifecycle planner.

The controller may decide, learn and re-plan from operational evidence, but it
never invents market direction, prices, grades or facts. Runtime extension
remains the canonical V373 allowlist path owned by V390. Source-level feature
needs remain non-executable contracts that require protected PR/CI and the
existing regression, integrity, alignment and actual-output validation chain.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v390 as v390
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v391"
CORE_CONTROLLER_VERSION = "v390"

STATE_PATH = ROOT / ".tablet_autonomy_v391_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v391_report.json"
PLAN_PATH = ROOT / "tablet_autonomy_improvement_plan_v391.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v391.lock"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_500_000
MAX_HISTORY = 192
MAX_FAULTS = 24
MAX_FEATURES = 48
MIN_STRESS_CRITIC_SAMPLES = 6
COUNTERFACTUAL_CONSENSUS_REQUIRED = 3
REGRESSION_MIN_VERIFIED_SAMPLES = 6
REGRESSION_LONG_REWARD_FLOOR = -0.18
REGRESSION_LCB_FLOOR = -0.25
HIGH_STRESS_HOLD = 0.55

_HOLD_STATUSES = set(getattr(v390, "_HOLD_STATUSES", set())) | {
    "V391_STATE_CORRUPTION_HOLD",
    "V391_CONCURRENT_AUTONOMY_HOLD",
    "V391_UPSTREAM_HOLD",
    "V391_VERIFIED_REGRESSION_HOLD",
    "V391_COUNTERFACTUAL_INSTABILITY_HOLD",
    "V391_CRITICAL_SELF_DIAGNOSTIC_HOLD",
    "V391_STATE_COMMIT_HOLD",
}

SAFETY = dict(v390.SAFETY)
SAFETY.update({
    "self_diagnosis_enabled": True,
    "self_diagnosis_operational_evidence_only": True,
    "fault_streak_learning_enabled": True,
    "counterfactual_decision_stress_test_enabled": True,
    "counterfactual_is_deterministic_and_advisory": True,
    "verified_regression_guard_enabled": True,
    "recovery_action_regression_hold_forbidden": True,
    "feature_lifecycle_planner_enabled": True,
    "feature_lifecycle_source_plan_non_executable": True,
    "feature_lifecycle_requires_protected_pr_ci": True,
    "v390_gate_cannot_be_bypassed": True,
    "v388_gate_cannot_be_bypassed": True,
    "runtime_capability_owner": "v390_canonical_v373_allowlist",
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "market_direction_inferred": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "price_or_grade_invention": False,
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
    if value["schema_version"] != STATE_SCHEMA_VERSION or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["cycle"], int) or not 0 <= value["cycle"] <= 10_000_000:
        return False

    faults = value["fault_streaks"]
    if not isinstance(faults, dict) or len(faults) > MAX_FAULTS:
        return False
    for key, count in faults.items():
        if not isinstance(key, str) or not key or len(key) > 120:
            return False
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000_000:
            return False

    features = value["feature_lifecycle"]
    if not isinstance(features, dict) or len(features) > MAX_FEATURES:
        return False
    for key, row in features.items():
        if not isinstance(key, str) or not key or len(key) > 200 or not isinstance(row, dict):
            return False
        required = {"seen_cycles", "last_priority", "last_stage", "last_seen_cycle"}
        if set(row) != required:
            return False
        if not isinstance(row["seen_cycles"], int) or not 0 <= row["seen_cycles"] <= 1_000_000:
            return False
        priority = _finite(row["last_priority"])
        if priority is None or not 0.0 <= priority <= 1.0:
            return False
        if not isinstance(row["last_stage"], str) or len(row["last_stage"]) > 80:
            return False
        if not isinstance(row["last_seen_cycle"], int) or row["last_seen_cycle"] < 0:
            return False

    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V391_STATE_PATH")
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
            "error_code": "V391_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V391_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V391_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v391-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "V391_STATE_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {"status": "V391_STATE_SAVED", "written": True}


def _dimensions(preview: dict[str, Any]) -> dict[str, float]:
    kpis = preview.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    dims = kpis.get("dimensions")
    dims = dims if isinstance(dims, dict) else {}

    def get(name: str, default: float = 0.5) -> float:
        value = _finite(dims.get(name))
        return _clamp(value if value is not None else default)

    return {
        "market_freshness": get("market_freshness"),
        "market_coverage": get("market_coverage"),
        "source_health": get("source_health"),
        "neural_consensus": get("neural_consensus"),
        "resource_headroom": get("resource_headroom"),
    }


def self_diagnose(preview: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    dims = _dimensions(preview)
    budget = preview.get("v388_resource_budget")
    budget = budget if isinstance(budget, dict) else {}
    market = preview.get("market_adaptation_v381")
    market = market if isinstance(market, dict) else {}
    gate = preview.get("v390_autonomous_gate")
    gate = gate if isinstance(gate, dict) else {}
    critic = preview.get("v390_meta_critic")
    critic = critic if isinstance(critic, dict) else {}
    cap = preview.get("v390_goal_capability")
    cap = cap if isinstance(cap, dict) else {}
    cap_write = cap.get("write")
    cap_write = cap_write if isinstance(cap_write, dict) else {}
    state_write = preview.get("v390_state_write")
    state_write = state_write if isinstance(state_write, dict) else {}

    drift = _clamp(float(_finite(budget.get("drift_score")) or 0.0))
    uncertainty = _clamp(float(_finite(budget.get("selected_uncertainty")) or 0.0))
    degraded_ratio = _clamp(float(_finite(market.get("degraded_source_ratio")) or 0.0))

    raw: list[tuple[str, float, str]] = []
    if dims["market_freshness"] < 0.65:
        raw.append(("FRESHNESS_DEFICIT", 1.0 - dims["market_freshness"], "refresh_verified_market_data"))
    if dims["market_coverage"] < 0.65:
        raw.append(("COVERAGE_DEFICIT", 1.0 - dims["market_coverage"], "expand_verified_market_coverage"))
    source_stress = max(1.0 - dims["source_health"], degraded_ratio)
    if source_stress >= 0.25:
        raw.append(("SOURCE_DEGRADATION", source_stress, "recheck_degraded_sources"))
    drift_stress = max(drift, uncertainty)
    if drift_stress >= 0.40:
        raw.append(("DRIFT_UNCERTAINTY", drift_stress, "revalidate_before_non_recovery"))
    if dims["resource_headroom"] < 0.55:
        raw.append(("RESOURCE_PRESSURE", 1.0 - dims["resource_headroom"], "prefer_recovery_and_reduce_optional_learning"))
    if gate.get("allow_execution") is not True:
        raw.append(("UPSTREAM_GATE_HOLD", 0.92, "preserve_v390_and_prior_hold"))
    cap_status = str(cap_write.get("status") or "")
    if cap_status and cap_status not in {
        "GOAL_CAPABILITY_NOT_REQUESTED", "NO_GOAL_CAPABILITY",
        "CAPABILITIES_SAVED", "V390_CAPABILITY_SAVED",
    } and ("FAILED" in cap_status or "HOLD" in cap_status or "CORRUPT" in cap_status):
        raw.append(("CAPABILITY_PERSISTENCE_FAILURE", 0.88, "hold_next_cycle_capability_promotion"))
    state_status = str(state_write.get("status") or "")
    if state_status and state_status not in {"V390_STATE_WRITE_NOT_REQUESTED", "V390_STATE_SAVED"}:
        if "FAILED" in state_status or "HOLD" in state_status or "INVALID" in state_status:
            raw.append(("UPSTREAM_STATE_PERSISTENCE_FAILURE", 0.95, "hold_mutation_until_state_is_safe"))

    critic_samples = int(critic.get("sample_count") or 0)
    fresh_rows = int(critic.get("fresh_training_rows") or 0)
    if critic_samples < MIN_STRESS_CRITIC_SAMPLES and fresh_rows == 0:
        raw.append(("META_CRITIC_EVIDENCE_THIN", 0.28, "collect_verified_outcomes_before_strong_alignment"))

    old_streaks = state.get("fault_streaks") if isinstance(state.get("fault_streaks"), dict) else {}
    faults = []
    active_ids = set()
    for fault_id, severity, remediation in raw:
        active_ids.add(fault_id)
        previous = int(old_streaks.get(fault_id, 0) or 0)
        effective = _clamp(severity + min(0.18, 0.03 * previous))
        faults.append({
            "fault_id": fault_id,
            "severity": round(_clamp(severity), 6),
            "effective_severity": round(effective, 6),
            "prior_streak": previous,
            "remediation_hint": remediation,
            "operational_evidence_only": True,
            "market_direction_inferred": False,
        })
    faults.sort(key=lambda row: (-float(row["effective_severity"]), row["fault_id"]))

    top = faults[0] if faults else None
    top_id = str(top.get("fault_id") or "") if top else ""
    if top_id in {"UPSTREAM_STATE_PERSISTENCE_FAILURE", "CAPABILITY_PERSISTENCE_FAILURE", "UPSTREAM_GATE_HOLD"}:
        regime = "RECOVERY_GOVERNANCE"
    elif top_id == "RESOURCE_PRESSURE":
        regime = "RESOURCE_CONSTRAINED"
    elif top_id == "DRIFT_UNCERTAINTY":
        regime = "REVALIDATION"
    elif top_id in {"FRESHNESS_DEFICIT", "COVERAGE_DEFICIT", "SOURCE_DEGRADATION"}:
        regime = "MARKET_EVIDENCE_RECOVERY"
    elif top_id == "META_CRITIC_EVIDENCE_THIN":
        regime = "VERIFIED_LEARNING"
    else:
        regime = "STEADY_VERIFIED_OPTIMIZATION"

    stress_score = max((float(row["effective_severity"]) for row in faults), default=0.0)
    return {
        "faults": faults,
        "active_fault_ids": sorted(active_ids),
        "top_fault": top,
        "stress_score": round(_clamp(stress_score), 6),
        "operational_regime": regime,
        "dimensions": dims,
        "drift_score": round(drift, 6),
        "uncertainty": round(uncertainty, 6),
        "degraded_source_ratio": round(degraded_ratio, 6),
        "market_direction_inferred": False,
    }


def counterfactual_stress_test(preview: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    plan = preview.get("v390_goal_plan")
    plan = plan if isinstance(plan, dict) else {}
    candidates = plan.get("candidates")
    candidates = candidates if isinstance(candidates, list) else []
    recommended = str(plan.get("recommended_action") or "") or None
    stress = _clamp(float(_finite(diagnosis.get("stress_score")) or 0.0))

    scenarios = {
        "baseline": (0.46, 0.22, 0.18, 0.14),
        "confidence_heavy": (0.38, 0.18, 0.16, 0.28),
        "goal_heavy": (0.38, 0.34, 0.14, 0.14),
        "conservative": (0.34, 0.16, 0.24, 0.26),
    }
    winners: dict[str, str | None] = {}
    score_rows: dict[str, list[dict[str, Any]]] = {}

    for scenario, weights in scenarios.items():
        ranked = []
        for row in candidates:
            if not isinstance(row, dict):
                continue
            action = str(row.get("action_id") or "")[:160]
            if not action:
                continue
            utility = _clamp(float(_finite(row.get("goal_utility")) or 0.0))
            affinity = _clamp(float(_finite(row.get("goal_affinity")) or 0.0))
            portfolio = _clamp(float(_finite(row.get("portfolio_score")) or 0.0))
            confidence = _clamp(float(_finite(row.get("confidence")) or 0.0))
            recovery = bool(row.get("recovery_action"))
            status = str(row.get("status") or "challenger")
            score = (
                weights[0] * utility
                + weights[1] * affinity
                + weights[2] * portfolio
                + weights[3] * confidence
            )
            score -= stress * (0.02 if recovery else 0.10)
            if status == "quarantined":
                score -= 0.40
            elif status == "retired":
                score -= 0.80
            ranked.append({
                "action_id": action,
                "score": round(score, 6),
                "recovery_action": recovery,
                "status": status,
            })
        ranked.sort(key=lambda row: (-float(row["score"]), not bool(row["recovery_action"]), row["action_id"]))
        winners[scenario] = ranked[0]["action_id"] if ranked else None
        score_rows[scenario] = ranked

    consensus = sum(1 for action in winners.values() if recommended and action == recommended)
    stable = recommended is None or consensus >= COUNTERFACTUAL_CONSENSUS_REQUIRED
    return {
        "recommended_action": recommended,
        "scenario_winners": winners,
        "recommended_consensus": consensus,
        "scenario_count": len(scenarios),
        "stable": stable,
        "stress_score": round(stress, 6),
        "score_rows": score_rows,
        "deterministic": True,
        "advisory_only": True,
        "market_direction_inferred": False,
    }


def verified_regression_guard(preview: dict[str, Any]) -> dict[str, Any]:
    policy = preview.get("v388_policy_portfolio")
    policy = policy if isinstance(policy, dict) else {}
    selected = str(policy.get("upstream_selected_action") or "") or None
    rows = policy.get("candidates")
    rows = rows if isinstance(rows, list) else []
    row = next((x for x in rows if isinstance(x, dict) and str(x.get("action_id") or "") == selected), None)
    if row is None or selected is None:
        return {
            "status": "NO_SELECTED_VERIFIED_POLICY_ROW",
            "block": False,
            "selected_action": selected,
            "recovery_action": False,
        }

    verified = max(0, int(row.get("verified_samples") or 0))
    long_reward = _finite(row.get("long_reward"))
    reward_lcb = _finite(row.get("reward_lcb"))
    recovery = v390.v388._is_recovery(selected)
    regressed = (
        verified >= REGRESSION_MIN_VERIFIED_SAMPLES
        and (
            (long_reward is not None and long_reward <= REGRESSION_LONG_REWARD_FLOOR)
            or (reward_lcb is not None and reward_lcb <= REGRESSION_LCB_FLOOR)
        )
    )
    block = bool(regressed and not recovery)
    return {
        "status": "VERIFIED_REGRESSION_BLOCK" if block else ("RECOVERY_REGRESSION_OBSERVE_ONLY" if regressed else "VERIFIED_REGRESSION_CLEAR"),
        "block": block,
        "selected_action": selected,
        "recovery_action": recovery,
        "verified_samples": verified,
        "long_reward": long_reward,
        "reward_lcb": reward_lcb,
        "thresholds": {
            "min_verified_samples": REGRESSION_MIN_VERIFIED_SAMPLES,
            "long_reward_floor": REGRESSION_LONG_REWARD_FLOOR,
            "reward_lcb_floor": REGRESSION_LCB_FLOOR,
        },
    }


def feature_lifecycle_plan(
    preview: dict[str, Any],
    state: dict[str, Any],
    *,
    next_cycle: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = preview.get("v390_source_feature_plan")
    rows = rows if isinstance(rows, list) else []
    previous = state.get("feature_lifecycle")
    previous = previous if isinstance(previous, dict) else {}
    result = []
    next_memory: dict[str, Any] = {}

    for row in rows[:MAX_FEATURES]:
        if not isinstance(row, dict):
            continue
        proposal_id = str(
            row.get("v388_proposal_id")
            or row.get("proposal_id")
            or row.get("feature_id")
            or ""
        )[:200]
        if not proposal_id:
            continue
        priority = _clamp(float(_finite(row.get("v388_priority_score")) or 0.0))
        recurrence = max(0, int(row.get("v388_recurrence") or 0))
        old = previous.get(proposal_id) if isinstance(previous.get(proposal_id), dict) else {}
        seen = min(1_000_000, int(old.get("seen_cycles") or 0) + 1)
        old_priority = _finite(old.get("last_priority"))
        trend = priority - old_priority if old_priority is not None else 0.0
        old_stage = str(old.get("last_stage") or "observe")

        if old_stage == "protected_pr_candidate" and trend >= 0.12:
            stage = "rework_required"
        elif priority >= 0.78 and recurrence >= 4 and seen >= 2:
            stage = "protected_pr_candidate"
        elif priority >= 0.56 and recurrence >= 2:
            stage = "canary_spec_candidate"
        elif priority >= 0.38:
            stage = "shadow_spec"
        else:
            stage = "observe"

        result.append({
            **deepcopy(row),
            "v391_stage": stage,
            "v391_seen_cycles": seen,
            "v391_priority_trend": round(trend, 6),
            "v391_execution_mode": "non_executable_feature_lifecycle_contract",
            "auto_execute": False,
            "auto_generate_source": False,
            "git_write": False,
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
            "rollback_or_rework_on_verified_regression": True,
        })
        next_memory[proposal_id] = {
            "seen_cycles": seen,
            "last_priority": round(priority, 6),
            "last_stage": stage,
            "last_seen_cycle": next_cycle,
        }

    for proposal_id, old in previous.items():
        if proposal_id in next_memory or not isinstance(old, dict):
            continue
        if len(next_memory) >= MAX_FEATURES:
            break
        next_memory[proposal_id] = {
            "seen_cycles": int(old.get("seen_cycles") or 0),
            "last_priority": round(_clamp(float(_finite(old.get("last_priority")) or 0.0)), 6),
            "last_stage": str(old.get("last_stage") or "observe")[:80],
            "last_seen_cycle": int(old.get("last_seen_cycle") or 0),
        }

    result.sort(key=lambda row: (-float(row.get("v388_priority_score") or 0.0), str(row.get("v388_proposal_id") or "")))
    return result, next_memory


def autonomous_gate(
    preview: dict[str, Any],
    diagnosis: dict[str, Any],
    stress_test: dict[str, Any],
    regression: dict[str, Any],
    *,
    corruption_hold: bool,
) -> dict[str, Any]:
    upstream = preview.get("v390_autonomous_gate")
    upstream = upstream if isinstance(upstream, dict) else {}
    allow = upstream.get("allow_execution") is True
    reasons: list[str] = []

    if not allow:
        reasons.append(str(upstream.get("status") or "V390_UPSTREAM_HOLD"))
    if corruption_hold:
        allow = False
        reasons.append("V391_STATE_CORRUPTION")
    if regression.get("block") is True:
        allow = False
        reasons.append("VERIFIED_NON_RECOVERY_REGRESSION")

    plan = preview.get("v390_goal_plan")
    plan = plan if isinstance(plan, dict) else {}
    upstream_action = str(plan.get("upstream_selected_action") or "") or None
    critic_samples = int(plan.get("critic_sample_count") or 0)
    stress = _clamp(float(_finite(diagnosis.get("stress_score")) or 0.0))
    unstable = stress_test.get("stable") is not True
    if (
        allow
        and unstable
        and critic_samples >= MIN_STRESS_CRITIC_SAMPLES
        and stress >= HIGH_STRESS_HOLD
        and upstream_action
        and not v390.v388._is_recovery(upstream_action)
    ):
        allow = False
        reasons.append("COUNTERFACTUAL_DECISION_INSTABILITY")

    top = diagnosis.get("top_fault")
    top = top if isinstance(top, dict) else {}
    top_id = str(top.get("fault_id") or "")
    top_severity = _clamp(float(_finite(top.get("effective_severity")) or 0.0))
    if (
        allow
        and top_id in {"UPSTREAM_STATE_PERSISTENCE_FAILURE", "CAPABILITY_PERSISTENCE_FAILURE"}
        and top_severity >= 0.85
    ):
        allow = False
        reasons.append("CRITICAL_PERSISTENCE_DIAGNOSTIC")

    if "V391_STATE_CORRUPTION" in reasons:
        status = "V391_STATE_CORRUPTION_HOLD"
    elif "VERIFIED_NON_RECOVERY_REGRESSION" in reasons:
        status = "V391_VERIFIED_REGRESSION_HOLD"
    elif "COUNTERFACTUAL_DECISION_INSTABILITY" in reasons:
        status = "V391_COUNTERFACTUAL_INSTABILITY_HOLD"
    elif "CRITICAL_PERSISTENCE_DIAGNOSTIC" in reasons:
        status = "V391_CRITICAL_SELF_DIAGNOSTIC_HOLD"
    elif not allow:
        status = "V391_UPSTREAM_HOLD"
    else:
        status = "V391_VERIFIED_ALLOW"

    return {
        "status": status,
        "allow_execution": allow,
        "reasons": reasons,
        "upstream_action": upstream_action,
        "counterfactual_stable": stress_test.get("stable") is True,
        "verified_regression_block": regression.get("block") is True,
        "hard_blocker_override": False,
        "market_direction_inferred": False,
    }


def remediation_candidate(
    preview: dict[str, Any],
    diagnosis: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    existing = preview.get("v390_goal_capability")
    existing = existing if isinstance(existing, dict) else {}
    if isinstance(existing.get("candidate"), dict):
        return {
            "status": "V390_CAPABILITY_ALREADY_SELECTED",
            "candidate": existing.get("candidate"),
            "owner": "v390",
            "written_by_v391": False,
        }

    top = diagnosis.get("top_fault")
    top = top if isinstance(top, dict) else {}
    fault_id = str(top.get("fault_id") or "")
    severity = _clamp(float(_finite(top.get("effective_severity")) or 0.0))
    mapping = {
        "FRESHNESS_DEFICIT": ("RECOVER_MARKET_FRESHNESS", "REFRESH_MARKET_DATA"),
        "SOURCE_DEGRADATION": ("RECOVER_SOURCE_HEALTH", "RECHECK_DEGRADED_SOURCES"),
        "COVERAGE_DEFICIT": ("EXPAND_VERIFIED_MARKET_COVERAGE", "EXPAND_MARKET_COVERAGE"),
    }
    if fault_id not in mapping:
        return {
            "status": "NO_SAFE_DECLARATIVE_REMEDIATION",
            "candidate": None,
            "owner": "v390",
            "written_by_v391": False,
        }
    goal_id, action = mapping[fault_id]
    candidate = v390.goal_capability(
        {
            "primary_goal": {"goal_id": goal_id, "urgency": severity},
            "recommended_action": action,
        },
        preview,
        now=now,
    )
    return {
        "status": "CANONICAL_REMEDIATION_CANDIDATE" if candidate else "NO_VALID_CANONICAL_REMEDIATION",
        "candidate": candidate,
        "owner": "v390_canonical_v373_allowlist",
        "written_by_v391": False,
        "next_cycle_only": True,
    }


def _next_state(
    current: dict[str, Any],
    diagnosis: dict[str, Any],
    lifecycle_memory: dict[str, Any],
    gate: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    cycle = min(10_000_000, int(current.get("cycle") or 0) + 1)
    active = set(str(x) for x in diagnosis.get("active_fault_ids", []) if str(x))
    old = current.get("fault_streaks")
    old = old if isinstance(old, dict) else {}
    streaks: dict[str, int] = {}
    for fault_id in sorted(set(old) | active):
        if fault_id in active:
            streaks[fault_id] = min(1_000_000, int(old.get(fault_id, 0) or 0) + 1)
        else:
            decayed = max(0, int(old.get(fault_id, 0) or 0) - 1)
            if decayed:
                streaks[fault_id] = decayed
    streaks = dict(sorted(streaks.items(), key=lambda item: (-item[1], item[0]))[:MAX_FAULTS])

    history = list(current.get("history") or [])
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
        "feature_lifecycle": lifecycle_memory,
        "history": history[-MAX_HISTORY:],
    }


def run_cycle(
    *,
    domain: str = "tablet_gpt",
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    state_path: Path | None = None,
    persist_outputs: bool = True,
    **upstream_paths: Any,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = state_path or (root / STATE_PATH.name)

    fd = None
    if mutating:
        fd, lock_info = v390.v388.v387.v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v391_status": "V391_CONCURRENT_AUTONOMY_HOLD",
                "v391_lock": lock_info,
                "execution": {
                    "status": "V391_CONCURRENT_AUTONOMY_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                },
                "safety": SAFETY,
            }

    try:
        preview = v390.run_cycle(
            domain=domain,
            execute=False,
            apply_capabilities=False,
            train_meta=False,
            apply_skills=False,
            root=root,
            now=moment,
            persist_outputs=False,
            **upstream_paths,
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
        gate = autonomous_gate(
            preview,
            diagnosis,
            stress_test,
            regression,
            corruption_hold=bool(loaded.get("corruption_hold")),
        )
        remediation = remediation_candidate(preview, diagnosis, now=moment)

        base = preview
        if mutating and gate.get("allow_execution") is True:
            base = v390.run_cycle(
                domain=domain,
                execute=execute,
                apply_capabilities=apply_capabilities,
                train_meta=train_meta,
                apply_skills=apply_skills,
                root=root,
                now=moment,
                persist_outputs=False,
                **upstream_paths,
            )
            if str(base.get("v390_status") or "") in getattr(v390, "_HOLD_STATUSES", set()):
                gate = {
                    **gate,
                    "status": "V391_UPSTREAM_HOLD",
                    "allow_execution": False,
                    "reasons": list(gate.get("reasons") or []) + [str(base.get("v390_status") or "V390_HOLD")],
                }

        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v391_status": gate.get("status") if mutating else "PLAN_ONLY",
            "v391_self_diagnosis": diagnosis,
            "v391_counterfactual_stress_test": stress_test,
            "v391_verified_regression_guard": regression,
            "v391_feature_lifecycle": lifecycle,
            "v391_remediation_candidate": remediation,
            "v391_autonomous_gate": gate,
            "evolution_contract_v391": {
                "base_controller": "v390",
                "primary_loop": "observe_diagnose_stress_test_select_execute_monitor_replan",
                "fault_learning": "device_local_operational_streaks_only",
                "decision_stress_test": "deterministic_multi_weight_counterfactual_panel",
                "regression_guard": "verified_reward_non_recovery_block_recovery_observe_only",
                "runtime_self_extension": "v390_canonical_v373_declarative_allowlist_only",
                "source_feature_evolution": "observe_shadow_canary_spec_protected_pr_or_rework_non_executable",
                "market_adaptation": "operational_freshness_coverage_source_health_drift_uncertainty_only",
                "v390_and_prior_gate_bypass": False,
                "peer_model_weights_imported": False,
                "peer_raw_state_imported": False,
                "git_write": False,
                "source_code_auto_generation": False,
                "source_code_auto_rewrite": False,
                "arbitrary_command_execution": False,
                "verification_bypass": False,
                "market_direction_inferred": False,
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

        state_write = {"status": "V391_STATE_WRITE_NOT_REQUESTED", "written": False}
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
                result["v391_status"] = "V391_STATE_COMMIT_HOLD"
                result["v391_autonomous_gate"] = {
                    **gate,
                    "status": "V391_STATE_COMMIT_HOLD",
                    "allow_execution": False,
                    "reasons": list(gate.get("reasons") or []) + ["V391_STATE_WRITE_FAILED"],
                }
        result["v391_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(
                    root / PLAN_PATH.name,
                    {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "diagnosis": diagnosis,
                        "counterfactual_stress_test": stress_test,
                        "verified_regression_guard": regression,
                        "feature_lifecycle": lifecycle,
                        "remediation_candidate": remediation,
                        "auto_generate_source": False,
                        "git_write": False,
                        "protected_pr_ci_required": True,
                    },
                    suffix=".v391-plan.tmp",
                )
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v391-report.tmp")
                result["v391_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v391_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }
        return result
    finally:
        if fd is not None:
            v390.v388.v387.v386.v385._release_lock(fd)


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert SAFETY["self_diagnosis_enabled"] is True
    assert SAFETY["counterfactual_decision_stress_test_enabled"] is True
    assert SAFETY["verified_regression_guard_enabled"] is True
    assert SAFETY["feature_lifecycle_planner_enabled"] is True
    assert SAFETY["v390_gate_cannot_be_bypassed"] is True
    assert SAFETY["peer_model_weights_imported"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet self-diagnosing verified adaptive evolution governor v391: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=sorted(v390.v388.v387.v386.DOMAINS), default="tablet_gpt")
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
        domain=args.domain,
        execute=args.execute_safe_learning,
        apply_capabilities=args.apply_capabilities,
        train_meta=args.train_meta,
        apply_skills=args.apply_skills,
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("v391_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
