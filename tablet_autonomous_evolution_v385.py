#!/usr/bin/env python3
"""V385: regime-aware neural autonomy and safe capability self-extension.

V385 sits above V382. It adds a small online neural policy model trained only
from verified V381/V382 outcome aggregates, regime-conditioned memory,
resource-aware scheduling, change-point detection, canary capability recipes,
and prioritized non-executable source-feature contracts.

The controller may autonomously choose whether to learn, which verified
capability recipe to keep in shadow/canary/active state, and how much compute
to spend. It cannot generate or rewrite source code, execute arbitrary
commands, write Git/main, weaken verification, invent market direction,
facts, prices or grades, or bypass V382/V381 hard gates.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v382 as v382
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v385"
CORE_CONTROLLER_VERSION = "v382"

STATE_PATH = ROOT / ".tablet_autonomy_v385_state.json"
REPORT_PATH = ROOT / "tablet_autonomy_v385_report.json"
CAPABILITY_REGISTRY_PATH = ROOT / "tablet_autonomy_capability_registry_v385.json"
FEATURE_CONTRACT_PATH = ROOT / "tablet_autonomy_feature_contracts_v385.json"
LOCK_PATH = ROOT / ".tablet_autonomy_execution_v385.lock"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_500_000
MAX_HISTORY = 128
MAX_REGIMES = 16
MAX_ACTIONS_PER_REGIME = 32
INPUT_DIM = 14
HIDDEN_DIM = 8
MIN_VERIFIED_SAMPLES = max(3, int(getattr(v382.v381, "MIN_POLICY_SAMPLES", 3)))
TRAIN_STEPS = 24
BASE_LR = 0.035
KPI_CANARY_DROP = 0.08
CHANGE_POINT_THRESHOLD = 0.18
RESOURCE_LOW = 0.30
RESOURCE_CRITICAL = 0.16
CANARY_MIN_OBSERVATIONS = 3

RECOVERY_ACTIONS = set(getattr(v382, "RECOVERY_ACTIONS", set()))

PRIMITIVES = {
    "REFRESH_VERIFIED_MARKET": {
        "kind": "recovery",
        "requires": ["market_freshness"],
        "effects": ["request_verified_refresh"],
    },
    "RECHECK_DEGRADED_SOURCES": {
        "kind": "recovery",
        "requires": ["source_health"],
        "effects": ["request_source_recheck"],
    },
    "EXPAND_VERIFIED_COVERAGE": {
        "kind": "coverage",
        "requires": ["market_coverage"],
        "effects": ["request_allowlisted_coverage_expansion"],
    },
    "RECALIBRATE_NEURAL_POLICY": {
        "kind": "learning",
        "requires": ["verified_outcomes"],
        "effects": ["train_verified_neural_policy"],
    },
    "CONSERVE_RESOURCE_BUDGET": {
        "kind": "resource",
        "requires": ["resource_headroom"],
        "effects": ["reduce_optional_learning_work"],
    },
    "REPLAY_REGIME_VERIFIED_HISTORY": {
        "kind": "learning",
        "requires": ["verified_outcomes", "market_regime"],
        "effects": ["use_regime_conditioned_memory"],
    },
}
PRIMITIVE_NAMES = frozenset(PRIMITIVES)

_HOLD_STATUSES = set(getattr(v382, "_HOLD_STATUSES", set())) | {
    "V385_STATE_CORRUPTION_HOLD",
    "V385_LOCK_UNAVAILABLE",
    "V385_CONCURRENT_AUTONOMY_HOLD",
    "V385_UPSTREAM_HOLD",
    "V385_RESOURCE_CRITICAL_HOLD",
    "V385_CHANGE_POINT_RECOVERY_ONLY",
    "V385_NEURAL_DISAGREEMENT_HOLD",
    "V385_STATE_COMMIT_HOLD",
}

SAFETY = dict(v382.SAFETY)
SAFETY.update({
    "verified_online_neural_policy": True,
    "verified_outcomes_only_training": True,
    "regime_conditioned_policy_memory": True,
    "resource_aware_scheduler": True,
    "change_point_detection_operational_only": True,
    "market_direction_inferred": False,
    "capability_self_extension_declarative_only": True,
    "capability_primitives_allowlisted_only": True,
    "capability_canary_before_activation": True,
    "capability_rollback_on_verified_kpi_drop": True,
    "source_feature_planner_non_executable": True,
    "source_feature_requires_protected_pr_ci": True,
    "v382_gate_cannot_be_bypassed": True,
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


def _digest(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_unit(text: str) -> float:
    raw = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(raw[:8], "big") / float((1 << 64) - 1)


def _tanh(value: float) -> float:
    return math.tanh(max(-20.0, min(20.0, value)))


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _initial_network() -> dict[str, Any]:
    w1 = []
    for hidden in range(HIDDEN_DIM):
        row = []
        for feature in range(INPUT_DIM):
            unit = _stable_unit(f"v385:w1:{hidden}:{feature}")
            row.append(round((unit - 0.5) * 0.12, 8))
        w1.append(row)
    b1 = [0.0 for _ in range(HIDDEN_DIM)]
    w2 = [round((_stable_unit(f"v385:w2:{hidden}") - 0.5) * 0.12, 8) for hidden in range(HIDDEN_DIM)]
    return {"w1": w1, "b1": b1, "w2": w2, "b2": 0.0, "updates": 0}


def _valid_network(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    w1, b1, w2 = value.get("w1"), value.get("b1"), value.get("w2")
    if not isinstance(w1, list) or len(w1) != HIDDEN_DIM:
        return False
    if not isinstance(b1, list) or len(b1) != HIDDEN_DIM:
        return False
    if not isinstance(w2, list) or len(w2) != HIDDEN_DIM:
        return False
    for row in w1:
        if not isinstance(row, list) or len(row) != INPUT_DIM:
            return False
        if any(_finite(item) is None or abs(float(item)) > 8.0 for item in row):
            return False
    if any(_finite(item) is None or abs(float(item)) > 8.0 for item in b1 + w2):
        return False
    if _finite(value.get("b2")) is None or abs(float(value.get("b2"))) > 8.0:
        return False
    return isinstance(value.get("updates"), int) and 0 <= value["updates"] <= 1_000_000


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "network": _initial_network(),
        "regime_memory": {},
        "capability_registry": {},
        "gap_counts": {},
        "last_kpi_score": None,
        "ewma_kpi": None,
        "ewma_drift": None,
        "history": [],
    }


def _validate_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if value.get("schema_version") != STATE_SCHEMA_VERSION or value.get("controller_version") != CONTROLLER_VERSION:
        return False
    if not _valid_network(value.get("network")):
        return False
    if not isinstance(value.get("regime_memory"), dict) or len(value["regime_memory"]) > MAX_REGIMES:
        return False
    if not isinstance(value.get("capability_registry"), dict) or len(value["capability_registry"]) > 64:
        return False
    if not isinstance(value.get("gap_counts"), dict) or len(value["gap_counts"]) > 128:
        return False
    history = value.get("history")
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        return False
    for regime, rows in value["regime_memory"].items():
        if not isinstance(regime, str) or len(regime) > 80 or not isinstance(rows, dict) or len(rows) > MAX_ACTIONS_PER_REGIME:
            return False
    for recipe_id, row in value["capability_registry"].items():
        if not isinstance(recipe_id, str) or len(recipe_id) > 160 or not isinstance(row, dict):
            return False
        steps = row.get("steps")
        if not isinstance(steps, list) or not steps or len(steps) > 3 or any(step not in PRIMITIVE_NAMES for step in steps):
            return False
        if row.get("status") not in {"shadow", "canary", "active", "rolled_back"}:
            return False
    return True


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_V385_STATE_PATH")
        value = json.loads(safe_read_text(path, max_bytes=MAX_STATE_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {"state": _default_state(), "status": "corrupt", "corruption_hold": True, "error_code": type(exc).__name__}
    if not _validate_state(value):
        return {"state": _default_state(), "status": "corrupt", "corruption_hold": True, "error_code": "V385_STATE_SCHEMA_INVALID"}
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], *, path: Path, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V385_STATE_CORRUPTION_HOLD", "written": False}
    if not _validate_state(state):
        return {"status": "V385_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v385-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V385_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V385_STATE_SAVED", "written": True}


def _market_regime(base: dict[str, Any]) -> str:
    market = base.get("market_adaptation_v381")
    if isinstance(market, dict):
        return str(market.get("regime") or "UNKNOWN")[:80]
    drift = base.get("v382_drift")
    if isinstance(drift, dict):
        return str(drift.get("market_regime") or "UNKNOWN")[:80]
    return "UNKNOWN"


def _dimensions(base: dict[str, Any]) -> dict[str, float]:
    kpi = base.get("v382_kpis") if isinstance(base.get("v382_kpis"), dict) else {}
    rows = kpi.get("dimensions") if isinstance(kpi.get("dimensions"), dict) else {}
    return {str(key): _clamp(float(value)) for key, value in rows.items() if _finite(value) is not None}


def _global_features(base: dict[str, Any]) -> list[float]:
    dims = _dimensions(base)
    kpi = base.get("v382_kpis") if isinstance(base.get("v382_kpis"), dict) else {}
    drift = base.get("v382_drift") if isinstance(base.get("v382_drift"), dict) else {}
    calibration = base.get("v382_neural_calibration") if isinstance(base.get("v382_neural_calibration"), dict) else {}
    kpi_score = _finite(kpi.get("score"))
    drift_score = _finite(drift.get("score"))
    cal = _finite(calibration.get("mean_absolute_error"))
    regime = _market_regime(base)
    return [
        _clamp(kpi_score if kpi_score is not None else 0.5),
        _clamp(1.0 - (drift_score if drift_score is not None else 0.5)),
        dims.get("market_freshness", 0.5),
        dims.get("market_coverage", 0.5),
        dims.get("source_health", 0.5),
        dims.get("neural_consensus", 0.5),
        dims.get("resource_headroom", 0.5),
        _clamp(1.0 - (cal if cal is not None else 0.5)),
        _stable_unit(f"regime:{regime}"),
        1.0 if str(drift.get("level") or "") == "HIGH" else 0.0,
    ]


def _action_features(action: str) -> list[float]:
    return [_stable_unit(f"action:{slot}:{action}") for slot in range(4)]


def feature_vector(base: dict[str, Any], action: str) -> list[float]:
    vector = _global_features(base) + _action_features(action)
    if len(vector) != INPUT_DIM:
        raise ValueError("V385_FEATURE_DIMENSION_MISMATCH")
    return vector


def _forward(network: dict[str, Any], vector: list[float]) -> tuple[list[float], float]:
    hidden = []
    for index in range(HIDDEN_DIM):
        total = float(network["b1"][index])
        total += sum(float(weight) * float(value) for weight, value in zip(network["w1"][index], vector))
        hidden.append(_tanh(total))
    output = float(network["b2"]) + sum(float(weight) * value for weight, value in zip(network["w2"], hidden))
    return hidden, _sigmoid(output)


def _candidate_rows(base: dict[str, Any]) -> list[dict[str, Any]]:
    policy = base.get("policy_evolution_v381") if isinstance(base.get("policy_evolution_v381"), dict) else {}
    rows = policy.get("candidate_actions") if isinstance(policy.get("candidate_actions"), list) else []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action_id") or "")[:160]
        if not action:
            continue
        result.append(row)
    return result[:48]


def train_verified_network(network: dict[str, Any], base: dict[str, Any], *, learning_rate: float) -> dict[str, Any]:
    model = deepcopy(network)
    examples = []
    for row in _candidate_rows(base):
        samples = max(0, int(row.get("verified_samples") or 0))
        reward = _finite(row.get("reward_mean"))
        action = str(row.get("action_id") or "")
        if samples < MIN_VERIFIED_SAMPLES or reward is None:
            continue
        target = _clamp((reward + 1.0) / 2.0)
        examples.append((action, target, min(8, samples)))
    if not examples:
        return {"network": model, "trained": False, "examples": 0, "loss": None, "verified_outcomes_only": True}

    losses = []
    steps = min(TRAIN_STEPS, max(4, len(examples) * 4))
    for step in range(steps):
        action, target, weight = examples[step % len(examples)]
        vector = feature_vector(base, action)
        hidden, prediction = _forward(model, vector)
        error = prediction - target
        losses.append(error * error)
        output_grad = 2.0 * error * prediction * (1.0 - prediction) * min(2.0, 0.5 + weight / 8.0)
        old_w2 = [float(value) for value in model["w2"]]
        for h in range(HIDDEN_DIM):
            model["w2"][h] = round(max(-4.0, min(4.0, float(model["w2"][h]) - learning_rate * output_grad * hidden[h])), 8)
        model["b2"] = round(max(-4.0, min(4.0, float(model["b2"]) - learning_rate * output_grad)), 8)
        for h in range(HIDDEN_DIM):
            hidden_grad = output_grad * old_w2[h] * (1.0 - hidden[h] * hidden[h])
            for f in range(INPUT_DIM):
                model["w1"][h][f] = round(max(-4.0, min(4.0, float(model["w1"][h][f]) - learning_rate * hidden_grad * vector[f])), 8)
            model["b1"][h] = round(max(-4.0, min(4.0, float(model["b1"][h]) - learning_rate * hidden_grad)), 8)
    model["updates"] = int(model.get("updates") or 0) + steps
    return {
        "network": model,
        "trained": True,
        "examples": len(examples),
        "steps": steps,
        "loss": round(sum(losses) / len(losses), 8) if losses else None,
        "verified_outcomes_only": True,
    }


def regime_memory_update(state: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    memory = deepcopy(state.get("regime_memory") or {})
    regime = _market_regime(base)
    rows = dict(memory.get(regime) or {})
    for item in _candidate_rows(base):
        action = str(item.get("action_id") or "")[:160]
        samples = max(0, int(item.get("verified_samples") or 0))
        reward = _finite(item.get("reward_mean"))
        if not action or samples < MIN_VERIFIED_SAMPLES or reward is None:
            continue
        previous = rows.get(action) if isinstance(rows.get(action), dict) else {}
        previous_count = max(0, int(previous.get("observations") or 0))
        rows[action] = {
            "observations": min(9999, previous_count + 1),
            "verified_samples": samples,
            "reward_mean": round(max(-1.0, min(1.0, reward)), 6),
            "last_seen_digest": _digest([regime, action, samples, round(reward, 6)]),
        }
    rows = dict(sorted(rows.items(), key=lambda pair: (-int(pair[1].get("observations") or 0), pair[0]))[:MAX_ACTIONS_PER_REGIME])
    memory[regime] = rows
    return dict(list(memory.items())[-MAX_REGIMES:])


def neural_policy_scores(network: dict[str, Any], state: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    regime = _market_regime(base)
    memory = state.get("regime_memory", {}).get(regime, {}) if isinstance(state.get("regime_memory"), dict) else {}
    scored = []
    for row in _candidate_rows(base):
        action = str(row.get("action_id") or "")
        _hidden, neural = _forward(network, feature_vector(base, action))
        upstream = _finite(row.get("score"))
        reward = _finite(row.get("reward_mean"))
        samples = max(0, int(row.get("verified_samples") or 0))
        regime_row = memory.get(action) if isinstance(memory, dict) and isinstance(memory.get(action), dict) else {}
        regime_reward = _finite(regime_row.get("reward_mean"))
        verified_component = _clamp(((reward if reward is not None else 0.0) + 1.0) / 2.0)
        regime_component = _clamp(((regime_reward if regime_reward is not None else (reward or 0.0)) + 1.0) / 2.0)
        sample_confidence = _clamp(samples / float(max(MIN_VERIFIED_SAMPLES * 4, 1)))
        combined = (
            0.34 * neural
            + 0.28 * _clamp(upstream if upstream is not None else 0.5)
            + 0.23 * verified_component
            + 0.15 * regime_component
        )
        combined *= 0.85 + 0.15 * sample_confidence
        scored.append({
            "action_id": action,
            "score": round(_clamp(combined), 6),
            "neural_score": round(neural, 6),
            "verified_samples": samples,
            "reward_mean": round(reward, 6) if reward is not None else None,
            "regime_reward_mean": round(regime_reward, 6) if regime_reward is not None else None,
        })
    scored.sort(key=lambda row: (-row["score"], -row["verified_samples"], row["action_id"]))
    return {
        "regime": regime,
        "candidates": scored,
        "selected_action": scored[0]["action_id"] if scored else None,
        "selected_score": scored[0]["score"] if scored else None,
        "market_direction_inferred": False,
    }


def change_point(state: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    kpi = base.get("v382_kpis") if isinstance(base.get("v382_kpis"), dict) else {}
    drift = base.get("v382_drift") if isinstance(base.get("v382_drift"), dict) else {}
    current_kpi = _finite(kpi.get("score"))
    current_drift = _finite(drift.get("score"))
    prior_kpi = _finite(state.get("ewma_kpi"))
    prior_drift = _finite(state.get("ewma_drift"))
    if current_kpi is None:
        current_kpi = 0.5
    if current_drift is None:
        current_drift = 0.5
    ewma_kpi = current_kpi if prior_kpi is None else 0.25 * current_kpi + 0.75 * prior_kpi
    ewma_drift = current_drift if prior_drift is None else 0.25 * current_drift + 0.75 * prior_drift
    surprise = max(abs(current_kpi - ewma_kpi), abs(current_drift - ewma_drift))
    detected = surprise >= CHANGE_POINT_THRESHOLD
    return {
        "detected": detected,
        "surprise": round(surprise, 6),
        "ewma_kpi": round(ewma_kpi, 6),
        "ewma_drift": round(ewma_drift, 6),
        "scope": "operational_only",
        "market_direction_inferred": False,
    }


def _gap_signals(base: dict[str, Any]) -> dict[str, float]:
    dims = _dimensions(base)
    calibration = base.get("v382_neural_calibration") if isinstance(base.get("v382_neural_calibration"), dict) else {}
    cal = _finite(calibration.get("mean_absolute_error"))
    return {
        "freshness_gap": 1.0 - dims.get("market_freshness", 0.5),
        "coverage_gap": 1.0 - dims.get("market_coverage", 0.5),
        "source_gap": 1.0 - dims.get("source_health", 0.5),
        "resource_gap": 1.0 - dims.get("resource_headroom", 0.5),
        "calibration_gap": _clamp(cal if cal is not None else 0.0),
    }


def forge_capability(state: dict[str, Any], base: dict[str, Any], cp: dict[str, Any]) -> dict[str, Any]:
    signals = _gap_signals(base)
    ranked = sorted(signals.items(), key=lambda pair: (-pair[1], pair[0]))
    steps: list[str] = []
    for key, value in ranked:
        if value < 0.20:
            continue
        primitive = {
            "freshness_gap": "REFRESH_VERIFIED_MARKET",
            "coverage_gap": "EXPAND_VERIFIED_COVERAGE",
            "source_gap": "RECHECK_DEGRADED_SOURCES",
            "resource_gap": "CONSERVE_RESOURCE_BUDGET",
            "calibration_gap": "RECALIBRATE_NEURAL_POLICY",
        }[key]
        if primitive not in steps:
            steps.append(primitive)
        if len(steps) >= 2:
            break
    if cp.get("detected") is True and "REPLAY_REGIME_VERIFIED_HISTORY" not in steps and len(steps) < 3:
        steps.append("REPLAY_REGIME_VERIFIED_HISTORY")
    if not steps:
        steps = ["REPLAY_REGIME_VERIFIED_HISTORY"]

    recipe_id = "V385:" + _digest([_market_regime(base), steps])[:20]
    registry = state.get("capability_registry") if isinstance(state.get("capability_registry"), dict) else {}
    existing = registry.get(recipe_id) if isinstance(registry.get(recipe_id), dict) else {}
    observations = max(0, int(existing.get("observations") or 0)) + 1
    status = str(existing.get("status") or "shadow")
    previous_kpi = _finite(existing.get("activation_kpi"))
    current_kpi = _finite((base.get("v382_kpis") or {}).get("score")) if isinstance(base.get("v382_kpis"), dict) else None

    if status == "active" and previous_kpi is not None and current_kpi is not None and previous_kpi - current_kpi > KPI_CANARY_DROP:
        status = "rolled_back"
    elif status == "shadow" and observations >= 2:
        status = "canary"
    elif status == "canary" and observations >= CANARY_MIN_OBSERVATIONS:
        status = "active"

    return {
        "recipe_id": recipe_id,
        "steps": steps,
        "status": status,
        "observations": observations,
        "activation_kpi": current_kpi if status in {"canary", "active"} else previous_kpi,
        "auto_execute_commands": False,
        "source_code_generated": False,
        "all_primitives_allowlisted": all(step in PRIMITIVE_NAMES for step in steps),
        "canary_required": True,
    }


def resource_scheduler(base: dict[str, Any], cp: dict[str, Any], recipe: dict[str, Any], *,
                       execute: bool, apply_capabilities: bool, train_meta: bool, apply_skills: bool) -> dict[str, Any]:
    headroom = _dimensions(base).get("resource_headroom", 0.5)
    drift = base.get("v382_drift") if isinstance(base.get("v382_drift"), dict) else {}
    high_drift = str(drift.get("level") or "") == "HIGH"
    critical = headroom < RESOURCE_CRITICAL
    low = headroom < RESOURCE_LOW

    allowed = {
        "execute": bool(execute),
        "apply_capabilities": bool(apply_capabilities and not low and recipe.get("status") == "active"),
        "train_meta": bool(train_meta and not low and not high_drift),
        "apply_skills": bool(apply_skills and not low and not high_drift),
    }
    if critical:
        allowed["apply_capabilities"] = False
        allowed["train_meta"] = False
        allowed["apply_skills"] = False
    if cp.get("detected") is True:
        allowed["train_meta"] = False
    return {
        "resource_headroom": round(headroom, 6),
        "resource_state": "CRITICAL" if critical else ("LOW" if low else "NORMAL"),
        "requested": {
            "execute": bool(execute),
            "apply_capabilities": bool(apply_capabilities),
            "train_meta": bool(train_meta),
            "apply_skills": bool(apply_skills),
        },
        "allowed": allowed,
        "high_drift": high_drift,
        "change_point": bool(cp.get("detected")),
    }


def source_feature_plan(state: dict[str, Any], base: dict[str, Any]) -> list[dict[str, Any]]:
    counts = dict(state.get("gap_counts") or {})
    rows = base.get("v382_feature_contracts") if isinstance(base.get("v382_feature_contracts"), list) else []
    result = []
    for row in rows[:32]:
        if not isinstance(row, dict):
            continue
        contract_id = str(row.get("contract_id") or "")
        if not contract_id:
            continue
        count = min(9999, int(counts.get(contract_id) or 0) + 1)
        counts[contract_id] = count
        result.append({
            "proposal_id": "V385:" + _digest([contract_id, row.get("gap_kind")])[:20],
            "upstream_contract_id": contract_id[:190],
            "gap_kind": str(row.get("gap_kind") or "source_feature")[:80],
            "recurrence": count,
            "priority": "HIGH" if count >= 4 else ("MEDIUM" if count >= 2 else "LOW"),
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
        })
    result.sort(key=lambda row: ({"HIGH": 0, "MEDIUM": 1, "LOW": 2}[row["priority"]], -row["recurrence"], row["proposal_id"]))
    return result[:32]


def autonomous_gate(base: dict[str, Any], policy: dict[str, Any], cp: dict[str, Any], scheduler: dict[str, Any]) -> dict[str, Any]:
    upstream = base.get("v382_autonomous_gate") if isinstance(base.get("v382_autonomous_gate"), dict) else {}
    upstream_action = str(upstream.get("selected_action") or "")
    neural_action = str(policy.get("selected_action") or "")
    reasons: list[str] = []

    if upstream.get("allow_execution") is not True:
        reasons.append("V382_UPSTREAM_GATE_HOLD")
    if scheduler.get("resource_state") == "CRITICAL" and upstream_action not in RECOVERY_ACTIONS:
        reasons.append("RESOURCE_CRITICAL")
    if cp.get("detected") is True and upstream_action not in RECOVERY_ACTIONS:
        reasons.append("CHANGE_POINT_RECOVERY_ONLY")

    top = policy.get("candidates") if isinstance(policy.get("candidates"), list) else []
    neural_confident = bool(top and int(top[0].get("verified_samples") or 0) >= MIN_VERIFIED_SAMPLES * 2 and float(top[0].get("score") or 0.0) >= 0.62)
    if neural_confident and neural_action and upstream_action and neural_action != upstream_action and upstream_action not in RECOVERY_ACTIONS:
        reasons.append("VERIFIED_NEURAL_UPSTREAM_DISAGREEMENT")

    if not reasons:
        status = "ALLOW_BOUNDED"
    elif "V382_UPSTREAM_GATE_HOLD" in reasons:
        status = "V385_UPSTREAM_HOLD"
    elif "RESOURCE_CRITICAL" in reasons:
        status = "V385_RESOURCE_CRITICAL_HOLD"
    elif "CHANGE_POINT_RECOVERY_ONLY" in reasons:
        status = "V385_CHANGE_POINT_RECOVERY_ONLY"
    else:
        status = "V385_NEURAL_DISAGREEMENT_HOLD"

    return {
        "status": status,
        "allow_execution": not reasons,
        "reasons": reasons,
        "upstream_action": upstream_action or None,
        "neural_selected_action": neural_action or None,
        "hard_blocker_override": False,
        "market_direction_inferred": False,
    }


def _next_state(state: dict[str, Any], base: dict[str, Any], training: dict[str, Any], cp: dict[str, Any],
                recipe: dict[str, Any], feature_plan: list[dict[str, Any]], gate: dict[str, Any],
                *, now: datetime) -> dict[str, Any]:
    next_state = deepcopy(state)
    next_state["network"] = deepcopy(training["network"])
    next_state["regime_memory"] = regime_memory_update(next_state, base)

    registry = dict(next_state.get("capability_registry") or {})
    registry[recipe["recipe_id"]] = {
        "steps": list(recipe["steps"]),
        "status": recipe["status"],
        "observations": int(recipe["observations"]),
        "activation_kpi": recipe.get("activation_kpi"),
        "last_seen_at": now.isoformat(timespec="seconds"),
    }
    next_state["capability_registry"] = dict(list(registry.items())[-64:])

    counts = dict(next_state.get("gap_counts") or {})
    for row in feature_plan:
        upstream = str(row.get("upstream_contract_id") or "")
        if upstream:
            counts[upstream] = int(row.get("recurrence") or counts.get(upstream) or 0)
    next_state["gap_counts"] = dict(sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:128])

    kpi = base.get("v382_kpis") if isinstance(base.get("v382_kpis"), dict) else {}
    kpi_score = _finite(kpi.get("score"))
    next_state["last_kpi_score"] = kpi_score
    next_state["ewma_kpi"] = cp.get("ewma_kpi")
    next_state["ewma_drift"] = cp.get("ewma_drift")

    history = list(next_state.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "market_regime": _market_regime(base),
        "kpi_score": kpi_score,
        "change_point": bool(cp.get("detected")),
        "gate_status": gate.get("status"),
        "recipe_id": recipe.get("recipe_id"),
        "recipe_status": recipe.get("status"),
        "network_updates": int(training["network"].get("updates") or 0),
    })
    next_state["history"] = history[-MAX_HISTORY:]
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
            return None, {"status": "V385_LOCK_UNAVAILABLE", "error_code": "NOT_REGULAR_FILE"}
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd, {"status": "V385_LOCK_ACQUIRED", "error_code": None}
    except BlockingIOError:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return None, {"status": "V385_CONCURRENT_AUTONOMY_HOLD", "error_code": "LOCK_BUSY"}
    except OSError as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        return None, {"status": "V385_LOCK_UNAVAILABLE", "error_code": type(exc).__name__}


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
    v385_state_path: Path | None = None,
    v385_lock_path: Path | None = None,
    persist_outputs: bool = True,
    **upstream_paths: Any,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
    state_file = v385_state_path or (root / STATE_PATH.name)
    lock_info = {"status": "V385_LOCK_NOT_REQUIRED", "error_code": None}
    fd = None

    if mutating:
        fd, lock_info = _acquire_lock(v385_lock_path or (root / LOCK_PATH.name))
        if fd is None:
            return {
                "controller_version": CONTROLLER_VERSION,
                "core_controller_version": CORE_CONTROLLER_VERSION,
                "v385_status": lock_info["status"],
                "execution": {"status": lock_info["status"], "executed": False, "git_write": False, "source_code_modified": False},
                "v385_single_run_lock": lock_info,
                "safety": SAFETY,
            }

    try:
        upstream_kwargs = dict(upstream_paths)
        upstream_kwargs.update({"root": root, "now": moment, "persist_outputs": False})
        preview = v382.run_cycle(
            execute=False,
            apply_capabilities=False,
            train_meta=False,
            apply_skills=False,
            **upstream_kwargs,
        )

        loaded = load_state(state_file)
        cp = change_point(loaded["state"], preview)
        resource = _dimensions(preview).get("resource_headroom", 0.5)
        lr = BASE_LR * (0.5 if cp.get("detected") else 1.0) * (0.6 if resource < RESOURCE_LOW else 1.0)
        training = train_verified_network(loaded["state"]["network"], preview, learning_rate=lr)
        shadow_state = deepcopy(loaded["state"])
        shadow_state["regime_memory"] = regime_memory_update(shadow_state, preview)
        policy = neural_policy_scores(training["network"], shadow_state, preview)
        recipe = forge_capability(shadow_state, preview, cp)
        scheduler = resource_scheduler(
            preview,
            cp,
            recipe,
            execute=execute,
            apply_capabilities=apply_capabilities,
            train_meta=train_meta,
            apply_skills=apply_skills,
        )
        feature_plan = source_feature_plan(shadow_state, preview)

        if mutating and loaded.get("corruption_hold") is True:
            gate = {
                "status": "V385_STATE_CORRUPTION_HOLD",
                "allow_execution": False,
                "reasons": ["STATE_CORRUPTION_HOLD"],
                "upstream_action": None,
                "neural_selected_action": policy.get("selected_action"),
                "hard_blocker_override": False,
                "market_direction_inferred": False,
            }
        else:
            gate = autonomous_gate(preview, policy, cp, scheduler)

        base = preview
        if mutating and gate.get("allow_execution") is True:
            allowed = scheduler["allowed"]
            base = v382.run_cycle(
                execute=allowed["execute"],
                apply_capabilities=allowed["apply_capabilities"],
                train_meta=allowed["train_meta"],
                apply_skills=allowed["apply_skills"],
                **upstream_kwargs,
            )
            if str(base.get("v382_status") or "") in getattr(v382, "_HOLD_STATUSES", set()):
                gate = {
                    "status": "V385_UPSTREAM_HOLD",
                    "allow_execution": False,
                    "reasons": [str(base.get("v382_status") or "V382_HOLD")],
                    "upstream_action": (base.get("v382_autonomous_gate") or {}).get("selected_action") if isinstance(base.get("v382_autonomous_gate"), dict) else None,
                    "neural_selected_action": policy.get("selected_action"),
                    "hard_blocker_override": False,
                    "market_direction_inferred": False,
                }

        result = deepcopy(base)
        result.update({
            "core_controller_version": str(base.get("controller_version") or CORE_CONTROLLER_VERSION),
            "controller_version": CONTROLLER_VERSION,
            "v385_status": gate.get("status") if mutating else "PLAN_ONLY",
            "v385_verified_neural_policy": {
                **policy,
                "trained_this_cycle": bool(training.get("trained")),
                "training_examples": int(training.get("examples") or 0),
                "training_loss": training.get("loss"),
                "verified_outcomes_only": True,
                "weights_source": "device_local_v385_state",
            },
            "v385_change_point": cp,
            "v385_resource_scheduler": scheduler,
            "v385_capability_forge": recipe,
            "v385_source_feature_plan": feature_plan,
            "v385_autonomous_gate": gate,
            "v385_single_run_lock": lock_info,
            "evolution_contract_v385": {
                "neural_network": "14x8x1_online_mlp",
                "training_data": "verified_v381_outcome_aggregates_only",
                "market_adaptation": "operational_regime_conditioned_no_direction_prediction",
                "capability_self_extension": "allowlisted_declarative_primitives_shadow_canary_active",
                "source_level_new_functions": "non_executable_plan_requires_protected_pr_ci",
                "resource_scheduling": "bounded_optional_learning_budget",
                "change_point": "operational_kpi_and_drift_only",
                "v382_gate_bypass": False,
                "arbitrary_command_execution": False,
                "git_write": False,
                "source_code_auto_generation": False,
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

        state_write = {"status": "V385_STATE_WRITE_NOT_REQUESTED", "written": False}
        if mutating:
            next_state = _next_state(loaded["state"], base, training, cp, recipe, feature_plan, gate, now=moment)
            state_write = save_state(next_state, path=state_file, corruption_hold=bool(loaded.get("corruption_hold")))
            if not state_write.get("written") and gate.get("allow_execution") is True:
                result["v385_status"] = "V385_STATE_COMMIT_HOLD"
                result["execution"] = {
                    "status": "V385_STATE_COMMIT_HOLD",
                    "executed": False,
                    "git_write": False,
                    "source_code_modified": False,
                    "proposals_executed": False,
                }

            if state_write.get("written"):
                registry_payload = {
                    "schema_version": 1,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "recipes": next_state["capability_registry"],
                    "policy": {
                        "allowlisted_primitives_only": True,
                        "arbitrary_commands_forbidden": True,
                        "source_generation_forbidden": True,
                        "canary_before_activation": True,
                    },
                }
                try:
                    atomic_write_json(root / CAPABILITY_REGISTRY_PATH.name, registry_payload, suffix=".v385-capability.tmp")
                except (OSError, UnicodeError, ValueError, TypeError):
                    pass

                feature_payload = {
                    "schema_version": 1,
                    "controller_version": CONTROLLER_VERSION,
                    "generated_at": moment.isoformat(timespec="seconds"),
                    "contracts": feature_plan,
                    "auto_execute": False,
                    "source_generation": False,
                    "protected_pr_ci_required": True,
                }
                try:
                    atomic_write_json(root / FEATURE_CONTRACT_PATH.name, feature_payload, suffix=".v385-feature.tmp")
                except (OSError, UnicodeError, ValueError, TypeError):
                    pass

        result["v385_state_write"] = state_write

        if persist_outputs:
            try:
                atomic_write_json(root / REPORT_PATH.name, result, suffix=".v385-report.tmp")
                result["v385_runtime_output"] = {"status": "SAVED"}
            except (OSError, UnicodeError, ValueError, TypeError) as exc:
                result["v385_runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
        return result
    finally:
        if fd is not None:
            _release_lock(fd)


def self_test() -> None:
    network = _initial_network()
    assert _valid_network(network)
    assert len(feature_vector({"v382_kpis": {"score": 0.5, "dimensions": {}}, "v382_drift": {}, "v382_neural_calibration": {}}, "TEST")) == INPUT_DIM
    assert SAFETY["verified_online_neural_policy"] is True
    assert SAFETY["verified_outcomes_only_training"] is True
    assert SAFETY["capability_self_extension_declarative_only"] is True
    assert SAFETY["capability_primitives_allowlisted_only"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["arbitrary_command_execution"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["verification_bypass"] is False
    assert SAFETY["market_direction_inferred"] is False
    print("Tablet regime-aware neural autonomy v385: PASS")


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
    return 2 if result.get("v385_status") in _HOLD_STATUSES else 0


if __name__ == "__main__":
    raise SystemExit(main())
