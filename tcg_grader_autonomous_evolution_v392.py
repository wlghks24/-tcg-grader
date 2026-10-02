#!/usr/bin/env python3
"""TCG Grader V392 closed-loop neural capability evolution.

V392 sits above V391 and adds a TCG-specific neural policy that learns from
verified operational outcomes across cycles. The policy observes grading
calibration health, 1->4->8 vision integrity, SELFREFINE health, market
freshness/coverage, source health, neural consensus, resource headroom and
uncertainty/drift. It selects and composes only allowlisted runtime
capabilities, then measures the next cycle to learn whether the choice helped.

Runtime feature composition is autonomous. New source-level primitives are not
silently written into production: missing primitives become non-executable
feature contracts that require protected PR/CI, targeted tests, regression,
integrity and actual-output validation.

No market direction or card grade is invented. No peer weights/raw state are
imported. No arbitrary commands or direct Git/main writes are performed.
"""
from __future__ import annotations

import argparse
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tcg_grader_autonomous_evolution_v391 as v391
from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "tcg-grader-v392"
CORE_CONTROLLER_VERSION = "tcg-grader-v391"

STATE_PATH = ROOT / "tcg_grader_autonomy_v392_state.json"
REPORT_PATH = ROOT / "tcg_grader_autonomy_v392_report.json"
PLAN_PATH = ROOT / "tcg_grader_autonomy_v392_plan.json"

STATE_SCHEMA_VERSION = 1
MAX_STATE_BYTES = 1_500_000
MAX_HISTORY = 192
INPUT_DIM = 10
HIDDEN_DIM = 8
ACTIONS = (
    "REBUILD_VERIFIED_GRADE_CALIBRATION",
    "REFRESH_MARKET_EVIDENCE",
    "RETRY_DEGRADED_SOURCES",
    "PRIORITIZE_LOW_COVERAGE_REGION",
    "PRIORITIZE_REPAIR_LEARNING",
    "INCREASE_MARKET_OBSERVATION",
    "REVALIDATE_ONLY",
)
ACTION_INDEX = {action: i for i, action in enumerate(ACTIONS)}
LEARNING_RATE = 0.035
TRAIN_EPOCHS = 8
WEIGHT_BOUND = 4.0
MAX_SELECTED_ACTIONS = 3
MIN_AUTONOMOUS_UTILITY = 0.34
REWARD_SCALE = 4.0

