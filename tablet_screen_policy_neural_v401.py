#!/usr/bin/env python3
"""Verified-outcome screen-policy neural adapter for the tablet runtime.

This module learns only from V400 history rows that contain:
- an applied allowlisted screen plan,
- a bounded operational feature vector,
- verified surface scores before and after that plan.

It never reads clicks, pointer movement, browsing history, card facts or free-form
user content. The model is advisory-only: it produces a small bounded bias for
the existing 18 allowlisted tablet features. Source generation, arbitrary
commands, Git writes and direct UI mutation are outside this module.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "tablet_screen_policy_neural_v401.json"
CONTROLLER_VERSION = "v401-screen-policy"
SCHEMA_VERSION = 1

SURFACES = (
    "ui",
    "card_measurement",
    "card_market",
    "card_release",
    "collab_event",
    "purchase_availability",
    "tablet_ops",
)
FEATURE_KEYS = (
    "auto-grade",
    "manual-photo",
    "precision-grade",
    "market-search",
    "grading-economics",
    "trading-catalog",
    "box-knowledge",
    "box-hit-analysis",
    "release-info",
    "promo-event-info",
    "purchase-finder",
    "purchase-distance",
    "card-ocr",
    "verified-grade",
    "learning-status",
    "tablet-manager",
    "code-audit",
    "code-validation",
)
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

INPUT_DIM = 17  # 7 urgencies + 7 confidences + release/event/market activity.
HIDDEN_DIM = 12
MIN_TRAINING_ROWS = 12
MAX_TRAINING_ROWS = 512
MAX_MODEL_BYTES = 2_000_000
MAX_MODEL_AGE_SECONDS = 45 * 24 * 60 * 60
LEARNING_RATE = 0.025
EPOCHS = 12
MAX_FEATURE_BIAS = 0.05
MAX_TARGET_DELTA = 0.20
MIN_VERIFIED_CONFIDENCE = 0.55

SAFETY = {
    "verified_surface_outcomes_only": True,
    "allowlisted_features_only": True,
    "advisory_only": True,
    "feature_bias_bounded": True,
    "user_behavior_tracking": False,
    "market_direction_inferred": False,
    "source_code_generation": False,
    "source_code_rewrite": False,
    "arbitrary_command_execution": False,
    "git_write": False,
    "direct_main_write": False,
    "verification_bypass": False,
    "price_grade_stock_release_event_fact_invention": False,
}


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


def _clamp(value: float, low: float, high: float) -> float:
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


def policy_features(portfolio: dict[str, Any], activity: dict[str, Any]) -> list[float]:
    rows = portfolio.get("surfaces") if isinstance(portfolio.get("surfaces"), list) else []
    by_surface = {
        str(row.get("surface") or ""): row
        for row in rows
        if isinstance(row, dict)
    }
    values: list[float] = []
    for surface in SURFACES:
        row = by_surface.get(surface) or {}
        values.append(_clamp(float(_finite(row.get("urgency")) or 0.0), 0.0, 1.0))
    for surface in SURFACES:
        row = by_surface.get(surface) or {}
        values.append(_clamp(float(_finite(row.get("confidence")) or 0.0), 0.0, 1.0))
    for key in ("release_activity", "event_activity", "market_activity"):
        values.append(_clamp(float(_finite(activity.get(key)) or 0.0), 0.0, 1.0))
    return values


def _default_model(now: datetime) -> dict[str, Any]:
    w1 = [
        [round(math.sin((i + 1) * (j + 2)) * 0.02, 9) for j in range(HIDDEN_DIM)]
        for i in range(INPUT_DIM)
    ]
    w2 = [
        [round(math.cos((i + 3) * (j + 1)) * 0.02, 9) for j in range(len(FEATURE_KEYS))]
        for i in range(HIDDEN_DIM)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "controller_version": CONTROLLER_VERSION,
        "trained_at": now.isoformat(timespec="seconds"),
        "sample_count": 0,
        "input_dim": INPUT_DIM,
        "hidden_dim": HIDDEN_DIM,
        "features": list(FEATURE_KEYS),
        "w1": w1,
        "b1": [0.0] * HIDDEN_DIM,
        "w2": w2,
        "b2": [0.0] * len(FEATURE_KEYS),
    }


def _valid_matrix(value: Any, rows: int, cols: int) -> bool:
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


def _valid_structure(model: Any) -> bool:
    if not isinstance(model, dict):
        return False
    if model.get("schema_version") != SCHEMA_VERSION or model.get("controller_version") != CONTROLLER_VERSION:
        return False
    if model.get("input_dim") != INPUT_DIM or model.get("hidden_dim") != HIDDEN_DIM:
        return False
    if model.get("features") != list(FEATURE_KEYS):
        return False
    if not _valid_matrix(model.get("w1"), INPUT_DIM, HIDDEN_DIM):
        return False
    if not _valid_matrix([model.get("b1")], 1, HIDDEN_DIM):
        return False
    if not _valid_matrix(model.get("w2"), HIDDEN_DIM, len(FEATURE_KEYS)):
        return False
    if not _valid_matrix([model.get("b2")], 1, len(FEATURE_KEYS)):
        return False
    count = model.get("sample_count")
    return isinstance(count, int) and not isinstance(count, bool) and 0 <= count <= MAX_TRAINING_ROWS


def validate_model(model: Any, *, now: datetime | None = None) -> bool:
    if not _valid_structure(model):
        return False
    stamp = _parse_time(model.get("trained_at"))
    moment = (now or _now()).astimezone(timezone.utc)
    return (
        stamp is not None
        and stamp <= moment + timedelta(minutes=5)
        and (moment - stamp).total_seconds() <= MAX_MODEL_AGE_SECONDS
    )


def load_model(path: Path = MODEL_PATH, *, now: datetime | None = None) -> dict[str, Any]:
    if not path.exists():
        return {"status": "SCREEN_NEURAL_FRESH", "model": None, "corruption_hold": False}
    try:
        if path.is_symlink() or not path.is_file():
            raise ValueError("UNSAFE_SCREEN_NEURAL_MODEL_PATH")
        model = json.loads(safe_read_text(path, max_bytes=MAX_MODEL_BYTES))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {
            "status": "SCREEN_NEURAL_CORRUPTION_HOLD",
            "model": None,
            "corruption_hold": True,
            "error_code": type(exc).__name__,
        }
    if not _valid_structure(model):
        return {
            "status": "SCREEN_NEURAL_CORRUPTION_HOLD",
            "model": None,
            "corruption_hold": True,
            "error_code": "SCREEN_NEURAL_SCHEMA_INVALID",
        }
    if not validate_model(model, now=now):
        return {"status": "SCREEN_NEURAL_STALE", "model": None, "corruption_hold": False}
    return {"status": "SCREEN_NEURAL_LOADED", "model": model, "corruption_hold": False}


def _forward(model: dict[str, Any], features: list[float]) -> tuple[list[float], list[float]]:
    x = [_clamp(float(value), 0.0, 1.0) for value in features]
    hidden = []
    for j in range(HIDDEN_DIM):
        total = float(model["b1"][j])
        for i, value in enumerate(x):
            total += value * float(model["w1"][i][j])
        hidden.append(math.tanh(total))
    outputs = []
    for k in range(len(FEATURE_KEYS)):
        total = float(model["b2"][k])
        for j, value in enumerate(hidden):
            total += hidden[j] * float(model["w2"][j][k])
        outputs.append(math.tanh(total))
    return hidden, outputs


def feature_bias(model: dict[str, Any] | None, features: list[float], *, now: datetime | None = None) -> dict[str, Any]:
    sample_count = (
        int(model.get("sample_count") or 0)
        if isinstance(model, dict)
        and isinstance(model.get("sample_count"), int)
        and not isinstance(model.get("sample_count"), bool)
        else 0
    )
    active = (
        validate_model(model, now=now)
        and sample_count >= MIN_TRAINING_ROWS
        and len(features) == INPUT_DIM
    )
    if not active:
        return {
            "active": False,
            "sample_count": sample_count,
            "feature_biases": {key: 0.0 for key in FEATURE_KEYS},
            "max_abs_bias": 0.0,
            "verified_surface_outcomes_only": True,
            "advisory_only": True,
        }
    _, outputs = _forward(model, features)
    biases = {
        key: round(_clamp(outputs[index] * MAX_FEATURE_BIAS, -MAX_FEATURE_BIAS, MAX_FEATURE_BIAS), 6)
        for index, key in enumerate(FEATURE_KEYS)
    }
    return {
        "active": True,
        "sample_count": int(model.get("sample_count") or 0),
        "feature_biases": biases,
        "max_abs_bias": round(max(abs(value) for value in biases.values()), 6),
        "verified_surface_outcomes_only": True,
        "advisory_only": True,
    }


def training_rows(
    history: list[dict[str, Any]],
    *,
    current_surface_scores: dict[str, float] | None = None,
    current_surface_confidences: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    cleaned = [row for row in history[-192:] if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(cleaned):
        if row.get("adaptive_applied") is not True:
            continue
        features = row.get("policy_features")
        before = row.get("surface_scores")
        before_conf = row.get("surface_confidences")
        top = row.get("top_features")
        if not isinstance(features, list) or len(features) != INPUT_DIM:
            continue
        normalized: list[float] = []
        valid = True
        for item in features:
            number = _finite(item)
            if number is None or number < 0.0 or number > 1.0:
                valid = False
                break
            normalized.append(float(number))
        if (
            not valid
            or not isinstance(before, dict)
            or not isinstance(before_conf, dict)
            or not isinstance(top, list)
        ):
            continue

        after = None
        after_conf = None
        for later in cleaned[index + 1:]:
            candidate = later.get("surface_scores")
            confidence = later.get("surface_confidences")
            if isinstance(candidate, dict) and isinstance(confidence, dict):
                after = candidate
                after_conf = confidence
                break
        if (
            after is None
            and isinstance(current_surface_scores, dict)
            and isinstance(current_surface_confidences, dict)
        ):
            after = current_surface_scores
            after_conf = current_surface_confidences
        if not isinstance(after, dict) or not isinstance(after_conf, dict):
            continue

        for rank, raw_feature in enumerate(top[:5]):
            feature = str(raw_feature)
            surface = FEATURE_SURFACE.get(feature)
            if feature not in FEATURE_KEYS or not surface:
                continue
            start = _finite(before.get(surface))
            end = _finite(after.get(surface))
            start_conf = _finite(before_conf.get(surface))
            end_conf = _finite(after_conf.get(surface))
            if (
                start is None
                or end is None
                or start_conf is None
                or end_conf is None
                or start_conf < MIN_VERIFIED_CONFIDENCE
                or end_conf < MIN_VERIFIED_CONFIDENCE
            ):
                continue
            delta = _clamp(float(end) - float(start), -MAX_TARGET_DELTA, MAX_TARGET_DELTA)
            target = delta / MAX_TARGET_DELTA if MAX_TARGET_DELTA else 0.0
            confidence_weight = _clamp(min(float(start_conf), float(end_conf)), 0.0, 1.0)
            rows.append({
                "feature_key": feature,
                "target": round(_clamp(target, -1.0, 1.0), 6),
                "rank_weight": round(max(0.60, 1.0 - 0.10 * rank) * confidence_weight, 6),
                "features": normalized,
                "evidence_ref": str(row.get("observed_at") or f"cycle:{row.get('cycle')}")[:160],
            })
    return rows[-MAX_TRAINING_ROWS:]


def train_model(
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if len(rows) < MIN_TRAINING_ROWS:
        return None
    moment = (now or _now()).astimezone(timezone.utc)
    model = json.loads(json.dumps(existing)) if validate_model(existing, now=moment) else _default_model(moment)
    feature_index = {key: index for index, key in enumerate(FEATURE_KEYS)}
    usable = rows[-MAX_TRAINING_ROWS:]
    for _ in range(EPOCHS):
        for row in usable:
            feature = str(row.get("feature_key") or "")
            x = row.get("features")
            target = _finite(row.get("target"))
            weight = _finite(row.get("rank_weight"))
            if feature not in feature_index or not isinstance(x, list) or len(x) != INPUT_DIM:
                continue
            if target is None or weight is None:
                continue
            if any(_finite(item) is None or not 0.0 <= float(item) <= 1.0 for item in x):
                continue
            k = feature_index[feature]
            hidden, outputs = _forward(model, [float(item) for item in x])
            output = outputs[k]
            dz2 = (output - _clamp(float(target), -1.0, 1.0)) * (1.0 - output * output)
            dz2 *= _clamp(float(weight), 0.5, 1.0)
            old_w2 = [float(model["w2"][j][k]) for j in range(HIDDEN_DIM)]
            for j in range(HIDDEN_DIM):
                model["w2"][j][k] = _clamp(
                    float(model["w2"][j][k]) - LEARNING_RATE * dz2 * hidden[j],
                    -4.0, 4.0,
                )
            model["b2"][k] = _clamp(float(model["b2"][k]) - LEARNING_RATE * dz2, -4.0, 4.0)
            for j in range(HIDDEN_DIM):
                dh = dz2 * old_w2[j] * (1.0 - hidden[j] * hidden[j])
                for i, value in enumerate(x):
                    model["w1"][i][j] = _clamp(
                        float(model["w1"][i][j]) - LEARNING_RATE * dh * float(value),
                        -4.0, 4.0,
                    )
                model["b1"][j] = _clamp(float(model["b1"][j]) - LEARNING_RATE * dh, -4.0, 4.0)
    model["trained_at"] = moment.isoformat(timespec="seconds")
    model["sample_count"] = min(MAX_TRAINING_ROWS, len(usable))
    return model if validate_model(model, now=moment) else None


def persist_model(model: dict[str, Any], path: Path = MODEL_PATH, *, now: datetime | None = None) -> dict[str, Any]:
    if not validate_model(model, now=now):
        return {"status": "SCREEN_NEURAL_INVALID_MODEL", "written": False}
    try:
        atomic_write_json(path, model, suffix=".screen-neural.tmp")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {
            "status": "SCREEN_NEURAL_WRITE_FAILED",
            "written": False,
            "error_code": type(exc).__name__,
        }
    return {
        "status": "SCREEN_NEURAL_MODEL_SAVED",
        "written": True,
        "sample_count": int(model.get("sample_count") or 0),
    }


def self_test() -> None:
    now = _now()
    model = _default_model(now)
    assert validate_model(model, now=now)
    assert len(policy_features({"surfaces": []}, {})) == INPUT_DIM
    assert set(FEATURE_KEYS) == set(FEATURE_SURFACE)
    assert 0.5 <= MIN_VERIFIED_CONFIDENCE <= 1.0
    assert SAFETY["verified_surface_outcomes_only"] is True
    assert SAFETY["user_behavior_tracking"] is False
    assert SAFETY["source_code_generation"] is False
    assert SAFETY["git_write"] is False
    print("Tablet verified screen-policy neural adapter v401: PASS")


if __name__ == "__main__":
    self_test()
