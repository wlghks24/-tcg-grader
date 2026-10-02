#!/usr/bin/env python3
"""V382: drift-aware adaptive meta-governor for Tablet GPT / TCG Grader.

V382 sits above the verified V381 adaptive policy controller. It adds:
- multi-objective KPI and long-horizon operational drift detection;
- neural-policy calibration monitoring from verified outcome evidence;
- conservative verified-reliability lower bounds and temporary quarantine;
- an advisory-only shadow challenger;
- persistent, bounded governance memory;
- non-executable feature contracts for source-level gaps.

V381 remains the mandatory mutation gate. V382 never generates/rewrites source
code, executes arbitrary commands, writes Git/main, bypasses verification,
promotes unverified facts/prices/grades, or infers market direction.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import stat
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v381 as v381
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v382"
CORE_CONTROLLER_VERSION = "v381"

STATE_PATH = ROOT / ".tablet_autonomy_v382_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v382_report.json"
FEATURE_CONTRACT_PATH = ROOT / "tablet_autonomy_feature_contracts_v382.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v382.lock"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_000_000
MAX_HISTORY = 96
DRIFT_HIGH = 0.50
DRIFT_MEDIUM = 0.25
KPI_DROP_HOLD = 0.15
CALIBRATION_HOLD = 0.45
QUARANTINE_SECONDS = 6 * 60 * 60

RECOVERY_ACTIONS = {
    "REFRESH_MARKET_DATA",
    "EXPAND_MARKET_COVERAGE",
    "RECHECK_DEGRADED_SOURCES",
}

_HOLD_STATUSES = set(getattr(v381, "_HOLD_STATUSES", set())) | {
    "V382_STATE_CORRUPTION_HOLD",
    "V382_LOCK_UNAVAILABLE",
    "V382_CONCURRENT_AUTONOMY_HOLD",
    "V382_STATE_COMMIT_HOLD",
    "V382_UPSTREAM_HOLD",
    "V382_DRIFT_RECOVERY_ONLY",
    "V382_VERIFIED_POLICY_REGRESSION_HOLD",
    "V382_KPI_REGRESSION_HOLD",
    "V382_NEURAL_CALIBRATION_HOLD",
}

SAFETY = dict(v381.SAFETY)
SAFETY.update({
    "multi_objective_verified_feedback_governor": True,
    "operational_concept_drift_detection": True,
    "operational_drift_market_direction_free": True,
    "neural_policy_calibration_monitoring": True,
    "neural_calibration_verified_outcomes_only": True,
    "verified_history_confidence_bound_required": True,
    "verified_regression_quarantine_enabled": True,
    "shadow_challenger_advisory_only": True,
    "persistent_gap_feature_contracts_enabled": True,
    "feature_contracts_non_executable": True,
    "feature_contracts_require_protected_pr_ci": True,
    "v381_gate_cannot_be_bypassed": True,
    "runtime_self_extension_allowlisted_only": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
    "price_or_grade_invention": False,
    "market_direction_inferred": False,
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


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "last_kpis": None,
        "last_market_regime": None,
        "last_model_signature": None,
        "last_exchange_digest": None,
        "last_calibration_error": None,
        "quarantines": {},
        "history": [],
    }


def _validate_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != STATE_SCHEMA_VERSION:
        return False
    if value.get("controller_version") != CONTROLLER_VERSION:
        return False
    if not isinstance(value.get("quarantines"), dict):
        return False
    history = value.get("history")
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        return False
    for action, row in value["quarantines"].items():
        if not isinstance(action, str) or len(action) > 160 or not isinstance(row, dict):
            return False
        if _parse_time(row.get("until")) is None:
            return False
        if not isinstance(row.get("reason"), str):
            return False
    for row in history:
        if not isinstance(row, dict):
            return False
    return True


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V382_STATE_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_STATE_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": type(exc).__name__,
        }
    if not _validate_state(value):
        return {
            "state": _default_state(),
            "status": "corrupt",
            "corruption_hold": True,
            "error_code": "V382_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], *, path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V382_STATE_CORRUPTION_HOLD", "written": False}
    if not _validate_state(state):
        return {"status": "V382_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v382-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "V382_STATE_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {"status": "V382_STATE_SAVED", "written": True}


def _market_regime(base: dict[str, Any]) -> str:
    market = base.get("market_adaptation_v381")
    if isinstance(market, dict):
        return str(market.get("regime") or "UNKNOWN")
    return "UNKNOWN"


def _exchange_digest(base: dict[str, Any]) -> str:
    exchange = base.get("information_exchange_memory_v381")
    if not isinstance(exchange, dict):
        return ""
    return str(exchange.get("input_digest") or "")[:128]


def _model_signature(base: dict[str, Any]) -> str:
    plan = base.get("plan") if isinstance(base.get("plan"), dict) else {}
    meta_scores = plan.get("meta_scores") if isinstance(plan.get("meta_scores"), dict) else {}
    decision = base.get("autonomous_decision") if isinstance(base.get("autonomous_decision"), dict) else {}
    neural = decision.get("neural_council") if isinstance(decision.get("neural_council"), dict) else {}
    policy = base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"), dict) else {}
    selection = policy.get("selection") if isinstance(policy.get("selection"), dict) else {}
    sanitized = {
        "meta_scores": {
            str(key): _finite(value)
            for key, value in sorted(meta_scores.items())
            if _finite(value) is not None
        },
        "neural": {
            "status": str(neural.get("status") or "")[:120],
            "confidence": _finite(neural.get("confidence")),
            "agreement": _finite(neural.get("agreement")),
        },
        "champion_action": selection.get("champion_action"),
    }
    return _digest(sanitized)


def kpis(base: dict[str, Any]) -> dict[str, Any]:
    dimensions = v381.v380.dimension_values(base)
    weights = {
        "policy_contract": 16,
        "safety_boundary": 18,
        "evidence_commit": 14,
        "state_integrity": 10,
        "market_freshness": 8,
        "market_coverage": 7,
        "source_health": 8,
        "neural_consensus": 5,
        "resource_headroom": 4,
        "recovery_integrity": 4,
        "candidate_risk": 3,
        "proposal_boundary": 3,
    }
    total = float(sum(weights.values()))
    score = sum(float(dimensions.get(key, 0.0)) * weight for key, weight in weights.items()) / total
    return {
        "score": round(_clamp(score), 6),
        "dimensions": dimensions,
        "digest_sha256": _digest(dimensions),
    }


def neural_calibration(base: dict[str, Any]) -> dict[str, Any]:
    policy = base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"), dict) else {}
    rows = policy.get("candidate_actions") if isinstance(policy.get("candidate_actions"), list) else []
    errors: list[float] = []
    verified_samples = 0
    action_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        count = int(row.get("verified_samples") or 0)
        reward_mean = _finite(row.get("reward_mean"))
        neural_score = _finite(row.get("neural_score"))
        if count < v381.MIN_POLICY_SAMPLES or reward_mean is None or neural_score is None:
            continue
        expected = _clamp((reward_mean + 1.0) / 2.0)
        errors.append(abs(_clamp(neural_score) - expected))
        verified_samples += count
        action_count += 1
    mae = sum(errors) / len(errors) if errors else None
    hold = bool(mae is not None and action_count >= 1 and verified_samples >= v381.MIN_POLICY_SAMPLES and mae >= CALIBRATION_HOLD)
    status = "INSUFFICIENT_VERIFIED_CALIBRATION"
    if mae is not None:
        status = "CALIBRATION_HOLD_RECOMMENDED" if hold else ("CALIBRATION_WATCH" if mae >= 0.25 else "CALIBRATION_HEALTHY")
    return {
        "status": status,
        "actions_compared": action_count,
        "verified_samples": verified_samples,
        "mean_absolute_error": round(mae, 6) if mae is not None else None,
        "hold_recommended": hold,
        "verified_outcomes_only": True,
        "model_weights_modified": False,
    }


def policy_reliability(base: dict[str, Any]) -> dict[str, Any]:
    policy = base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"), dict) else {}
    selection = policy.get("selection") if isinstance(policy.get("selection"), dict) else {}
    action = str(selection.get("champion_action") or "")
    stats = policy.get("verified_outcome_stats") if isinstance(policy.get("verified_outcome_stats"), dict) else {}
    row = stats.get(action) if action and isinstance(stats.get(action), dict) else {}
    samples = max(0, int(row.get("verified_samples") or 0))
    mean = _finite(row.get("reward_mean"))
    minimum = _finite(row.get("reward_min"))
    lcb = None
    if mean is not None and samples > 0:
        lcb = max(-1.0, mean - min(1.0, 1.0 / math.sqrt(max(1, samples))))
    quarantine = bool(
        action
        and samples >= v381.MIN_POLICY_SAMPLES
        and (
            (lcb is not None and lcb < -0.20)
            or (minimum is not None and minimum <= -0.90)
        )
    )
    evidence = [action, samples, mean, minimum, lcb]
    return {
        "action_id": action or None,
        "verified_samples": samples,
        "reward_mean": round(mean, 6) if mean is not None else None,
        "reward_min": round(minimum, 6) if minimum is not None else None,
        "lower_confidence_bound": round(lcb, 6) if lcb is not None else None,
        "quarantine_recommended": quarantine,
        "evidence_digest": _digest(evidence),
    }


def operational_drift(
    state: dict[str, Any],
    current_kpis: dict[str, Any],
    base: dict[str, Any],
    calibration: dict[str, Any],
) -> dict[str, Any]:
    previous_dimensions = {}
    last_kpis = state.get("last_kpis")
    if isinstance(last_kpis, dict) and isinstance(last_kpis.get("dimensions"), dict):
        previous_dimensions = last_kpis["dimensions"]

    tracked = (
        "market_freshness",
        "market_coverage",
        "source_health",
        "neural_consensus",
        "resource_headroom",
    )
    components: dict[str, float] = {}
    if previous_dimensions:
        for key in tracked:
            old = _finite(previous_dimensions.get(key))
            new = _finite(current_kpis["dimensions"].get(key))
            components[key] = round(abs((new or 0.0) - (old or 0.0)), 6)
    else:
        components = {key: 0.0 for key in tracked}

    score = max(components.values(), default=0.0)
    regime = _market_regime(base)
    if state.get("last_market_regime") and state.get("last_market_regime") != regime:
        score = max(score, 0.35)

    signature = _model_signature(base)
    if state.get("last_model_signature") and state.get("last_model_signature") != signature:
        score = max(score, 0.25)

    exchange_digest = _exchange_digest(base)
    if state.get("last_exchange_digest") and exchange_digest and state.get("last_exchange_digest") != exchange_digest:
        score = max(score, 0.20)

    previous_calibration = _finite(state.get("last_calibration_error"))
    current_calibration = _finite(calibration.get("mean_absolute_error"))
    calibration_delta = 0.0
    if previous_calibration is not None and current_calibration is not None:
        calibration_delta = abs(current_calibration - previous_calibration)
        score = max(score, min(1.0, calibration_delta))

    level = "HIGH" if score >= DRIFT_HIGH else ("MEDIUM" if score >= DRIFT_MEDIUM else "LOW")
    return {
        "level": level,
        "score": round(score, 6),
        "components": components,
        "market_regime": regime,
        "model_signature": signature,
        "exchange_digest": exchange_digest or None,
        "neural_calibration_delta": round(calibration_delta, 6),
        "market_direction_inferred": False,
    }


def shadow_challenger(base: dict[str, Any]) -> dict[str, Any]:
    policy = base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"), dict) else {}
    selection = policy.get("selection") if isinstance(policy.get("selection"), dict) else {}
    champion = str(selection.get("champion_action") or "")
    rows = policy.get("candidate_actions") if isinstance(policy.get("candidate_actions"), list) else []
    candidates = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("action_id") or "") != champion
    ]
    candidates.sort(
        key=lambda row: (
            -float(_finite(row.get("score")) or 0.0),
            -int(row.get("verified_samples") or 0),
            str(row.get("action_id") or ""),
        )
    )
    candidate = None
    if candidates:
        row = candidates[0]
        candidate = {
            "action_id": str(row.get("action_id") or "")[:160],
            "score": round(float(_finite(row.get("score")) or 0.0), 6),
            "verified_samples": int(row.get("verified_samples") or 0),
            "promotion_eligible": row.get("promotion_eligible") is True,
        }
    return {
        "available": candidate is not None,
        "auto_execute": False,
        "candidate": candidate,
    }


def _feature_contract(contract_id: str, gap_kind: str, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "contract_id": contract_id[:190],
        "gap_kind": gap_kind[:80],
        "reason": reason[:240],
        "evidence": evidence,
        "auto_execute": False,
        "auto_generate_source": False,
        "git_write": False,
        "protected_pr_ci_required": True,
        "acceptance_sequence": [
            "targeted_tests",
            "related_regression",
            "full_current_runtime",
            "repository_integrity",
            "tablet_gpt_alignment",
            "actual_output_validation",
        ],
        "rollback_triggers": [
            "regression_detected",
            "integrity_failure",
            "alignment_failure",
            "provenance_loss",
            "security_boundary_regression",
        ],
    }


def feature_contracts(
    base: dict[str, Any],
    drift: dict[str, Any],
    calibration: dict[str, Any],
) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    proposals = base.get("source_feature_proposals_v381")
    if isinstance(proposals, list):
        for row in proposals[:24]:
            if not isinstance(row, dict):
                continue
            proposal_id = str(row.get("id") or row.get("proposal_id") or "")
            if not proposal_id:
                continue
            contracts.append(_feature_contract(
                f"V382:{proposal_id}",
                str(row.get("kind") or row.get("gap_kind") or "source_feature"),
                str(row.get("reason") or "v381_persistent_gap"),
                {"proposal_id": proposal_id, "source": "v381_verified_gap"},
            ))

    if calibration.get("hold_recommended") is True:
        contracts.append(_feature_contract(
            "V382:NEURAL_CALIBRATION_GAP",
            "neural_calibration",
            "verified neural-policy calibration error exceeded bounded threshold",
            {
                "mean_absolute_error": calibration.get("mean_absolute_error"),
                "verified_samples": calibration.get("verified_samples"),
            },
        ))

    if drift.get("level") == "HIGH" and not contracts:
        contracts.append(_feature_contract(
            "V382:HIGH_OPERATIONAL_DRIFT_DIAGNOSTIC",
            "operational_drift",
            "high operational drift has no existing source-level contract",
            {
                "drift_score": drift.get("score"),
                "components": drift.get("components"),
                "market_regime": drift.get("market_regime"),
            },
        ))
    return contracts[:32]


def _active_quarantine(state: dict[str, Any], action: str, now: datetime) -> bool:
    if not action:
        return False
    row = state.get("quarantines", {}).get(action)
    if not isinstance(row, dict):
        return False
    until = _parse_time(row.get("until"))
    return bool(until and until > now)


def autonomous_gate(
    base: dict[str, Any],
    state: dict[str, Any],
    drift: dict[str, Any],
    reliability: dict[str, Any],
    current_kpis: dict[str, Any],
    calibration: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    upstream = base.get("autonomous_decision") if isinstance(base.get("autonomous_decision"), dict) else {}
    action = str(reliability.get("action_id") or "")
    recovery = action in RECOVERY_ACTIONS
    reasons: list[str] = []

    if upstream.get("allow_execution") is not True:
        reasons.append("V381_UPSTREAM_GATE_HOLD")
    if _active_quarantine(state, action, now):
        reasons.append("VERIFIED_ACTION_QUARANTINE")
    if reliability.get("quarantine_recommended") is True:
        reasons.append("VERIFIED_POLICY_REGRESSION")

    previous_score = None
    last_kpis = state.get("last_kpis")
    if isinstance(last_kpis, dict):
        previous_score = _finite(last_kpis.get("score"))
    if (
        previous_score is not None
        and not recovery
        and previous_score - float(current_kpis["score"]) > KPI_DROP_HOLD
    ):
        reasons.append("KPI_REGRESSION")

    if drift.get("level") == "HIGH" and not recovery:
        reasons.append("HIGH_DRIFT_RECOVERY_ONLY")

    if calibration.get("hold_recommended") is True and not recovery:
        reasons.append("NEURAL_CALIBRATION_HOLD")

    if not reasons:
        status = "ALLOW_BOUNDED"
    elif "V381_UPSTREAM_GATE_HOLD" in reasons:
        status = "V382_UPSTREAM_HOLD"
    elif any(reason in reasons for reason in ("VERIFIED_ACTION_QUARANTINE", "VERIFIED_POLICY_REGRESSION")):
        status = "V382_VERIFIED_POLICY_REGRESSION_HOLD"
    elif "KPI_REGRESSION" in reasons:
        status = "V382_KPI_REGRESSION_HOLD"
    elif "NEURAL_CALIBRATION_HOLD" in reasons:
        status = "V382_NEURAL_CALIBRATION_HOLD"
    else:
        status = "V382_DRIFT_RECOVERY_ONLY"

    return {
        "status": status,
        "allow_execution": not reasons,
        "directive": "EXECUTE_VERIFIED_V381_SELECTION" if not reasons else "HOLD_AND_OBSERVE",
        "reasons": reasons,
        "selected_action": action or None,
        "recovery_action": recovery,
        "hard_blocker_override": False,
    }


def _next_state(
    state: dict[str, Any],
    base: dict[str, Any],
    current_kpis: dict[str, Any],
    drift: dict[str, Any],
    gate: dict[str, Any],
    reliability: dict[str, Any],
    calibration: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    next_state = deepcopy(state)
    quarantines = dict(next_state.get("quarantines") or {})
    for action, row in list(quarantines.items()):
        until = _parse_time(row.get("until")) if isinstance(row, dict) else None
        if until is None or until <= now:
            quarantines.pop(action, None)

    action = str(reliability.get("action_id") or "")
    if action and reliability.get("quarantine_recommended") is True:
        quarantines[action] = {
            "until": (now + timedelta(seconds=QUARANTINE_SECONDS)).isoformat(timespec="seconds"),
            "reason": "verified_policy_regression",
            "evidence_digest": str(reliability.get("evidence_digest") or "")[:128],
        }

    history = list(next_state.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "gate_status": str(gate.get("status") or "UNKNOWN")[:160],
        "selected_action": action or None,
        "kpi_score": current_kpis.get("score"),
        "drift_score": drift.get("score"),
        "drift_level": drift.get("level"),
        "calibration_error": calibration.get("mean_absolute_error"),
        "market_regime": _market_regime(base),
    })

    next_state.update({
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "last_kpis": current_kpis,
        "last_market_regime": _market_regime(base),
        "last_model_signature": _model_signature(base),
        "last_exchange_digest": _exchange_digest(base),
        "last_calibration_error": calibration.get("mean_absolute_error"),
        "quarantines": quarantines,
        "history": history[-MAX_HISTORY:],
    })
    return next_state


def _acquire_lock(path: Path) -> tuple[int | None, dict[str, Any]]:
    fd = None
    try:
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            return None, {"status": "V382_LOCK_UNAVAILABLE", "error_code": "NOT_REGULAR_FILE"}
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd, {"status": "V382_LOCK_ACQUIRED", "error_code": None}
    except BlockingIOError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return None, {"status": "V382_CONCURRENT_AUTONOMY_HOLD", "error_code": "LOCK_BUSY"}
    except OSError as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return None, {"status": "V382_LOCK_UNAVAILABLE", "error_code": type(exc).__name__}


def _release_lock(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def run_cycle(
    *,
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    proc_root: Path = Path("/proc"),
    state_path=None,
    capability_path=None,
    meta_model_path=None,
    meta_outcomes_path=None,
    skill_state_path=None,
    skill_outcomes_path=None,
    journal_path=None,
    core_lock_path=None,
    v380_lock_path=None,
    v381_lock_path=None,
    quality_policy_path=None,
    policy_state_path=None,
    v382_state_path=None,
    v382_lock_path=None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    lock_info = {"status": "V382_LOCK_NOT_REQUIRED", "error_code": None}
    fd = None

    if mutating:
        fd, lock_info = _acquire_lock(v382_lock_path or (root / LOCK_PATH.name))
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "core_controller_version": CORE_CONTROLLER_VERSION,
                "v382_status": lock_info["status"],
                "execution": {
                    "status": lock_info["status"],
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                },
                "v382_single_run_lock": lock_info,
                "safety": SAFETY,
            }

    state_file = v382_state_path or (root / STATE_PATH.name)
    kwargs = dict(
        root=root,
        now=moment,
        proc_root=proc_root,
        state_path=state_path,
        capability_path=capability_path,
        meta_model_path=meta_model_path,
        meta_outcomes_path=meta_outcomes_path,
        skill_state_path=skill_state_path,
        skill_outcomes_path=skill_outcomes_path,
        journal_path=journal_path,
        core_lock_path=core_lock_path,
        v380_lock_path=v380_lock_path,
        lock_path=v381_lock_path,
        quality_policy_path=quality_policy_path,
        policy_state_path=policy_state_path,
        persist_outputs=False,
    )

    try:
        preview = v381.run_cycle(
            execute=False,
            apply_capabilities=False,
            train_meta=False,
            apply_skills=False,
            **kwargs,
        )
        loaded = load_state(state_file)
        current_kpis = kpis(preview)
        calibration = neural_calibration(preview)
        reliability = policy_reliability(preview)
        drift = operational_drift(loaded["state"], current_kpis, preview, calibration)
        shadow = shadow_challenger(preview)
        contracts = feature_contracts(preview, drift, calibration)

        if mutating and loaded.get("corruption_hold") is True:
            gate = {
                "status": "V382_STATE_CORRUPTION_HOLD",
                "allow_execution": False,
                "directive": "HOLD_AND_OBSERVE",
                "reasons": ["STATE_CORRUPTION_HOLD"],
                "selected_action": reliability.get("action_id"),
                "recovery_action": False,
                "hard_blocker_override": False,
            }
        else:
            gate = autonomous_gate(
                preview,
                loaded["state"],
                drift,
                reliability,
                current_kpis,
                calibration,
                now=moment,
            )

        base = preview
        if mutating and gate.get("allow_execution") is True:
            base = v381.run_cycle(
                execute=execute,
                apply_capabilities=apply_capabilities,
                train_meta=train_meta,
                apply_skills=apply_skills,
                **kwargs,
            )
            inner_status = str(base.get("v381_status") or "")
            if inner_status in getattr(v381, "_HOLD_STATUSES", set()):
                gate = {
                    "status": "V382_UPSTREAM_HOLD",
                    "allow_execution": False,
                    "directive": "HOLD_AND_OBSERVE",
                    "reasons": [inner_status],
                    "selected_action": reliability.get("action_id"),
                    "recovery_action": reliability.get("action_id") in RECOVERY_ACTIONS,
                    "hard_blocker_override": False,
                }

        final_kpis = kpis(base)
        final_calibration = neural_calibration(base)
        final_reliability = policy_reliability(base)

        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v382_status": gate.get("status") if mutating else "PLAN_ONLY",
            "v382_kpis": final_kpis,
            "v382_drift": drift,
            "v382_neural_calibration": final_calibration,
            "v382_verified_reliability": final_reliability,
            "v382_shadow_challenger": shadow,
            "v382_feature_contracts": contracts,
            "v382_autonomous_gate": gate,
            "v382_single_run_lock": lock_info,
            "evolution_contract_v382": {
                "core_controller": CORE_CONTROLLER_VERSION,
                "verified_outcome_feedback_only": True,
                "neural_calibration": "advisory_verified_outcomes_only",
                "drift_scope": "operational_freshness_coverage_source_health_neural_resource",
                "high_drift_behavior": "recovery_actions_only",
                "verified_regression_behavior": "temporary_quarantine",
                "shadow_challenger": "advisory_only",
                "runtime_self_extension": "v381_allowlisted_declarative_capabilities_only",
                "source_level_new_functions": "feature_contract_requires_protected_pr_ci_full_validation",
                "market_direction_prediction": False,
                "external_human_review_claimed": False,
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

        state_write = {"status": "V382_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            next_state = _next_state(
                loaded["state"],
                base,
                final_kpis,
                drift,
                gate,
                final_reliability,
                final_calibration,
                now=moment,
            )
            state_write = save_state(
                next_state,
                path=state_file,
                corruption_hold=loaded.get("corruption_hold") is True,
            )
            if state_write.get("written") is not True and gate.get("allow_execution") is True:
                result["v382_status"] = "V382_STATE_COMMIT_HOLD"
        result["v382_state"] = {
            "load_status": loaded.get("status"),
            "corruption_hold": loaded.get("corruption_hold") is True,
            "write": state_write,
        }

        if mutating and contracts:
            try:
                atomic_write_json(
                    root / FEATURE_CONTRACT_PATH.name,
                    {
                        "schema_version": 1,
                        "controller_version": CONTROLLER_VERSION,
                        "generated_at": moment.isoformat(timespec="seconds"),
                        "auto_execute": False,
                        "protected_pr_ci_required": True,
                        "contracts": contracts,
                    },
                    suffix=".v382-feature-contracts.tmp",
                )
                result["v382_feature_contracts_write"] = {"status": "SAVED", "written": True}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v382_feature_contracts_write"] = {
                    "status": "WRITE_FAILED",
                    "written": False,
                    "error_code": type(exc).__name__,
                }

        if persist_outputs:
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v382-report.tmp")
                result["v382_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v382_runtime_output"] = {
                    "status": "WRITE_FAILED",
                    "error_code": type(exc).__name__,
                }

        return result
    finally:
        if fd is not None:
            _release_lock(fd)


def self_test() -> None:
    assert SAFETY["multi_objective_verified_feedback_governor"] is True
    assert SAFETY["operational_concept_drift_detection"] is True
    assert SAFETY["neural_policy_calibration_monitoring"] is True
    assert SAFETY["verified_history_confidence_bound_required"] is True
    assert SAFETY["shadow_challenger_advisory_only"] is True
    assert SAFETY["feature_contracts_non_executable"] is True
    assert SAFETY["v381_gate_cannot_be_bypassed"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet adaptive meta-governor v382: PASS")


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
    return 2 if result.get("v382_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