SAFETY = dict(v391.SAFETY)
SAFETY.update({
    "tcg_specialist_closed_loop_neural_policy": True,
    "verified_next_cycle_reward_learning_only": True,
    "autonomous_runtime_feature_composition": True,
    "runtime_capability_allowlist_only": True,
    "runtime_capability_shadow_canary_rollback": True,
    "new_source_primitive_auto_activation": False,
    "new_source_primitive_protected_pr_ci_required": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "direct_main_write": False,
    "git_write": False,
    "arbitrary_command_execution": False,
    "verification_bypass": False,
    "market_direction_inferred": False,
    "price_or_grade_invention": False,
    "peer_model_weights_imported": False,
    "peer_raw_state_imported": False,
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


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _initial_model() -> dict[str, Any]:
    w1 = [
        [round(math.sin((i + 1) * (j + 2) * 0.77) * 0.04, 9) for j in range(HIDDEN_DIM)]
        for i in range(INPUT_DIM)
    ]
    w2 = [
        [
            round(math.cos((j + 2) * (k + 3) * 0.61) * 0.04, 9)
            for k in range(len(ACTIONS))
        ]
        for j in range(HIDDEN_DIM)
    ]
    return {
        "input_dim": INPUT_DIM,
        "hidden_dim": HIDDEN_DIM,
        "output_dim": len(ACTIONS),
        "sample_count": 0,
        "w1": w1,
        "b1": [0.0] * HIDDEN_DIM,
        "w2": w2,
        "b2": [0.0] * len(ACTIONS),
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": 0,
        "model": _initial_model(),
        "last_decision": None,
        "action_stats": {
            action: {"observations": 0, "reward_ewma": 0.0, "last_reward": 0.0}
            for action in ACTIONS
        },
        "history": [],
    }


def _valid_number(value: Any, low: float, high: float) -> bool:
    number = _finite(value)
    return number is not None and low <= number <= high


def _valid_model(model: Any) -> bool:
    if not isinstance(model, dict):
        return False
    if model.get("input_dim") != INPUT_DIM or model.get("hidden_dim") != HIDDEN_DIM:
        return False
    if model.get("output_dim") != len(ACTIONS):
        return False
    if not isinstance(model.get("sample_count"), int) or not 0 <= model["sample_count"] <= 10_000_000:
        return False
    w1, b1, w2, b2 = model.get("w1"), model.get("b1"), model.get("w2"), model.get("b2")
    if not isinstance(w1, list) or len(w1) != INPUT_DIM:
        return False
    if not all(
        isinstance(row, list)
        and len(row) == HIDDEN_DIM
        and all(_valid_number(x, -WEIGHT_BOUND, WEIGHT_BOUND) for x in row)
        for row in w1
    ):
        return False
    if not isinstance(b1, list) or len(b1) != HIDDEN_DIM:
        return False
    if not all(_valid_number(x, -WEIGHT_BOUND, WEIGHT_BOUND) for x in b1):
        return False
    if not isinstance(w2, list) or len(w2) != HIDDEN_DIM:
        return False
    if not all(
        isinstance(row, list)
        and len(row) == len(ACTIONS)
        and all(_valid_number(x, -WEIGHT_BOUND, WEIGHT_BOUND) for x in row)
        for row in w2
    ):
        return False
    return (
        isinstance(b2, list)
        and len(b2) == len(ACTIONS)
        and all(_valid_number(x, -WEIGHT_BOUND, WEIGHT_BOUND) for x in b2)
    )


def _valid_decision(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    features = value.get("features")
    actions = value.get("selected_actions")
    return (
        isinstance(features, list)
        and len(features) == INPUT_DIM
        and all(_valid_number(x, 0.0, 1.0) for x in features)
        and isinstance(actions, list)
        and 1 <= len(actions) <= MAX_SELECTED_ACTIONS
        and all(action in ACTION_INDEX for action in actions)
        and _valid_number(value.get("baseline_quality"), 0.0, 1.0)
    )


def _valid_state(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required = {
        "schema_version", "controller_version", "cycle", "model",
        "last_decision", "action_stats", "history",
    }
    if set(value) != required:
        return False
    if value["schema_version"] != STATE_SCHEMA_VERSION or value["controller_version"] != CONTROLLER_VERSION:
        return False
    if not isinstance(value["cycle"], int) or not 0 <= value["cycle"] <= 10_000_000:
        return False
    if not _valid_model(value["model"]) or not _valid_decision(value["last_decision"]):
        return False
    stats = value["action_stats"]
    if not isinstance(stats, dict) or set(stats) != set(ACTIONS):
        return False
    for row in stats.values():
        if not isinstance(row, dict) or set(row) != {"observations", "reward_ewma", "last_reward"}:
            return False
        if not isinstance(row["observations"], int) or not 0 <= row["observations"] <= 10_000_000:
            return False
        if not _valid_number(row["reward_ewma"], -1.0, 1.0):
            return False
        if not _valid_number(row["last_reward"], -1.0, 1.0):
            return False
    return isinstance(value["history"], list) and len(value["history"]) <= MAX_HISTORY


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"state": _default_state(), "status": "fresh", "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("unsafe_state_path")
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
            "error_code": "V392_STATE_SCHEMA_INVALID",
        }
    return {"state": value, "status": "loaded", "corruption_hold": False}


def save_state(state: dict[str, Any], path: Path, *, corruption_hold: bool) -> dict[str, Any]:
    if corruption_hold:
        return {"status": "V392_STATE_CORRUPTION_HOLD", "written": False}
    if not _valid_state(state):
        return {"status": "V392_STATE_INVALID", "written": False}
    try:
        atomic_write_json(path, state, suffix=".v392-state.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "V392_STATE_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "V392_STATE_SAVED", "written": True}


def _core_dimensions(core: dict[str, Any]) -> dict[str, float]:
    kpis = core.get("v382_kpis")
    kpis = kpis if isinstance(kpis, dict) else {}
    dims = kpis.get("dimensions")
    dims = dims if isinstance(dims, dict) else {}
    result: dict[str, float] = {}
    for key in (
        "market_freshness", "market_coverage", "source_health",
        "neural_consensus", "resource_headroom",
    ):
        value = _finite(dims.get(key))
        if value is not None:
            result[key] = _clamp(value)
    return result


def observation(core: dict[str, Any]) -> dict[str, Any]:
    v391_payload = core.get("tcg_grader_autonomy_v391")
    v391_payload = v391_payload if isinstance(v391_payload, dict) else {}
    snap = v391_payload.get("snapshot_after")
    snap = snap if isinstance(snap, dict) else v391_payload.get("snapshot_before")
    snap = snap if isinstance(snap, dict) else {}

    grade = snap.get("verified_grade_learning")
    grade = grade if isinstance(grade, dict) else {}
    vision = snap.get("vision_1_4_8")
    vision = vision if isinstance(vision, dict) else {}
    selfrefine = snap.get("selfrefine")
    selfrefine = selfrefine if isinstance(selfrefine, dict) else {}
    market = snap.get("market")
    market = market if isinstance(market, dict) else {}
    dims = _core_dimensions(core)

    verified_rows = max(0, int(grade.get("verified_training_rows") or 0))
    profile_count = max(0, int(grade.get("vision_profile_count") or 0))
    open_errors = max(0, int(selfrefine.get("open_error_count") or 0))
    age = _finite(market.get("market_prices_age_hours"))
    stale_after = max(1.0, float(_finite(market.get("stale_after_hours")) or 6.0))

    budget = core.get("v388_resource_budget")
    budget = budget if isinstance(budget, dict) else {}
    uncertainty = _clamp(float(_finite(budget.get("selected_uncertainty")) or 0.5))
    drift = _clamp(float(_finite(budget.get("drift_score")) or 0.5))

    features = [
        1.0 if grade.get("audit_ok") is True else 0.0,
        _clamp(math.log1p(verified_rows) / math.log(501.0)),
        _clamp(profile_count / 6.0),
        1.0 if vision.get("one_four_eight_contract_present") is True else 0.0,
        _clamp(1.0 - open_errors / 12.0),
        _clamp(1.0 - ((age if age is not None else stale_after * 2.0) / (stale_after * 2.0))),
        dims.get("source_health", 0.5),
        dims.get("neural_consensus", 0.5),
        dims.get("resource_headroom", 0.5),
        _clamp(1.0 - max(uncertainty, drift)),
    ]

    market_adaptation = core.get("market_adaptation_v381")
    market_adaptation = market_adaptation if isinstance(market_adaptation, dict) else {}
    low_regions = [
        str(region) for region in list(market_adaptation.get("low_coverage_regions") or [])
        if str(region) in {"KR", "JP", "US"}
    ]
    degraded = _finite(market_adaptation.get("degraded_source_ratio"))
    degraded_ratio = _clamp(degraded if degraded is not None else 0.0)

    return {
        "features": [round(_clamp(x), 6) for x in features],
        "verified_grade_rows": verified_rows,
        "vision_profile_count": profile_count,
        "grade_audit_ok": grade.get("audit_ok") is True,
        "vision_1_4_8_ok": vision.get("one_four_eight_contract_present") is True,
        "open_selfrefine_errors": open_errors,
        "market_age_hours": round(age, 4) if age is not None else None,
        "market_stale_after_hours": stale_after,
        "low_coverage_regions": low_regions,
        "degraded_source_ratio": round(degraded_ratio, 6),
        "dimensions": dims,
        "uncertainty": round(uncertainty, 6),
        "drift": round(drift, 6),
    }


def quality_score(obs: dict[str, Any]) -> float:
    features = obs.get("features") if isinstance(obs.get("features"), list) else [0.0] * INPUT_DIM
    weights = (0.15, 0.08, 0.08, 0.14, 0.12, 0.12, 0.10, 0.09, 0.05, 0.07)
    return round(_clamp(sum(float(x) * w for x, w in zip(features, weights))), 6)


def _forward(model: dict[str, Any], features: list[float]) -> tuple[list[float], list[float]]:
    hidden: list[float] = []
    for j in range(HIDDEN_DIM):
        total = float(model["b1"][j])
        for i, value in enumerate(features):
            total += float(value) * float(model["w1"][i][j])
        hidden.append(math.tanh(total))
    outputs: list[float] = []
    for k in range(len(ACTIONS)):
        total = float(model["b2"][k])
        for j, value in enumerate(hidden):
            total += value * float(model["w2"][j][k])
        outputs.append(_sigmoid(total))
    return hidden, outputs


def train_from_previous(
    model: dict[str, Any],
    last_decision: dict[str, Any] | None,
    current_quality: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(last_decision, dict):
        return deepcopy(model), {"status": "NO_PREVIOUS_DECISION", "trained": False}
    features = [float(x) for x in last_decision.get("features") or []]
    selected = [str(x) for x in last_decision.get("selected_actions") or []]
    baseline = _finite(last_decision.get("baseline_quality"))
    if len(features) != INPUT_DIM or not selected or baseline is None:
        return deepcopy(model), {"status": "PREVIOUS_DECISION_INVALID", "trained": False}

    reward = max(-1.0, min(1.0, (current_quality - baseline) * REWARD_SCALE))
    label = _clamp((reward + 1.0) / 2.0)
    trained = deepcopy(model)

    for _ in range(TRAIN_EPOCHS):
        hidden, outputs = _forward(trained, features)
        for action in selected:
            if action not in ACTION_INDEX:
                continue
            k = ACTION_INDEX[action]
            pred = outputs[k]
            delta2 = (pred - label) * pred * (1.0 - pred)
            old_w2 = [float(trained["w2"][j][k]) for j in range(HIDDEN_DIM)]
            for j in range(HIDDEN_DIM):
                updated = float(trained["w2"][j][k]) - LEARNING_RATE * delta2 * hidden[j]
                trained["w2"][j][k] = round(max(-WEIGHT_BOUND, min(WEIGHT_BOUND, updated)), 9)
            b2 = float(trained["b2"][k]) - LEARNING_RATE * delta2
            trained["b2"][k] = round(max(-WEIGHT_BOUND, min(WEIGHT_BOUND, b2)), 9)

            for j in range(HIDDEN_DIM):
                delta1 = delta2 * old_w2[j] * (1.0 - hidden[j] * hidden[j])
                for i, value in enumerate(features):
                    updated = float(trained["w1"][i][j]) - LEARNING_RATE * delta1 * value
                    trained["w1"][i][j] = round(
                        max(-WEIGHT_BOUND, min(WEIGHT_BOUND, updated)), 9
                    )
                b1 = float(trained["b1"][j]) - LEARNING_RATE * delta1
                trained["b1"][j] = round(max(-WEIGHT_BOUND, min(WEIGHT_BOUND, b1)), 9)

    trained["sample_count"] = min(10_000_000, int(model.get("sample_count") or 0) + 1)
    return trained, {
        "status": "TRAINED_VERIFIED_NEXT_CYCLE_REWARD",
        "trained": True,
        "reward": round(reward, 6),
        "label": round(label, 6),
        "actions": selected,
        "baseline_quality": round(baseline, 6),
        "current_quality": round(current_quality, 6),
    }


def heuristic_urgency(obs: dict[str, Any]) -> dict[str, float]:
    rows = int(obs.get("verified_grade_rows") or 0)
    profiles = int(obs.get("vision_profile_count") or 0)
    audit_ok = obs.get("grade_audit_ok") is True
    vision_ok = obs.get("vision_1_4_8_ok") is True
    age = _finite(obs.get("market_age_hours"))
    stale_after = max(1.0, float(_finite(obs.get("market_stale_after_hours")) or 6.0))
    degraded = _clamp(float(_finite(obs.get("degraded_source_ratio")) or 0.0))
    open_errors = max(0, int(obs.get("open_selfrefine_errors") or 0))
    dims = obs.get("dimensions") if isinstance(obs.get("dimensions"), dict) else {}
    uncertainty = _clamp(float(_finite(obs.get("uncertainty")) or 0.5))
    drift = _clamp(float(_finite(obs.get("drift")) or 0.5))

    calibration = 0.0
    if audit_ok and rows > 0 and profiles == 0:
        calibration = 1.0
    elif audit_ok and rows > 0:
        calibration = 0.18

    refresh = 0.9 if age is None else _clamp(age / (stale_after * 1.5))
    repair = max(
        _clamp(open_errors / 10.0),
        _clamp(1.0 - float(_finite(dims.get("neural_consensus")) or 0.5)),
    )
    coverage = _clamp(1.0 - float(_finite(dims.get("market_coverage")) or 0.5))
    if obs.get("low_coverage_regions"):
        coverage = max(coverage, 0.72)
    observation = max(uncertainty, drift)
    revalidate = 0.20
    if not audit_ok or not vision_ok:
        revalidate = 1.0

    return {
        "REBUILD_VERIFIED_GRADE_CALIBRATION": round(calibration, 6),
        "REFRESH_MARKET_EVIDENCE": round(refresh, 6),
        "RETRY_DEGRADED_SOURCES": round(degraded, 6),
        "PRIORITIZE_LOW_COVERAGE_REGION": round(coverage, 6),
        "PRIORITIZE_REPAIR_LEARNING": round(repair, 6),
        "INCREASE_MARKET_OBSERVATION": round(observation, 6),
        "REVALIDATE_ONLY": round(revalidate, 6),
    }


def select_actions(
    model: dict[str, Any],
    obs: dict[str, Any],
    *,
    action_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    features = [float(x) for x in obs["features"]]
    _, predictions = _forward(model, features)
    urgency = heuristic_urgency(obs)
    stats = action_stats if isinstance(action_stats, dict) else {}

    ranked = []
    for action in ACTIONS:
        pred = _clamp(predictions[ACTION_INDEX[action]])
        prior = stats.get(action) if isinstance(stats.get(action), dict) else {}
        reward_ewma = float(_finite(prior.get("reward_ewma")) or 0.0)
        reward_component = _clamp((reward_ewma + 1.0) / 2.0)
        utility = 0.50 * urgency[action] + 0.35 * pred + 0.15 * reward_component
        ranked.append({
            "action_id": action,
            "heuristic_urgency": urgency[action],
            "neural_score": round(pred, 6),
            "verified_reward_prior": round(reward_ewma, 6),
            "utility": round(_clamp(utility), 6),
        })
    ranked.sort(key=lambda row: (-float(row["utility"]), row["action_id"]))

    blockers = not bool(obs.get("grade_audit_ok")) or not bool(obs.get("vision_1_4_8_ok"))
    if blockers:
        selected = ["REVALIDATE_ONLY"]
    else:
        selected = [
            row["action_id"] for row in ranked
            if float(row["utility"]) >= MIN_AUTONOMOUS_UTILITY
            and row["action_id"] != "REVALIDATE_ONLY"
        ][:MAX_SELECTED_ACTIONS]
        if not selected:
            selected = [ranked[0]["action_id"] if ranked else "REVALIDATE_ONLY"]

    return {
        "selected_actions": selected,
        "ranked_actions": ranked,
        "model_sample_count": int(model.get("sample_count") or 0),
        "blockers_present": blockers,
        "selection_mode": "verified_neural_plus_operational_urgency",
        "market_direction_inferred": False,
    }


def _capability_rows(
    plan: dict[str, Any],
    obs: dict[str, Any],
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    v373 = v391.v390.v373
    rows: list[dict[str, Any]] = []
    selected = set(plan.get("selected_actions") or [])
    evidence = {
        "reason": "tcg_grader_v392_neural_capability_composition",
        "controller": CONTROLLER_VERSION,
    }

    if "REFRESH_MARKET_EVIDENCE" in selected:
        rows.append(v373._capability(
            "REQUEST_FRESHNESS_REFRESH", "TCG_V392", {"max_runs": 1}, evidence, now=now
        ))
    if "RETRY_DEGRADED_SOURCES" in selected:
        rows.append(v373._capability(
            "RETRY_DEGRADED_SOURCES", "TCG_V392",
            {"max_retry": 2, "backoff_seconds": 120}, evidence, now=now
        ))
    if "PRIORITIZE_LOW_COVERAGE_REGION" in selected:
        regions = list(obs.get("low_coverage_regions") or [])
        if regions:
            rows.append(v373._capability(
                "PRIORITIZE_REGION", f"TCG_V392_{regions[0]}",
                {"region": regions[0], "boost": 0.12}, evidence, now=now
            ))
    if "PRIORITIZE_REPAIR_LEARNING" in selected:
        rows.append(v373._capability(
            "PRIORITIZE_SAFE_LEARNING", "TCG_V392_REPAIR",
            {"action_id": "TRAIN_REPAIR_PRIORITY", "boost": 0.10}, evidence, now=now
        ))
    if "INCREASE_MARKET_OBSERVATION" in selected:
        rows.append(v373._capability(
            "INCREASE_OBSERVATION", "TCG_V392_MARKET",
            {"scope": "market_health", "factor": 1.25}, evidence, now=now
        ))
    return [row for row in rows if v373.validate_capability(row, now=now)]


def persist_composed_capabilities(
    rows: list[dict[str, Any]],
    *,
    root: Path,
    now: datetime,
) -> dict[str, Any]:
    if not rows:
        return {"status": "NO_RUNTIME_CAPABILITIES", "written": False, "count": 0}
    v373 = v391.v390.v373
    try:
        with v391.isolated_tcg_runtime_paths():
            path = root / v373.CAPABILITY_PATH.name
            loaded = v373.load_capabilities(path=path, now=now)
            if loaded.get("corruption_hold") is True:
                return {"status": "CAPABILITY_CORRUPTION_HOLD", "written": False, "count": 0}
            merged = v373.merge_capabilities(
                list(loaded.get("capabilities") or []), rows, now=now
            )
            result = v373.save_capabilities(
                merged, path=path, corruption_hold=False, now=now
            )
            return {
                "status": result.get("status"),
                "written": result.get("written") is True,
                "count": len(rows),
                "active_count": len(merged),
            }
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "CAPABILITY_COMPOSITION_WRITE_FAILED",
            "written": False,
            "count": 0,
            "error_code": type(exc).__name__,
        }


def execute_specialist_action(
    plan: dict[str, Any],
    obs: dict[str, Any],
    core: dict[str, Any],
    *,
    execute: bool,
) -> dict[str, Any]:
    selected = set(plan.get("selected_actions") or [])
    if not execute or "REBUILD_VERIFIED_GRADE_CALIBRATION" not in selected:
        return {"status": "SPECIALIST_DIRECT_ACTION_NOT_SELECTED", "executed": False}
    if obs.get("grade_audit_ok") is not True or int(obs.get("verified_grade_rows") or 0) <= 0:
        return {"status": "GRADE_CALIBRATION_VERIFICATION_HOLD", "executed": False}

    v391_payload = core.get("tcg_grader_autonomy_v391")
    v391_payload = v391_payload if isinstance(v391_payload, dict) else {}
    existing = v391_payload.get("grade_calibration_action")
    existing = existing if isinstance(existing, dict) else {}
    if existing.get("executed") is True:
        return {
            "status": "GRADE_CALIBRATION_ALREADY_REBUILT_BY_V391",
            "executed": True,
            "registry_verified_training_rows": existing.get("registry_verified_training_rows"),
        }

    gate = core.get("v390_autonomous_gate")
    gate = gate if isinstance(gate, dict) else {}
    if gate.get("allow_execution") is not True:
        return {"status": "GRADE_CALIBRATION_UPSTREAM_HOLD", "executed": False}
    try:
        result = v391.grade_learning.rebuild_safe_vision_calibration()
    except Exception as exc:
        return {
            "status": "GRADE_CALIBRATION_REBUILD_FAILED",
            "executed": False,
            "error_code": type(exc).__name__,
        }
    return {
        "status": "GRADE_CALIBRATION_REBUILT_VERIFIED_ONLY",
        "executed": True,
        "registry_verified_training_rows": int(result.get("registry_verified_training_rows") or 0),
        "registry_gate_v135": result.get("registry_gate_v135") is True,
    }


def source_feature_contracts(obs: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if obs.get("grade_audit_ok") is not True:
        rows.append({
            "feature_id": "TCG_V392_GRADE_AUDIT_RECOVERY_ADAPTER",
            "reason": "verified grade audit unavailable or failed",
        })
    if obs.get("vision_1_4_8_ok") is not True:
        rows.append({
            "feature_id": "TCG_V392_VISION_HIERARCHY_RECOVERY_ADAPTER",
            "reason": "1->4->8 vision contract missing or invalid",
        })
    if float(_finite(obs.get("degraded_source_ratio")) or 0.0) >= 0.50:
        rows.append({
            "feature_id": "TCG_V392_SOURCE_ADAPTER_RESILIENCE_EXTENSION",
            "reason": "degraded market source ratio remains high",
        })
    if int(plan.get("model_sample_count") or 0) < 6:
        rows.append({
            "feature_id": "TCG_V392_VERIFIED_POLICY_FEEDBACK_EXPANSION",
            "reason": "TCG specialist neural policy needs more verified next-cycle outcomes",
        })

    result = []
    for row in rows:
        result.append({
            **row,
            "stage": "shadow_spec",
            "auto_execute": False,
            "source_code_generated": False,
            "git_write": False,
            "protected_pr_ci_required": True,
            "promotion_requires": [
                "targeted_tests",
                "grading_regression",
                "market_collection_regression",
                "full_current_runtime",
                "repository_integrity",
                "actual_output_validation",
            ],
            "rollback_rule": "restore prior verified behavior on KPI regression or verification failure",
        })
    return result


def _next_state(
    state: dict[str, Any],
    model: dict[str, Any],
    training: dict[str, Any],
    plan: dict[str, Any],
    obs: dict[str, Any],
    current_quality: float,
    *,
    now: datetime,
) -> dict[str, Any]:
    nxt = deepcopy(state)
    cycle = min(10_000_000, int(state.get("cycle") or 0) + 1)
    stats = deepcopy(state["action_stats"])

    if training.get("trained") is True:
        reward = max(-1.0, min(1.0, float(_finite(training.get("reward")) or 0.0)))
        for action in training.get("actions") or []:
            if action not in stats:
                continue
            row = stats[action]
            count = int(row.get("observations") or 0) + 1
            prior = float(_finite(row.get("reward_ewma")) or 0.0)
            ewma = reward if count == 1 else 0.25 * reward + 0.75 * prior
            row.update({
                "observations": min(10_000_000, count),
                "reward_ewma": round(max(-1.0, min(1.0, ewma)), 6),
                "last_reward": round(reward, 6),
            })

    selected = [str(x) for x in plan.get("selected_actions") or [] if str(x) in ACTION_INDEX]
    last_decision = {
        "observed_at": now.isoformat(timespec="seconds"),
        "features": [round(float(x), 6) for x in obs["features"]],
        "selected_actions": selected[:MAX_SELECTED_ACTIONS],
        "baseline_quality": round(current_quality, 6),
    }

    history = list(state.get("history") or [])
    history.append({
        "observed_at": now.isoformat(timespec="seconds"),
        "cycle": cycle,
        "quality": round(current_quality, 6),
        "selected_actions": selected[:MAX_SELECTED_ACTIONS],
        "trained": training.get("trained") is True,
        "reward": training.get("reward"),
    })

    nxt.update({
        "schema_version": STATE_SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "cycle": cycle,
        "model": model,
        "last_decision": last_decision,
        "action_stats": stats,
        "history": history[-MAX_HISTORY:],
    })
    return nxt


def run_cycle(
    *,
    execute: bool = False,
    apply_capabilities: bool = False,
    train_meta: bool = False,
    apply_skills: bool = False,
    root: Path = ROOT,
    now: datetime | None = None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    state_file = root / STATE_PATH.name

    try:
        with exclusive_file_lock(state_file, timeout_seconds=2.0, stale_seconds=1800.0):
            loaded = load_state(state_file)

            preview = v391.run_cycle(
                execute=False,
                apply_capabilities=False,
                train_meta=False,
                apply_skills=False,
                root=root,
                now=moment,
                persist_outputs=False,
            )
            preview_obs = observation(preview)
            current_quality = quality_score(preview_obs)
            model, training = train_from_previous(
                loaded["state"]["model"],
                loaded["state"]["last_decision"],
                current_quality,
            )
            plan = select_actions(
                model,
                preview_obs,
                action_stats=loaded["state"]["action_stats"],
            )

            mutating = bool(execute or apply_capabilities or train_meta or apply_skills)
            core = preview
            if mutating and not plan.get("blockers_present"):
                core = v391.run_cycle(
                    execute=execute,
                    apply_capabilities=apply_capabilities,
                    train_meta=train_meta,
                    apply_skills=apply_skills,
                    root=root,
                    now=moment,
                    persist_outputs=False,
                )

            capability_rows = _capability_rows(plan, preview_obs, now=moment)
            capability_write = {"status": "CAPABILITY_APPLY_NOT_REQUESTED", "written": False, "count": 0}
            if apply_capabilities and not plan.get("blockers_present"):
                capability_write = persist_composed_capabilities(
                    capability_rows, root=root, now=moment
                )

            direct_action = execute_specialist_action(
                plan, preview_obs, core, execute=execute and not plan.get("blockers_present")
            )
            contracts = source_feature_contracts(preview_obs, plan)

            state_write = {"status": "V392_STATE_WRITE_NOT_REQUESTED", "written": False}
            if mutating:
                nxt = _next_state(
                    loaded["state"],
                    model,
                    training,
                    plan,
                    preview_obs,
                    current_quality,
                    now=moment,
                )
                state_write = save_state(
                    nxt, state_file, corruption_hold=bool(loaded.get("corruption_hold"))
                )

            result = deepcopy(core)
            result.update({
                "core_controller_version": str(core.get("controller_version") or CORE_CONTROLLER_VERSION),
                "controller_version": CONTROLLER_VERSION,
                "tcg_grader_autonomy_v392": {
                    "observation": preview_obs,
                    "quality_score": current_quality,
                    "neural_training": training,
                    "neural_plan": plan,
                    "composed_runtime_capabilities": {
                        "candidate_count": len(capability_rows),
                        "candidates": capability_rows,
                        "write": capability_write,
                    },
                    "specialist_direct_action": direct_action,
                    "source_feature_contracts": contracts,
                    "closed_loop": "observe->learn_previous_reward->rank->compose->execute->measure_next_cycle",
                    "market_adaptation": "freshness_coverage_source_health_regime_only_no_direction_prediction",
                },
                "v392_state_write": state_write,
                "safety": SAFETY,
            })

            if persist_outputs:
                try:
                    atomic_write_json(
                        root / PLAN_PATH.name,
                        {
                            "schema_version": 1,
                            "controller_version": CONTROLLER_VERSION,
                            "generated_at": moment.isoformat(timespec="seconds"),
                            "quality_score": current_quality,
                            "neural_plan": plan,
                            "runtime_capabilities": capability_rows,
                            "source_feature_contracts": contracts,
                            "source_code_auto_generation": False,
                            "protected_pr_ci_required_for_new_primitives": True,
                        },
                        suffix=".v392-plan.tmp",
                    )
                    atomic_write_json(
                        root / REPORT_PATH.name, result, suffix=".v392-report.tmp"
                    )
                    result["tcg_grader_v392_runtime_output"] = {"status": "SAVED"}
                except (OSError, UnicodeError, ValueError, TypeError) as exc:
                    result["tcg_grader_v392_runtime_output"] = {
                        "status": "WRITE_FAILED",
                        "error_code": type(exc).__name__,
                    }
            return result
    except TimeoutError:
        return {
            "controller_version": CONTROLLER_VERSION,
            "v392_status": "V392_CONCURRENT_AUTONOMY_HOLD",
            "execution": {
                "status": "V392_CONCURRENT_AUTONOMY_HOLD",
                "executed": False,
                "git_write": False,
                "source_code_modified": False,
            },
            "safety": SAFETY,
        }


def self_test() -> None:
    state = _default_state()
    assert _valid_state(state)
    assert tuple(ACTION_INDEX) == ACTIONS
    _, outputs = _forward(state["model"], [0.5] * INPUT_DIM)
    assert len(outputs) == len(ACTIONS)
    assert all(0.0 <= score <= 1.0 for score in outputs)
    assert SAFETY["tcg_specialist_closed_loop_neural_policy"] is True
    assert SAFETY["autonomous_runtime_feature_composition"] is True
    assert SAFETY["new_source_primitive_auto_activation"] is False
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["price_or_grade_invention"] is False
    print("TCG Grader closed-loop neural capability evolution v392: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description="TCG Grader V392 closed-loop neural autonomy")
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
        payload = result.get("tcg_grader_autonomy_v392")
        payload = payload if isinstance(payload, dict) else {}
        plan = payload.get("neural_plan")
        plan = plan if isinstance(plan, dict) else {}
        print(json.dumps({
            "controller_version": result.get("controller_version"),
            "quality_score": payload.get("quality_score"),
            "selected_actions": plan.get("selected_actions"),
            "neural_sample_count": plan.get("model_sample_count"),
            "runtime_capabilities": (
                payload.get("composed_runtime_capabilities") or {}
            ).get("write"),
            "specialist_direct_action": payload.get("specialist_direct_action"),
        }, ensure_ascii=False, sort_keys=True))

    if result.get("v392_status") == "V392_CONCURRENT_AUTONOMY_HOLD":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
