#!/usr/bin/env python3
"""Verified-outcome meta-neural autonomy for Tablet GPT / TCG Grader.

V373 extends v372 with:
- a small local neural meta-policy trained only from verified outcome records;
- bounded adaptive ranking of already-allowlisted learning actions;
- a declarative capability DSL that can create/activate new operational policies
  without generating or rewriting Python/source code;
- market-state adaptation based on freshness, regional coverage and source health;
- fail-closed local state/model/capability validation.

The controller never invents card facts/prices, never promotes trust/verification,
never executes arbitrary commands, and never writes Git/main. Source-code changes
remain normal branch/PR/CI work. Runtime "self-added functions" are limited to the
validated declarative primitives below.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import tablet_autonomous_evolution_v372 as v372
from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
CONTROLLER_VERSION = "v373"
SCHEMA_VERSION = 3

CAPABILITY_PATH = ROOT / "tablet_autonomy_capabilities.json"
META_MODEL_PATH = ROOT / "tablet_autonomy_meta_neural.json"
OUTCOMES_PATH = ROOT / "tablet_autonomy_verified_outcomes.jsonl"
REPORT_PATH = ROOT / "tablet_autonomy_v373_report.json"

MAX_CAPABILITIES = 64
CAPABILITY_TTL_SECONDS = 24 * 60 * 60
MAX_CAPABILITY_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_META_OUTCOMES = 2_000
MAX_OUTCOME_BYTES = 4_000_000
MIN_META_OUTCOMES = 8
META_INPUT_DIM = 10
META_HIDDEN_DIM = 8
META_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
META_LEARNING_RATE = 0.035
META_EPOCHS = 18
MAX_NEURAL_PRIORITY_DELTA = 12
MAX_OPERATIONAL_BOOST = 0.15

META_ACTIONS = (
    "TRAIN_QUERY_STRATEGY",
    "TRAIN_JOB_STRATEGY",
    "TRAIN_REPAIR_PRIORITY",
    "REFRESH_MARKET_DATA",
    "EXPAND_MARKET_COVERAGE",
    "RECHECK_DEGRADED_SOURCES",
)

CAPABILITY_PRIMITIVES = {
    "PRIORITIZE_REGION": {
        "required": {"region", "boost"},
        "regions": {"KR", "JP", "US"},
    },
    "RETRY_DEGRADED_SOURCES": {
        "required": {"max_retry", "backoff_seconds"},
    },
    "REQUEST_FRESHNESS_REFRESH": {
        "required": {"max_runs"},
    },
    "PRIORITIZE_SAFE_LEARNING": {
        "required": {"action_id", "boost"},
        "actions": set(v372.SAFE_LEARNING_ACTIONS),
    },
    "INCREASE_OBSERVATION": {
        "required": {"scope", "factor"},
        "scopes": {"market_health", "runtime_models", "sync_health"},
    },
}

SAFETY = dict(v372.SAFETY)
SAFETY.update({
    "meta_neural_verified_outcomes_only": True,
    "meta_neural_advisory_only": True,
    "declarative_capability_auto_generation": True,
    "declarative_capability_auto_activation": True,
    "declarative_capability_allowlisted_primitives_only": True,
    "declarative_capability_source_code_generation": False,
    "declarative_capability_arbitrary_command_execution": False,
    "adaptive_priority_delta_bounded": True,
    "operational_boost_bounded": True,
    "market_direction_inferred": False,
    "market_operational_regime_adaptation": True,
    "source_code_auto_generation": False,
    "source_code_auto_rewrite": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "trust_or_fact_auto_promotion": False,
})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    return v372._parse_time(value)


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
        raw = safe_read_text(path, max_bytes=max_bytes)
        value = json.loads(raw)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _resource_normal(plan: dict[str, Any]) -> bool:
    return isinstance(plan.get("resources"), dict) and plan["resources"].get("status") == "normal"


def feature_vector(plan: dict[str, Any]) -> list[float]:
    """Return a bounded feature vector derived only from current operational evidence."""
    signals = plan.get("signals") if isinstance(plan.get("signals"), dict) else {}
    runtime = signals.get("runtime_models") if isinstance(signals.get("runtime_models"), dict) else {}
    models = runtime.get("models") if isinstance(runtime.get("models"), dict) else {}
    repair = signals.get("repair_neural") if isinstance(signals.get("repair_neural"), dict) else {}
    market = plan.get("market_profile") if isinstance(plan.get("market_profile"), dict) else {}

    def broken(name: str) -> float:
        row = models.get(name) if isinstance(models.get(name), dict) else {}
        return 1.0 if str(row.get("status") or "") in {"broken", "degraded"} else 0.0

    low_regions = market.get("low_coverage_regions")
    low_ratio = len(low_regions) / 3.0 if isinstance(low_regions, list) else 1.0
    degraded = _finite(market.get("degraded_source_ratio"))
    degraded_ratio = _clamp(degraded if degraded is not None else 1.0, 0.0, 1.0)
    total = int(market.get("entry_count") or 0) if not isinstance(market.get("entry_count"), bool) else 0
    old = int(market.get("source_date_older_than_30d_count") or 0) if not isinstance(
        market.get("source_date_older_than_30d_count"), bool
    ) else 0
    old_ratio = _clamp(old / max(1, total), 0.0, 1.0)

    return [
        1.0 if runtime.get("status") == "broken" else 0.0,
        broken("query_strategy"),
        broken("job_strategy"),
        1.0 if repair.get("requires_attention") is True else 0.0,
        1.0 if market.get("freshness", {}).get("status") != "fresh" else 0.0,
        _clamp(low_ratio, 0.0, 1.0),
        degraded_ratio,
        old_ratio,
        1.0 if _resource_normal(plan) else 0.0,
        1.0 if plan.get("state_corruption_hold") is True else 0.0,
    ]


def market_regime(plan: dict[str, Any]) -> dict[str, Any]:
    profile = plan.get("market_profile") if isinstance(plan.get("market_profile"), dict) else {}
    freshness = profile.get("freshness") if isinstance(profile.get("freshness"), dict) else {}
    low = list(profile.get("low_coverage_regions") or [])
    ratio = _finite(profile.get("degraded_source_ratio"))
    if freshness.get("status") != "fresh":
        regime = "FRESHNESS_HOLD"
    elif low and ratio is not None and ratio > 0.35:
        regime = "COVERAGE_AND_SOURCE_STRESS"
    elif low:
        regime = "UNDERCOVERED"
    elif ratio is not None and ratio > 0.35:
        regime = "SOURCE_DEGRADED"
    else:
        regime = "HEALTHY"
    return {
        "regime": regime,
        "low_coverage_regions": low,
        "degraded_source_ratio": round(ratio, 6) if ratio is not None else None,
        "market_direction_inferred": False,
    }


def _default_meta_model(now: datetime) -> dict[str, Any]:
    w1 = [
        [round(math.sin((i + 1) * (j + 2)) * 0.025, 9) for j in range(META_HIDDEN_DIM)]
        for i in range(META_INPUT_DIM)
    ]
    w2 = [
        [round(math.cos((i + 3) * (j + 1)) * 0.025, 9) for j in range(len(META_ACTIONS))]
        for i in range(META_HIDDEN_DIM)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "trained_at": now.isoformat(timespec="seconds"),
        "sample_count": 0,
        "input_dim": META_INPUT_DIM,
        "hidden_dim": META_HIDDEN_DIM,
        "actions": list(META_ACTIONS),
        "w1": w1,
        "b1": [0.0] * META_HIDDEN_DIM,
        "w2": w2,
        "b2": [0.0] * len(META_ACTIONS),
    }


def _validate_matrix(value: Any, rows: int, cols: int) -> bool:
    if not isinstance(value, list) or len(value) != rows:
        return False
    for row in value:
        if not isinstance(row, list) or len(row) != cols:
            return False
        for item in row:
            number = _finite(item)
            if number is None or abs(number) > 4.0:
                return False
    return True


def validate_meta_model(model: Any, *, now: datetime | None = None) -> bool:
    if not isinstance(model, dict):
        return False
    if model.get("schema_version") != SCHEMA_VERSION or model.get("controller_version") != CONTROLLER_VERSION:
        return False
    if model.get("input_dim") != META_INPUT_DIM or model.get("hidden_dim") != META_HIDDEN_DIM:
        return False
    if model.get("actions") != list(META_ACTIONS):
        return False
    if not _validate_matrix(model.get("w1"), META_INPUT_DIM, META_HIDDEN_DIM):
        return False
    if not _validate_matrix(model.get("w2"), META_HIDDEN_DIM, len(META_ACTIONS)):
        return False
    if not _validate_matrix([model.get("b1")], 1, META_HIDDEN_DIM):
        return False
    if not _validate_matrix([model.get("b2")], 1, len(META_ACTIONS)):
        return False
    trained = _parse_time(model.get("trained_at"))
    moment = (now or _now()).astimezone(timezone.utc)
    if trained is None or trained > moment + timedelta(minutes=5):
        return False
    if (moment - trained).total_seconds() > META_MAX_AGE_SECONDS:
        return False
    sample_count = model.get("sample_count")
    return isinstance(sample_count, int) and not isinstance(sample_count, bool) and 0 <= sample_count <= MAX_META_OUTCOMES


def load_meta_model(*, path: Path = META_MODEL_PATH, now: datetime | None = None) -> dict[str, Any] | None:
    model = _read_json(path, max_bytes=2_000_000)
    return model if validate_meta_model(model, now=now) else None


def _forward(model: dict[str, Any], features: list[float]) -> tuple[list[float], list[float]]:
    hidden = []
    for j in range(META_HIDDEN_DIM):
        total = float(model["b1"][j])
        for i, value in enumerate(features):
            total += value * float(model["w1"][i][j])
        hidden.append(math.tanh(total))
    outputs = []
    for k in range(len(META_ACTIONS)):
        total = float(model["b2"][k])
        for j, value in enumerate(hidden):
            total += value * float(model["w2"][j][k])
        outputs.append(math.tanh(total))
    return hidden, outputs


def meta_scores(model: dict[str, Any] | None, features: list[float]) -> dict[str, float]:
    if model is None or len(features) != META_INPUT_DIM or any(_finite(x) is None for x in features):
        return {action: 0.0 for action in META_ACTIONS}
    _, outputs = _forward(model, [_clamp(float(x), 0.0, 1.0) for x in features])
    return {action: round(_clamp(outputs[i], -1.0, 1.0), 6) for i, action in enumerate(META_ACTIONS)}


def load_verified_outcomes(*, path: Path = OUTCOMES_PATH) -> list[dict[str, Any]]:
    try:
        if not path.is_file() or path.is_symlink():
            return []
        text = safe_read_text(path, max_bytes=MAX_OUTCOME_BYTES)
    except (OSError, UnicodeError, ValueError, TypeError):
        return []
    rows = []
    for raw_line in text.splitlines()[-MAX_META_OUTCOMES:]:
        try:
            row = json.loads(raw_line)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(row, dict) or row.get("verified") is not True:
            continue
        action = str(row.get("action_id") or "")
        reward = _finite(row.get("reward"))
        features = row.get("features")
        evidence = str(row.get("evidence_ref") or "").strip()
        if action not in META_ACTIONS or reward is None or not evidence:
            continue
        if not isinstance(features, list) or len(features) != META_INPUT_DIM:
            continue
        cleaned = []
        valid = True
        for item in features:
            number = _finite(item)
            if number is None or number < 0.0 or number > 1.0:
                valid = False
                break
            cleaned.append(float(number))
        if not valid:
            continue
        rows.append({
            "action_id": action,
            "reward": _clamp(reward, -1.0, 1.0),
            "features": cleaned,
            "evidence_ref": evidence[:240],
        })
    return rows


def train_meta_model(
    rows: list[dict[str, Any]], *, now: datetime | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if len(rows) < MIN_META_OUTCOMES:
        return None
    moment = (now or _now()).astimezone(timezone.utc)
    model = json.loads(json.dumps(existing)) if validate_meta_model(existing, now=moment) else _default_meta_model(moment)
    action_index = {action: i for i, action in enumerate(META_ACTIONS)}
    rows = rows[-MAX_META_OUTCOMES:]
    for _ in range(META_EPOCHS):
        for row in rows:
            x = row["features"]
            target = float(row["reward"])
            k = action_index[row["action_id"]]
            hidden, outputs = _forward(model, x)
            output = outputs[k]
            dz2 = (output - target) * (1.0 - output * output)
            old_w2 = [float(model["w2"][j][k]) for j in range(META_HIDDEN_DIM)]
            for j in range(META_HIDDEN_DIM):
                updated = float(model["w2"][j][k]) - META_LEARNING_RATE * dz2 * hidden[j]
                model["w2"][j][k] = _clamp(updated, -4.0, 4.0)
            model["b2"][k] = _clamp(float(model["b2"][k]) - META_LEARNING_RATE * dz2, -4.0, 4.0)
            for j in range(META_HIDDEN_DIM):
                dh = dz2 * old_w2[j] * (1.0 - hidden[j] * hidden[j])
                for i in range(META_INPUT_DIM):
                    updated = float(model["w1"][i][j]) - META_LEARNING_RATE * dh * x[i]
                    model["w1"][i][j] = _clamp(updated, -4.0, 4.0)
                model["b1"][j] = _clamp(float(model["b1"][j]) - META_LEARNING_RATE * dh, -4.0, 4.0)
    model["trained_at"] = moment.isoformat(timespec="seconds")
    model["sample_count"] = len(rows)
    return model if validate_meta_model(model, now=moment) else None


def persist_meta_model(model: dict[str, Any], *, path: Path = META_MODEL_PATH) -> dict[str, Any]:
    if not validate_meta_model(model):
        return {"status": "INVALID_META_MODEL", "written": False}
    try:
        atomic_write_json(path, model, suffix=".meta-neural.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "META_MODEL_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "META_MODEL_SAVED", "written": True}


def _capability_id(primitive: str, suffix: str) -> str:
    normalized = "".join(ch for ch in suffix.upper() if ch.isalnum() or ch in "_-")[:64]
    return f"{primitive}:{normalized or 'DEFAULT'}"


def _capability(
    primitive: str, suffix: str, params: dict[str, Any], evidence: dict[str, Any],
    *, now: datetime,
) -> dict[str, Any]:
    return {
        "id": _capability_id(primitive, suffix),
        "primitive": primitive,
        "parameters": params,
        "evidence": evidence,
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": (now + timedelta(seconds=CAPABILITY_TTL_SECONDS)).isoformat(timespec="seconds"),
        "auto_generated": True,
        "auto_active": True,
        "source_code_change": False,
        "arbitrary_command": False,
        "scope": "operational_policy",
    }


def validate_capability(row: Any, *, now: datetime | None = None) -> bool:
    if not isinstance(row, dict):
        return False
    primitive = str(row.get("primitive") or "")
    spec = CAPABILITY_PRIMITIVES.get(primitive)
    if spec is None or row.get("auto_generated") is not True or row.get("auto_active") is not True:
        return False
    if row.get("source_code_change") is not False or row.get("arbitrary_command") is not False:
        return False
    params = row.get("parameters")
    if not isinstance(params, dict) or set(spec["required"]) - set(params):
        return False
    created = _parse_time(row.get("created_at"))
    expires = _parse_time(row.get("expires_at"))
    moment = (now or _now()).astimezone(timezone.utc)
    if created is None or expires is None or expires <= moment:
        return False
    if created > moment + timedelta(minutes=5) or expires - created > timedelta(seconds=MAX_CAPABILITY_TTL_SECONDS):
        return False

    if primitive == "PRIORITIZE_REGION":
        boost = _finite(params.get("boost"))
        return str(params.get("region") or "") in spec["regions"] and boost is not None and 0 < boost <= MAX_OPERATIONAL_BOOST
    if primitive == "RETRY_DEGRADED_SOURCES":
        retry = params.get("max_retry")
        backoff = params.get("backoff_seconds")
        return (
            isinstance(retry, int) and not isinstance(retry, bool) and 1 <= retry <= 3
            and isinstance(backoff, int) and not isinstance(backoff, bool) and 30 <= backoff <= 900
        )
    if primitive == "REQUEST_FRESHNESS_REFRESH":
        runs = params.get("max_runs")
        return isinstance(runs, int) and not isinstance(runs, bool) and runs == 1
    if primitive == "PRIORITIZE_SAFE_LEARNING":
        boost = _finite(params.get("boost"))
        return (
            str(params.get("action_id") or "") in spec["actions"]
            and boost is not None and 0 < boost <= MAX_OPERATIONAL_BOOST
        )
    if primitive == "INCREASE_OBSERVATION":
        factor = _finite(params.get("factor"))
        return str(params.get("scope") or "") in spec["scopes"] and factor is not None and 1.0 < factor <= 1.5
    return False


def synthesize_capabilities(plan: dict[str, Any], *, now: datetime | None = None) -> list[dict[str, Any]]:
    moment = (now or _now()).astimezone(timezone.utc)
    regime = market_regime(plan)
    rows: list[dict[str, Any]] = []
    for region in regime["low_coverage_regions"]:
        rows.append(_capability(
            "PRIORITIZE_REGION", str(region),
            {"region": str(region), "boost": 0.12},
            {"reason": "region_coverage_gap", "regime": regime["regime"]},
            now=moment,
        ))
    ratio = regime.get("degraded_source_ratio")
    if isinstance(ratio, (int, float)) and ratio > 0.35:
        rows.append(_capability(
            "RETRY_DEGRADED_SOURCES", "MARKET",
            {"max_retry": 2, "backoff_seconds": 120},
            {"reason": "degraded_source_ratio", "ratio": ratio},
            now=moment,
        ))
    if regime["regime"] == "FRESHNESS_HOLD":
        rows.append(_capability(
            "REQUEST_FRESHNESS_REFRESH", "MARKET",
            {"max_runs": 1},
            {"reason": "market_freshness_hold"},
            now=moment,
        ))

    signals = plan.get("signals") if isinstance(plan.get("signals"), dict) else {}
    runtime = signals.get("runtime_models") if isinstance(signals.get("runtime_models"), dict) else {}
    models = runtime.get("models") if isinstance(runtime.get("models"), dict) else {}
    for model_name, action in (
        ("query_strategy", "TRAIN_QUERY_STRATEGY"),
        ("job_strategy", "TRAIN_JOB_STRATEGY"),
    ):
        row = models.get(model_name) if isinstance(models.get(model_name), dict) else {}
        if str(row.get("status") or "") in {"broken", "degraded"}:
            rows.append(_capability(
                "PRIORITIZE_SAFE_LEARNING", action,
                {"action_id": action, "boost": 0.10},
                {"reason": "model_needs_recovery", "model": model_name},
                now=moment,
            ))
    repair = signals.get("repair_neural") if isinstance(signals.get("repair_neural"), dict) else {}
    if repair.get("requires_attention") is True:
        rows.append(_capability(
            "PRIORITIZE_SAFE_LEARNING", "TRAIN_REPAIR_PRIORITY",
            {"action_id": "TRAIN_REPAIR_PRIORITY", "boost": 0.10},
            {"reason": "repair_neural_requires_attention"},
            now=moment,
        ))
    if regime["regime"] != "HEALTHY":
        rows.append(_capability(
            "INCREASE_OBSERVATION", "MARKET_HEALTH",
            {"scope": "market_health", "factor": 1.25},
            {"reason": "market_operational_stress", "regime": regime["regime"]},
            now=moment,
        ))
    return [row for row in rows if validate_capability(row, now=moment)]


def load_capabilities(*, path: Path = CAPABILITY_PATH, now: datetime | None = None) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    raw = _read_json(path, max_bytes=1_000_000)
    if raw is None:
        return {"status": "fresh", "capabilities": [], "corruption_hold": False}
    rows = raw.get("capabilities")
    if not isinstance(rows, list) or len(rows) > MAX_CAPABILITIES:
        return {"status": "corrupt", "capabilities": [], "corruption_hold": True}
    valid = []
    invalid_count = 0
    for row in rows:
        if validate_capability(row, now=moment):
            valid.append(row)
        else:
            invalid_count += 1
    if invalid_count:
        return {"status": "corrupt", "capabilities": [], "corruption_hold": True, "invalid_count": invalid_count}
    return {"status": "loaded", "capabilities": valid, "corruption_hold": False}


def merge_capabilities(
    existing: list[dict[str, Any]], generated: list[dict[str, Any]], *, now: datetime | None = None
) -> list[dict[str, Any]]:
    moment = (now or _now()).astimezone(timezone.utc)
    merged: dict[str, dict[str, Any]] = {}
    for row in list(existing) + list(generated):
        if validate_capability(row, now=moment):
            merged[str(row["id"])] = row
    ordered = sorted(merged.values(), key=lambda row: (str(row["primitive"]), str(row["id"])))
    return ordered[:MAX_CAPABILITIES]


def save_capabilities(
    rows: list[dict[str, Any]], *, path: Path = CAPABILITY_PATH,
    corruption_hold: bool = False, now: datetime | None = None,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    if corruption_hold:
        return {"status": "CAPABILITY_CORRUPTION_HOLD", "written": False}
    if len(rows) > MAX_CAPABILITIES or any(not validate_capability(row, now=moment) for row in rows):
        return {"status": "INVALID_CAPABILITY_SET", "written": False}
    payload = {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "updated_at": moment.isoformat(timespec="seconds"),
        "capabilities": rows,
    }
    try:
        atomic_write_json(path, payload, suffix=".capability.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {"status": "CAPABILITY_WRITE_FAILED", "written": False, "error_code": type(exc).__name__}
    return {"status": "CAPABILITIES_SAVED", "written": True, "count": len(rows)}


def capability_priority_boosts(rows: list[dict[str, Any]]) -> dict[str, float]:
    boosts = {action: 0.0 for action in v372.SAFE_LEARNING_ACTIONS}
    for row in rows:
        if row.get("primitive") != "PRIORITIZE_SAFE_LEARNING":
            continue
        params = row.get("parameters") if isinstance(row.get("parameters"), dict) else {}
        action = str(params.get("action_id") or "")
        boost = _finite(params.get("boost"))
        if action in boosts and boost is not None:
            boosts[action] = _clamp(boosts[action] + boost, 0.0, MAX_OPERATIONAL_BOOST)
    return boosts


def adaptive_rank_plan(
    plan: dict[str, Any], *, model: dict[str, Any] | None, capabilities: list[dict[str, Any]]
) -> dict[str, Any]:
    result = dict(plan)
    features = feature_vector(plan)
    scores = meta_scores(model, features)
    boosts = capability_priority_boosts(capabilities)
    actions = [dict(row) for row in plan.get("actions", []) if isinstance(row, dict)]
    for row in actions:
        action_id = str(row.get("id") or "")
        base_priority = int(row.get("priority") or 0)
        neural_delta = int(round(scores.get(action_id, 0.0) * MAX_NEURAL_PRIORITY_DELTA))
        capability_delta = int(round(boosts.get(action_id, 0.0) * 100))
        row["base_priority"] = base_priority
        row["neural_priority_delta"] = max(-MAX_NEURAL_PRIORITY_DELTA, min(MAX_NEURAL_PRIORITY_DELTA, neural_delta))
        row["capability_priority_delta"] = max(0, min(int(MAX_OPERATIONAL_BOOST * 100), capability_delta))
        row["adaptive_priority"] = base_priority + row["neural_priority_delta"] + row["capability_priority_delta"]
    actions.sort(key=lambda row: (-int(row.get("adaptive_priority", row.get("priority", 0))), str(row.get("id") or "")))
    result["actions"] = actions
    result["meta_features"] = features
    result["meta_scores"] = scores
    result["market_regime"] = market_regime(plan)
    result["active_capabilities"] = capabilities

    deferred = plan.get("deferred_safe_learning_actions")
    selected = plan.get("selected_safe_learning_actions")
    eligible = set(selected if isinstance(selected, list) else [])
    if isinstance(deferred, list):
        for row in deferred:
            if isinstance(row, dict) and row.get("reason") == "per_cycle_training_budget":
                eligible.add(str(row.get("id") or ""))
    eligible &= set(v372.SAFE_LEARNING_ACTIONS)
    budget = int(plan.get("training_budget") or 0)
    if budget > 0 and eligible:
        score_by_id = {
            str(row.get("id") or ""): int(row.get("adaptive_priority", row.get("priority", 0)))
            for row in actions
        }
        winner = max(sorted(eligible), key=lambda action: score_by_id.get(action, -10_000))
        result["selected_safe_learning_actions"] = [winner]
        new_deferred = []
        for row in deferred if isinstance(deferred, list) else []:
            if not isinstance(row, dict):
                continue
            action = str(row.get("id") or "")
            if action == winner and row.get("reason") == "per_cycle_training_budget":
                continue
            new_deferred.append(dict(row))
        for action in sorted(eligible - {winner}):
            if not any(str(row.get("id") or "") == action for row in new_deferred):
                new_deferred.append({"id": action, "reason": "adaptive_meta_policy_budget"})
        result["deferred_safe_learning_actions"] = new_deferred
    return result


def run_cycle(
    *, execute: bool = False, apply_capabilities: bool = False, train_meta: bool = False,
    root: Path = ROOT, now: datetime | None = None, proc_root: Path = Path("/proc"),
    state_path: Path | None = None, capability_path: Path | None = None,
    meta_model_path: Path | None = None, outcomes_path: Path | None = None,
    persist_outputs: bool = True,
) -> dict[str, Any]:
    moment = (now or _now()).astimezone(timezone.utc)
    state = state_path or (root / v372.STATE_PATH.name)
    cap_path = capability_path or (root / CAPABILITY_PATH.name)
    model_path = meta_model_path or (root / META_MODEL_PATH.name)
    outcome_path = outcomes_path or (root / OUTCOMES_PATH.name)

    base = v372.plan_cycle(root=root, now=moment, proc_root=proc_root, state_path=state)
    loaded_caps = load_capabilities(path=cap_path, now=moment)
    generated = synthesize_capabilities(base, now=moment)
    capabilities = merge_capabilities(loaded_caps["capabilities"], generated, now=moment)

    model = load_meta_model(path=model_path, now=moment)
    training = {"status": "META_TRAINING_NOT_REQUESTED", "written": False}
    if train_meta:
        rows = load_verified_outcomes(path=outcome_path)
        candidate = train_meta_model(rows, now=moment, existing=model)
        if candidate is None:
            training = {"status": "META_TRAINING_GATE_HELD", "written": False, "verified_outcomes": len(rows)}
        else:
            training = persist_meta_model(candidate, path=model_path)
            training["verified_outcomes"] = len(rows)
            if training.get("written") is True:
                model = candidate

    plan = adaptive_rank_plan(base, model=model, capabilities=capabilities)
    execution = (
        v372.execute_safe_learning(plan, state_path=state, now=moment)
        if execute else {
            "status": "PLAN_ONLY", "results": {}, "proposals_executed": False,
            "git_write": False, "source_code_modified": False,
        }
    )

    capability_write = {"status": "CAPABILITY_APPLY_NOT_REQUESTED", "written": False}
    if apply_capabilities:
        capability_write = save_capabilities(
            capabilities, path=cap_path, corruption_hold=bool(loaded_caps["corruption_hold"]), now=moment
        )

    result = {
        "controller_version": CONTROLLER_VERSION,
        "plan": plan,
        "execution": execution,
        "capability_state": {
            "load_status": loaded_caps["status"],
            "corruption_hold": loaded_caps["corruption_hold"],
            "generated_count": len(generated),
            "active_count": len(capabilities),
            "write": capability_write,
        },
        "meta_neural": {
            "active": model is not None,
            "sample_count": int(model.get("sample_count") or 0) if model else 0,
            "training": training,
        },
        "safety": SAFETY,
    }
    if persist_outputs:
        try:
            atomic_write_json(root / REPORT_PATH.name, result, suffix=".v373-report.tmp")
            result["runtime_output"] = {"status": "SAVED"}
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            result["runtime_output"] = {"status": "WRITE_FAILED", "error_code": type(exc).__name__}
    return result


def self_test() -> None:
    assert SAFETY["meta_neural_verified_outcomes_only"] is True
    assert SAFETY["declarative_capability_auto_generation"] is True
    assert SAFETY["source_code_auto_generation"] is False
    assert SAFETY["source_code_auto_rewrite"] is False
    assert SAFETY["git_write"] is False
    assert SAFETY["market_direction_inferred"] is False
    assert set(CAPABILITY_PRIMITIVES) == {
        "PRIORITIZE_REGION",
        "RETRY_DEGRADED_SOURCES",
        "REQUEST_FRESHNESS_REFRESH",
        "PRIORITIZE_SAFE_LEARNING",
        "INCREASE_OBSERVATION",
    }
    print("Tablet autonomous meta-neural evolution v373: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-safe-learning", action="store_true")
    parser.add_argument("--apply-capabilities", action="store_true")
    parser.add_argument("--train-meta", action="store_true")
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
    )
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())