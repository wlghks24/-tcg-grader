#!/usr/bin/env python3
"""V387: uncertainty-aware mutual neural autonomy and verified self-extension.

V387 sits above V386. V386 already provides bidirectional verified-outcome
summaries and a bounded mutual-consensus neural model. V387 adds a conservative
meta-controller that combines neural consensus, verified sample support,
peer/local agreement, KPI health, operational drift and regime transitions.

The controller may reprioritize allowlisted actions, request revalidation,
advance declarative feature proposals through shadow/canary/active-candidate
states, and roll proposals back when verified KPIs regress. It never predicts
market direction, imports peer model weights/raw state, generates source code,
executes arbitrary commands, writes Git/main, bypasses upstream gates, or turns
unverified peer evidence into facts/prices/grades.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v386 as v386
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v387"
CORE_CONTROLLER_VERSION = "v386"

STATE_PATH = ROOT / ".tablet_autonomy_v387_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v387_report.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v387.lock"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_000_000
MAX_ACTIONS = 64
MAX_HISTORY = 160
MAX_REGIME_HISTORY = 96
MAX_PROPOSALS = 64

MIN_LOCAL_CONFIDENCE = 0.55
MIN_MUTUAL_CONFIDENCE = 0.62
CANARY_CONFIDENCE = 0.70
ACTIVE_CANDIDATE_CONFIDENCE = 0.82
MAX_EXECUTION_UNCERTAINTY = 0.45
HIGH_DRIFT = 0.55
SEVERE_DRIFT = 0.72
KPI_REGRESSION_MARGIN = 0.08

RECOVERY_TOKENS = (
    "REFRESH", "REVALIDATE", "RECOVER", "VERIFY", "AUDIT", "COLLECT",
    "RECHECK", "REBUILD_LAST_GOOD", "RESTORE_LAST_GOOD",
)

_HOLD_STATUSES = set(getattr(v386, "_HOLD_STATUSES", set())) | {
    "V387_STATE_CORRUPTION_HOLD",
    "V387_LOCK_UNAVAILABLE",
    "V387_CONCURRENT_AUTONOMY_HOLD",
    "V387_UNCERTAINTY_HOLD",
    "V387_REGIME_TRANSITION_HOLD",
    "V387_UPSTREAM_HOLD",
    "V387_STATE_COMMIT_HOLD",
}

SAFETY = dict(v386.SAFETY)
SAFETY.update({
    "uncertainty_aware_action_selection": True,
    "verified_sample_confidence_required": True,
    "operational_regime_transition_detection": True,
    "multi_objective_verified_governor": True,
    "declarative_feature_lifecycle": True,
    "feature_shadow_canary_active_candidate_rollback": True,
    "low_confidence_requests_revalidation": True,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
    "peer_grading_raw_imported": False,
    "peer_grading_calibration_imported": False,
    "market_direction_inferred": False,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
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


def _is_recovery(action_id: str | None) -> bool:
    value = str(action_id or "").upper()
    return any(token in value for token in RECOVERY_TOKENS)


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "action_confidence": {},
        "regime_history": [],
        "proposal_history": {},
        "history": [],
    }


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if set(value) != {
        "schema_version", "controller_version", "action_confidence",
        "regime_history", "proposal_history", "history",
    }:
        return False
    if value.get("schema_version") != STATE_SCHEMA_VERSION:
        return False
    if value.get("controller_version") != CONTROLLER_VERSION:
        return False
    action_conf = value.get("action_confidence")
    if not isinstance(action_conf, dict) or len(action_conf) > MAX_ACTIONS:
        return False
    for action, row in action_conf.items():
        if not isinstance(action, str) or not action or len(action) > 160:
            return False
        if not isinstance(row, dict):
            return False
        confidence = _finite(row.get("confidence"))
        observations = row.get("observations")
        if confidence is None or not 0 <= confidence <= 1:
            return False
        if not isinstance(observations, int) or not 0 <= observations <= 1_000_000:
            return False
    regime_history = value.get("regime_history")
    if not isinstance(regime_history, list) or len(regime_history) > MAX_REGIME_HISTORY:
        return False
    proposals = value.get("proposal_history")
    if not isinstance(proposals, dict) or len(proposals) > MAX_PROPOSALS:
        return False
    history = value.get("history")
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        return False
    return True


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V387_STATE_PATH")
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
            "error_code": "V387_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V387_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V387_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v387-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "V387_STATE_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {"status": "V387_STATE_SAVED", "written": True}


def regime_transition(base: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    mutual = base.get("v386_mutual_neural_policy")
    mutual = mutual if isinstance(mutual, dict) else {}
    local_regime = str(mutual.get("local_regime") or "UNKNOWN")[:80]
    peer_regime = str(mutual.get("peer_regime") or "UNKNOWN")[:80]
    drift = base.get("v382_drift")
    drift = drift if isinstance(drift, dict) else {}
    drift_score = _finite(drift.get("score"))
    drift_score = _clamp(drift_score if drift_score is not None else 0.5)

    prior = state.get("regime_history") if isinstance(state.get("regime_history"), list) else []
    previous = str(prior[-1].get("local_regime") or "UNKNOWN") if prior and isinstance(prior[-1], dict) else None
    peer_mismatch = peer_regime not in {"", "UNKNOWN"} and peer_regime != local_regime
    local_changed = previous not in {None, "", "UNKNOWN"} and previous != local_regime

    if drift_score >= SEVERE_DRIFT:
        level = "UNSTABLE"
    elif drift_score >= HIGH_DRIFT or (peer_mismatch and local_changed):
        level = "TRANSITION"
    elif peer_mismatch or local_changed:
        level = "WATCH"
    else:
        level = "STABLE"

    return {
        "level": level,
        "local_regime": local_regime,
        "peer_regime": peer_regime,
        "previous_local_regime": previous,
        "peer_regime_mismatch": peer_mismatch,
        "local_regime_changed": local_changed,
        "drift_score": round(drift_score, 6),
        "market_direction_inferred": False,
    }


def _candidate_confidence(row: dict[str, Any], *, peer_available: bool, drift_score: float) -> dict[str, float]:
    local_samples = max(0, int(row.get("local_verified_samples") or 0))
    peer_samples = max(0, int(row.get("peer_verified_samples") or 0))
    total_samples = local_samples + peer_samples
    sample_support = 1.0 - math.exp(-total_samples / 12.0)

    values = [
        _finite(row.get("local_score")),
        _finite(row.get("peer_score")),
        _finite(row.get("mutual_neural_score")),
    ]
    values = [float(x) for x in values if x is not None]
    if len(values) >= 2:
        spread = max(values) - min(values)
        ensemble_agreement = _clamp(1.0 - spread)
    elif len(values) == 1:
        ensemble_agreement = 0.58
    else:
        ensemble_agreement = 0.0

    gap = _finite(row.get("reward_gap"))
    if gap is None:
        verified_agreement = 0.50 if peer_available else 0.38
    else:
        verified_agreement = _clamp(1.0 - abs(gap) / 2.0)

    peer_support = 1.0 if peer_samples >= getattr(v386, "MIN_VERIFIED_SAMPLES", 3) else (0.45 if peer_available else 0.25)
    regime_stability = _clamp(1.0 - drift_score)

    confidence = (
        0.30 * sample_support
        + 0.24 * ensemble_agreement
        + 0.20 * verified_agreement
        + 0.12 * peer_support
        + 0.14 * regime_stability
    )
    return {
        "confidence": round(_clamp(confidence), 6),
        "uncertainty": round(_clamp(1.0 - confidence), 6),
        "sample_support": round(sample_support, 6),
        "ensemble_agreement": round(ensemble_agreement, 6),
        "verified_agreement": round(verified_agreement, 6),
        "regime_stability": round(regime_stability, 6),
    }


def uncertainty_policy(base: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    mutual = base.get("v386_mutual_neural_policy")
    mutual = mutual if isinstance(mutual, dict) else {}
    transition = regime_transition(base, state)
    drift_score = float(transition["drift_score"])
    peer_available = bool(mutual.get("peer_available"))

    kpis = base.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    kpi_score = _finite(kpis.get("score"))
    kpi_score = _clamp(kpi_score if kpi_score is not None else 0.5)

    rows = []
    for row in mutual.get("candidates") or []:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action_id") or "")[:160]
        raw_score = _finite(row.get("score"))
        if not action or raw_score is None:
            continue
        conf = _candidate_confidence(
            row,
            peer_available=peer_available,
            drift_score=drift_score,
        )
        recovery = _is_recovery(action)
        recovery_bonus = 0.08 if recovery and transition["level"] in {"TRANSITION", "UNSTABLE"} else 0.0
        multi = (
            0.56 * _clamp(raw_score)
            + 0.20 * conf["confidence"]
            + 0.14 * kpi_score
            + 0.10 * conf["regime_stability"]
            + recovery_bonus
            - 0.12 * conf["uncertainty"]
            - 0.10 * drift_score
        )
        rows.append({
            **deepcopy(row),
            **conf,
            "recovery_action": recovery,
            "kpi_score": round(kpi_score, 6),
            "multi_objective_score": round(_clamp(multi), 6),
        })

    rows.sort(
        key=lambda row: (
            -float(row["multi_objective_score"]),
            -float(row["confidence"]),
            -int(row.get("local_verified_samples") or 0),
            str(row["action_id"]),
        )
    )
    selected = rows[0] if rows else None
    threshold = MIN_MUTUAL_CONFIDENCE if peer_available else MIN_LOCAL_CONFIDENCE
    revalidation_required = bool(
        selected
        and (
            float(selected["confidence"]) < threshold
            or float(selected["uncertainty"]) > MAX_EXECUTION_UNCERTAINTY
        )
    )
    return {
        "peer_available": peer_available,
        "regime_transition": transition,
        "candidates": rows,
        "selected_action": selected.get("action_id") if selected else None,
        "selected_confidence": selected.get("confidence") if selected else None,
        "selected_uncertainty": selected.get("uncertainty") if selected else None,
        "confidence_threshold": threshold,
        "revalidation_required": revalidation_required,
        "market_direction_inferred": False,
    }


def autonomous_gate(base: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    upstream = base.get("v386_autonomous_gate")
    upstream = upstream if isinstance(upstream, dict) else {}
    allow = upstream.get("allow_execution") is True
    reasons: list[str] = []
    if not allow:
        reasons.append(str(upstream.get("status") or "V386_UPSTREAM_HOLD"))

    selected = policy.get("selected_action")
    confidence = _finite(policy.get("selected_confidence"))
    uncertainty = _finite(policy.get("selected_uncertainty"))
    recovery = _is_recovery(selected)
    transition = policy.get("regime_transition")
    transition = transition if isinstance(transition, dict) else {}
    level = str(transition.get("level") or "UNSTABLE")

    if selected is None:
        allow = False
        reasons.append("NO_VERIFIED_ACTION")
    if policy.get("revalidation_required") and not recovery:
        allow = False
        reasons.append("LOW_VERIFIED_CONFIDENCE")
    if uncertainty is not None and uncertainty > MAX_EXECUTION_UNCERTAINTY and not recovery:
        allow = False
        reasons.append("HIGH_UNCERTAINTY")
    if level == "UNSTABLE" and not recovery:
        allow = False
        reasons.append("UNSTABLE_OPERATIONAL_REGIME")
    if level == "TRANSITION" and confidence is not None and confidence < CANARY_CONFIDENCE and not recovery:
        allow = False
        reasons.append("REGIME_TRANSITION_REVALIDATION")

    if "UNSTABLE_OPERATIONAL_REGIME" in reasons or "REGIME_TRANSITION_REVALIDATION" in reasons:
        status = "V387_REGIME_TRANSITION_HOLD"
    elif "LOW_VERIFIED_CONFIDENCE" in reasons or "HIGH_UNCERTAINTY" in reasons or "NO_VERIFIED_ACTION" in reasons:
        status = "V387_UNCERTAINTY_HOLD"
    elif not allow:
        status = "V387_UPSTREAM_HOLD"
    else:
        status = "V387_RECOVERY_ALLOW" if recovery else "V387_VERIFIED_ALLOW"

    return {
        "status": status,
        "allow_execution": allow,
        "selected_action": selected,
        "selected_confidence": confidence,
        "selected_uncertainty": uncertainty,
        "recovery_only": recovery and level in {"TRANSITION", "UNSTABLE"},
        "reasons": reasons,
        "hard_blocker_override": False,
        "market_direction_inferred": False,
    }


def feature_lifecycle(
    base: dict[str, Any],
    policy: dict[str, Any],
    state: dict[str, Any],
) -> list[dict[str, Any]]:
    plans = base.get("v386_function_plan")
    plans = plans if isinstance(plans, list) else []
    selected_conf = _finite(policy.get("selected_confidence")) or 0.0
    transition = policy.get("regime_transition")
    transition = transition if isinstance(transition, dict) else {}
    stable = transition.get("level") == "STABLE"
    kpis = base.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    kpi_score = _finite(kpis.get("score"))
    kpi_score = _clamp(kpi_score if kpi_score is not None else 0.5)
    history = state.get("proposal_history") if isinstance(state.get("proposal_history"), dict) else {}

    result = []
    for idx, raw in enumerate(plans[:MAX_PROPOSALS]):
        if not isinstance(raw, dict):
            continue
        item = deepcopy(raw)
        proposal_id = str(
            item.get("proposal_id")
            or item.get("contract_id")
            or item.get("feature_id")
            or f"v387-feature-{idx}"
        )[:160]
        prior = history.get(proposal_id) if isinstance(history.get(proposal_id), dict) else {}
        prior_status = str(prior.get("status") or "shadow")
        activation_kpi = _finite(prior.get("activation_kpi"))

        if activation_kpi is not None and kpi_score + KPI_REGRESSION_MARGIN < activation_kpi:
            status = "rolled_back"
        elif selected_conf >= ACTIVE_CANDIDATE_CONFIDENCE and stable and prior_status in {"canary", "active_candidate"}:
            status = "active_candidate"
        elif selected_conf >= CANARY_CONFIDENCE and stable:
            status = "canary"
        else:
            status = "shadow"

        item.update({
            "v387_proposal_id": proposal_id,
            "v387_status": status,
            "v387_confidence": round(selected_conf, 6),
            "v387_operational_regime": transition.get("level"),
            "auto_execute": False,
            "auto_generate_source": False,
            "source_code_generated": False,
            "git_write": False,
            "protected_pr_ci_required": True,
            "required_promotion_gates": [
                "targeted_tests",
                "related_regression",
                "full_current_runtime",
                "repository_integrity",
                "tablet_gpt_alignment",
                "actual_output_validation",
            ],
            "promotion_rule": "shadow->canary->active_candidate; source-level activation only after protected PR/CI and verified output",
            "rollback_rule": f"verified KPI drop > {KPI_REGRESSION_MARGIN:.2f} restores prior verified behavior",
        })
        result.append(item)
    return result


def _next_state(
    state: dict[str, Any],
    policy: dict[str, Any],
    gate: dict[str, Any],
    proposals: list[dict[str, Any]],
    *,
    now: datetime,
) -> dict[str, Any]:
    nxt = deepcopy(state)
    action = str(policy.get("selected_action") or "")
    confidence = _finite(policy.get("selected_confidence"))
    if action and confidence is not None:
        old = nxt["action_confidence"].get(action)
        old = old if isinstance(old, dict) else {}
        count = int(old.get("observations") or 0)
        old_conf = _finite(old.get("confidence"))
        blended = confidence if old_conf is None else (0.75 * old_conf + 0.25 * confidence)
        nxt["action_confidence"][action] = {
            "confidence": round(_clamp(blended), 6),
            "observations": min(1_000_000, count + 1),
        }
        nxt["action_confidence"] = dict(
            sorted(
                nxt["action_confidence"].items(),
                key=lambda pair: (-int(pair[1].get("observations") or 0), pair[0]),
            )[:MAX_ACTIONS]
        )

    transition = policy.get("regime_transition")
    transition = transition if isinstance(transition, dict) else {}
    regimes = list(nxt.get("regime_history") or [])
    regimes.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "local_regime": str(transition.get("local_regime") or "UNKNOWN")[:80],
        "peer_regime": str(transition.get("peer_regime") or "UNKNOWN")[:80],
        "level": str(transition.get("level") or "UNKNOWN")[:32],
        "drift_score": _clamp(_finite(transition.get("drift_score")) or 0.5),
    })
    nxt["regime_history"] = regimes[-MAX_REGIME_HISTORY:]

    proposal_history = dict(nxt.get("proposal_history") or {})
    kpi_score = _finite((policy.get("candidates") or [{}])[0].get("kpi_score")) if policy.get("candidates") else None
    for row in proposals:
        pid = str(row.get("v387_proposal_id") or "")
        if not pid:
            continue
        prior = proposal_history.get(pid)
        prior = prior if isinstance(prior, dict) else {}
        status = str(row.get("v387_status") or "shadow")
        proposal_history[pid] = {
            "status": status,
            "observations": min(1_000_000, int(prior.get("observations") or 0) + 1),
            "activation_kpi": (
                round(kpi_score, 6)
                if status in {"canary", "active_candidate"} and kpi_score is not None
                else prior.get("activation_kpi")
            ),
        }
    nxt["proposal_history"] = dict(
        sorted(
            proposal_history.items(),
            key=lambda pair: (-int(pair[1].get("observations") or 0), pair[0]),
        )[:MAX_PROPOSALS]
    )

    history = list(nxt.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "gate_status": gate.get("status"),
        "selected_action": policy.get("selected_action"),
        "selected_confidence": policy.get("selected_confidence"),
        "regime_level": transition.get("level"),
        "revalidation_required": bool(policy.get("revalidation_required")),
    })
    nxt["history"] = history[-MAX_HISTORY:]
    return nxt


def _persist_v386_summary(base: dict[str, Any], domain: str, root: Path, now: datetime) -> dict[str, Any]:
    try:
        local_path, _, _ = v386._paths_for_domain(root, domain)
        summary = v386.build_summary(base, domain, now=now)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(local_path, summary, suffix=".v387-v386-summary.tmp")
        return {"status": "SAVED", "summary_path": str(local_path)}
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "WRITE_FAILED", "error_code": type(exc).__name__}


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
    lock_info = {"status": "V387_LOCK_NOT_REQUIRED", "error_code": None}
    if mutating:
        fd, lock_info = v386.v385._acquire_lock(root / LOCK_PATH.name)
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "v387_status": "V387_CONCURRENT_AUTONOMY_HOLD",
                "execution": {
                    "status": "V387_CONCURRENT_AUTONOMY_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                },
                "safety": SAFETY,
            }

    try:
        preview = v386.run_cycle(
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
        policy = uncertainty_policy(preview, loaded["state"])
        gate = autonomous_gate(preview, policy)

        if mutating and loaded.get("corruption_hold"):
            gate = {
                "status": "V387_STATE_CORRUPTION_HOLD",
                "allow_execution": False,
                "selected_action": policy.get("selected_action"),
                "selected_confidence": policy.get("selected_confidence"),
                "selected_uncertainty": policy.get("selected_uncertainty"),
                "recovery_only": False,
                "reasons": ["STATE_CORRUPTION_HOLD"],
                "hard_blocker_override": False,
                "market_direction_inferred": False,
            }

        base = preview
        if mutating and gate.get("allow_execution") is True:
            base = v386.run_cycle(
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
            if str(base.get("v386_status") or "") in getattr(v386, "_HOLD_STATUSES", set()):
                gate = {
                    "status": "V387_UPSTREAM_HOLD",
                    "allow_execution": False,
                    "selected_action": policy.get("selected_action"),
                    "selected_confidence": policy.get("selected_confidence"),
                    "selected_uncertainty": policy.get("selected_uncertainty"),
                    "recovery_only": False,
                    "reasons": [str(base.get("v386_status") or "V386_HOLD")],
                    "hard_blocker_override": False,
                    "market_direction_inferred": False,
                }

        proposals = feature_lifecycle(base, policy, loaded["state"])
        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v387_status": gate.get("status") if mutating else "PLAN_ONLY",
            "v387_uncertainty_policy": policy,
            "v387_autonomous_gate": gate,
            "v387_feature_lifecycle": proposals,
            "evolution_contract_v387": {
                "base_controller": "v386",
                "decision_inputs": [
                    "verified_neural_consensus",
                    "verified_sample_support",
                    "peer_local_agreement",
                    "operational_kpi",
                    "operational_drift",
                    "regime_transition",
                ],
                "market_adaptation": "operational_regime_kpi_drift_only_no_direction_prediction",
                "low_confidence_behavior": "revalidate_or_recovery_only",
                "feature_lifecycle": "shadow_canary_active_candidate_rollback",
                "source_level_activation": "protected_pr_ci_required",
                "peer_model_weights_imported": False,
                "peer_raw_state_imported": False,
                "git_write": False,
                "source_code_auto_generation": False,
                "source_code_auto_rewrite": False,
                "arbitrary_command_execution": False,
                "verification_bypass": False,
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

        state_write = {"status": "V387_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            nxt = _next_state(
                loaded["state"],
                policy,
                gate,
                proposals,
                now=moment,
            )
            state_write = save_state(nxt, state_file, bool(loaded.get("corruption_hold")))
            if not state_write.get("written") and gate.get("allow_execution") is True:
                result["v387_status"] = "V387_STATE_COMMIT_HOLD"
                result["execution"] = {
                    "status": "V387_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }
        result["v387_state_write"] = state_write

        if persist_outputs:
            peer_exchange = _persist_v386_summary(base, domain, root, moment)
            result["v387_peer_exchange_write"] = peer_exchange
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v387-report.tmp")
                result["v387_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v387_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }
        return result
    finally:
        if fd is not None:
            v386.v385._release_lock(fd)


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert SAFETY["uncertainty_aware_action_selection"] is True
    assert SAFETY["peer_model_weights_imported"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet/TCG uncertainty-aware mutual neural autonomy v387: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=sorted(v386.DOMAINS), default="tablet_gpt")
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
    return 2 if result.get("v387_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
