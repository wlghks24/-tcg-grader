#!/usr/bin/env python3
"""Verified-only neural ranking for bounded SELFREFINE repair rules.

The neural model never generates source text, commands, paths, or git actions.
It can only rank code-defined allowlisted repair rules that the existing
verified_code_repair_rules gate has already accepted. Training labels are
accepted only from full-regression-verified repair-state history.

Activation requirements:
- at least 1,000 independent repair labels
- both success and failure classes represented by at least 100 labels
- one-hidden-layer candidates with hidden sizes 4, 8, and 12 are compared
- holdout performance must beat a constant-rate baseline before activation
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
LABELS_PATH = ROOT / "VERIFIED_NEURAL_REPAIR_LABELS.json"
MODEL_PATH = ROOT / "VERIFIED_NEURAL_REPAIR_MODEL.json"
REPORT_PATH = ROOT / "VERIFIED_NEURAL_REPAIR_REPORT.json"

SCHEMA = 1
MIN_INDEPENDENT_LABELS = 1000
MIN_CLASS_LABELS = 100
MAX_LABELS = 5000
HIDDEN_SIZES = (4, 8, 12)
SEEDS = (20260907, 20260917, 20260927)
PROTOCOL_VERSION = 2
PATH_BUCKETS = 6
STAGE_BUCKETS = 6
FAMILY_BUCKETS = 4
EPOCHS = 64
LEARNING_RATE = 0.035
L2 = 0.0005
ACTIVATION_MIN_ACCURACY = 0.65
ACTIVATION_MIN_LOGLOSS_GAIN = 0.01

SAFETY = {
    "verified_labels_only": True,
    "minimum_independent_labels": MIN_INDEPENDENT_LABELS,
    "minimum_each_class": MIN_CLASS_LABELS,
    "hidden_sizes_compared": list(HIDDEN_SIZES),
    "learned_text_executable": False,
    "learned_patch_text_used": False,
    "source_patch_generation": False,
    "git_write": False,
    "allowlisted_rules_only": True,
    "rule_fingerprint_required": True,
    "full_regression_required_for_training_label": True,
    "neural_output_is_priority_only": True,
    "unknown_rule_auto_repair": False,
}

RULE_ORDER = (
    "upgrade-core-actions-node24-v1",
    "close-literal-read-handles-v1",
    "align-photo-feature-contract-1-4-8-v1",
    "dynamic-feature-contract-count-v1",
    "collection-health-final-monitor-v1",
    "tablet-runtime-require-collection-health-v1",
)
FEATURE_COUNT = len(RULE_ORDER) + PATH_BUCKETS + STAGE_BUCKETS + FAMILY_BUCKETS + 3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_bucket(value: Any, buckets: int) -> int:
    raw = str(value or "").encode("utf-8", "replace")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16) % max(1, int(buckets))


def _clip01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _feature_vector(row: dict[str, Any]) -> list[float]:
    rule_id = str(row.get("rule_id") or row.get("auto_repair_rule") or row.get("fix_rule") or "")
    values: list[float] = [1.0 if rule_id == rid else 0.0 for rid in RULE_ORDER]

    path_bucket = _hash_bucket(str(row.get("path") or "").casefold(), PATH_BUCKETS)
    values.extend(1.0 if i == path_bucket else 0.0 for i in range(PATH_BUCKETS))

    stage_bucket = _hash_bucket(str(row.get("stage") or "").upper(), STAGE_BUCKETS)
    values.extend(1.0 if i == stage_bucket else 0.0 for i in range(STAGE_BUCKETS))

    family = str(row.get("error_family") or row.get("information_family") or "").casefold()
    family_bucket = _hash_bucket(family, FAMILY_BUCKETS)
    values.extend(1.0 if i == family_bucket else 0.0 for i in range(FAMILY_BUCKETS))

    values.append(1.0 if row.get("learned_solution_reuse") is True else 0.0)
    values.append(_clip01(row.get("learned_solution_confidence")))
    values.append(1.0 if row.get("auto_repair_allowed") is not False else 0.0)
    if len(values) != FEATURE_COUNT:
        raise AssertionError("feature contract mismatch")
    return values


def _default_labels() -> dict[str, Any]:
    return {"schema": SCHEMA, "updated_at": None, "labels": [], "safety": SAFETY}


def _load_json(path: Path, fallback: dict[str, Any], max_bytes: int = 4_000_000) -> dict[str, Any]:
    try:
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return fallback
    return value if isinstance(value, dict) else fallback


def _load_labels(path: Path = LABELS_PATH) -> dict[str, Any]:
    raw = _load_json(path, _default_labels())
    rows = raw.get("labels") if isinstance(raw.get("labels"), list) else []
    clean: dict[str, dict[str, Any]] = {}
    for item in rows[-MAX_LABELS * 2:]:
        if not isinstance(item, dict):
            continue
        sample_id = str(item.get("sample_id") or "")
        rule_id = str(item.get("rule_id") or "")
        fingerprint = str(item.get("rule_fingerprint") or "")
        outcome = item.get("outcome")
        if (
            len(sample_id) != 24
            or rule_id not in RULE_ORDER
            or len(fingerprint) < 8
            or type(outcome) is not bool
            or item.get("verification_level") != "full_regression"
        ):
            continue
        clean[sample_id] = {
            "sample_id": sample_id,
            "rule_id": rule_id,
            "rule_fingerprint": fingerprint[:64],
            "path": str(item.get("path") or "")[:320],
            "stage": str(item.get("stage") or "")[:120],
            "error_family": str(item.get("error_family") or "")[:80],
            "learned_solution_reuse": item.get("learned_solution_reuse") is True,
            "learned_solution_confidence": _clip01(item.get("learned_solution_confidence")),
            "auto_repair_allowed": item.get("auto_repair_allowed") is not False,
            "outcome": outcome,
            "verification_level": "full_regression",
            "recorded_at": str(item.get("recorded_at") or "")[:64],
        }
    ordered = sorted(clean.values(), key=lambda x: (x.get("recorded_at") or "", x["sample_id"]))[-MAX_LABELS:]
    return {
        "schema": SCHEMA,
        "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None,
        "labels": ordered,
        "safety": SAFETY,
    }


def _sample_id(row: dict[str, Any]) -> str:
    parts = (
        str(row.get("rule_id") or ""),
        str(row.get("rule_fingerprint") or ""),
        str(row.get("path") or ""),
        str(row.get("stage") or ""),
        str(row.get("before_hash") or ""),
        str(row.get("after_hash") or ""),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8", "replace")).hexdigest()[:24]


def ingest_full_regression_state(
    state_path: Path,
    *,
    labels_path: Path = LABELS_PATH,
) -> dict[str, Any]:
    """Ingest repair outcomes only after the caller's full regression succeeded."""
    if not state_path.is_file() or state_path.is_symlink():
        return {
            "ok": True,
            "added": 0,
            "reason": "repair_state_missing",
            "label_count": len(_load_labels(labels_path)["labels"]),
        }
    raw = _load_json(state_path, {})
    history = raw.get("history") if isinstance(raw.get("history"), list) else []
    labels = _load_labels(labels_path)
    by_id = {row["sample_id"]: row for row in labels["labels"]}
    added = 0
    now = _now()
    for row in history[-1000:]:
        if not isinstance(row, dict):
            continue
        rule_id = str(row.get("rule_id") or "")
        fingerprint = str(row.get("rule_fingerprint") or "")
        outcome_text = str(row.get("outcome") or "")
        if rule_id not in RULE_ORDER or len(fingerprint) < 8:
            continue
        if outcome_text not in {"verified_pass", "verification_failed"}:
            continue
        if not str(row.get("before_hash") or "") or not str(row.get("after_hash") or ""):
            continue
        sample = {
            "rule_id": rule_id,
            "rule_fingerprint": fingerprint,
            "path": str(row.get("path") or "")[:320],
            "stage": str(row.get("stage") or "")[:120],
            "error_family": str(row.get("error_family") or "")[:80],
            "learned_solution_reuse": row.get("learned_solution_reuse") is True,
            "learned_solution_confidence": _clip01(row.get("learned_solution_confidence")),
            "auto_repair_allowed": row.get("auto_repair_allowed") is not False,
            "outcome": outcome_text == "verified_pass",
            "verification_level": "full_regression",
            "recorded_at": now,
            "before_hash": str(row.get("before_hash") or "")[:40],
            "after_hash": str(row.get("after_hash") or "")[:40],
        }
        sid = _sample_id(sample)
        sample["sample_id"] = sid
        sample.pop("before_hash", None)
        sample.pop("after_hash", None)
        if sid not in by_id:
            by_id[sid] = sample
            added += 1
    labels["labels"] = sorted(
        by_id.values(), key=lambda x: (x.get("recorded_at") or "", x["sample_id"])
    )[-MAX_LABELS:]
    labels["updated_at"] = now
    atomic_write_json(labels_path, labels, suffix=".verified-neural-labels.tmp")
    return {
        "ok": True,
        "added": added,
        "label_count": len(labels["labels"]),
        "reason": "full_regression_ingested",
    }


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-min(60.0, x))
        return 1.0 / (1.0 + z)
    z = math.exp(max(-60.0, x))
    return z / (1.0 + z)


def _init_model(hidden: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    scale1 = 1.0 / math.sqrt(max(1, FEATURE_COUNT))
    scale2 = 1.0 / math.sqrt(max(1, hidden))
    return {
        "hidden": hidden,
        "w1": [[rng.uniform(-scale1, scale1) for _ in range(FEATURE_COUNT)] for _ in range(hidden)],
        "b1": [0.0] * hidden,
        "w2": [rng.uniform(-scale2, scale2) for _ in range(hidden)],
        "b2": 0.0,
    }


def _predict(model: dict[str, Any], x: list[float]) -> tuple[list[float], float]:
    hidden_values = []
    for weights, bias in zip(model["w1"], model["b1"]):
        hidden_values.append(math.tanh(sum(w * v for w, v in zip(weights, x)) + bias))
    score = sum(w * h for w, h in zip(model["w2"], hidden_values)) + float(model["b2"])
    return hidden_values, _sigmoid(score)


def _train(rows: list[dict[str, Any]], hidden: int, seed: int) -> dict[str, Any]:
    model = _init_model(hidden, seed)
    data = [(_feature_vector(row), 1.0 if row["outcome"] else 0.0, row["sample_id"]) for row in rows]
    rng = random.Random(seed ^ 0x5F3759DF)
    for epoch in range(EPOCHS):
        rng.shuffle(data)
        lr = LEARNING_RATE * (0.65 + 0.35 * (1.0 - epoch / max(1, EPOCHS - 1)))
        for x, y, _sid in data:
            hidden_values, pred = _predict(model, x)
            delta_out = pred - y
            old_w2 = list(model["w2"])
            for j in range(hidden):
                model["w2"][j] -= lr * (delta_out * hidden_values[j] + L2 * model["w2"][j])
            model["b2"] -= lr * delta_out
            for j in range(hidden):
                delta_h = delta_out * old_w2[j] * (1.0 - hidden_values[j] ** 2)
                row_w = model["w1"][j]
                for k in range(FEATURE_COUNT):
                    row_w[k] -= lr * (delta_h * x[k] + L2 * row_w[k])
                model["b1"][j] -= lr * delta_h
    return model


def _calibrated_probability(model: dict[str, Any], features: list[float], *, slope: float | None = None,
                            offset: float | None = None) -> float:
    _h, raw = _predict(model, features)
    raw = max(1e-9, min(1.0 - 1e-9, raw))
    a = float(model.get("calibration_slope", 1.0) if slope is None else slope)
    b = float(model.get("calibration_offset", 0.0) if offset is None else offset)
    return _sigmoid(a * math.log(raw / (1.0 - raw)) + b)


def _metrics(model: dict[str, Any], rows: list[dict[str, Any]], *, slope: float | None = None,
             offset: float | None = None) -> dict[str, float]:
    if not rows:
        return {"accuracy": 0.0, "logloss": 99.0}
    correct = 0
    loss = 0.0
    for row in rows:
        p = _calibrated_probability(model, _feature_vector(row), slope=slope, offset=offset)
        p = max(1e-7, min(1.0 - 1e-7, p))
        y = 1.0 if row["outcome"] else 0.0
        correct += int((p >= 0.5) == bool(row["outcome"]))
        loss += -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))
    return {
        "accuracy": round(correct / len(rows), 6),
        "logloss": round(loss / len(rows), 6),
    }


def _fit_calibration(model: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[float, float]:
    if not rows:
        return 1.0, 0.0
    logits = []
    for row in rows:
        _h, raw = _predict(model, _feature_vector(row))
        raw = max(1e-9, min(1.0 - 1e-9, raw))
        logits.append((math.log(raw / (1.0 - raw)), 1.0 if row["outcome"] else 0.0))
    slope, offset = 1.0, 0.0
    for _ in range(180):
        ga = gb = 0.0
        for z, y in logits:
            error = _sigmoid(slope * z + offset) - y
            ga += error * z
            gb += error
        slope = max(0.05, min(8.0, slope - 0.04 * ga / len(logits)))
        offset = max(-8.0, min(8.0, offset - 0.04 * gb / len(logits)))
    return slope, offset


def _baseline_metrics(train: list[dict[str, Any]], holdout: list[dict[str, Any]]) -> dict[str, float]:
    rate = (sum(bool(row["outcome"]) for row in train) + 1) / (len(train) + 2)
    rate = max(1e-7, min(1.0 - 1e-7, rate))
    correct = 0
    loss = 0.0
    for row in holdout:
        y = 1.0 if row["outcome"] else 0.0
        correct += int((rate >= 0.5) == bool(row["outcome"]))
        loss += -(y * math.log(rate) + (1.0 - y) * math.log(1.0 - rate))
    return {
        "positive_rate": round(rate, 6),
        "accuracy": round(correct / max(1, len(holdout)), 6),
        "logloss": round(loss / max(1, len(holdout)), 6),
    }


def _split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]],
                                                 list[dict[str, Any]], list[dict[str, Any]]]:
    """Chronological train/tune/calibration/final-test split."""
    ordered = sorted(rows, key=lambda row: (str(row.get("recorded_at") or ""), str(row.get("sample_id") or "")))
    n = len(ordered)
    a, b, d = int(n * 0.50), int(n * 0.65), int(n * 0.80)
    return ordered[:a], ordered[a:b], ordered[b:d], ordered[d:]


def train_if_ready(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
    report_path: Path = REPORT_PATH,
    current_rule_fingerprints: dict[str, str] | None = None,
) -> dict[str, Any]:
    all_labels = _load_labels(labels_path)["labels"]
    fingerprints = dict(sorted((current_rule_fingerprints or {}).items()))
    labels = [
        row for row in all_labels
        if fingerprints.get(str(row.get("rule_id") or "")) == str(row.get("rule_fingerprint") or "")
    ] if fingerprints else []
    positives = sum(bool(row["outcome"]) for row in labels)
    negatives = len(labels) - positives
    status: dict[str, Any] = {
        "schema": SCHEMA,
        "updated_at": _now(),
        "label_count": len(labels),
        "stored_label_count": len(all_labels),
        "stale_rule_fingerprint_labels": max(0, len(all_labels) - len(labels)),
        "positive_labels": positives,
        "negative_labels": negatives,
        "minimum_labels": MIN_INDEPENDENT_LABELS,
        "hidden_sizes": list(HIDDEN_SIZES),
        "seeds": list(SEEDS),
        "protocol_version": PROTOCOL_VERSION,
        "active": False,
        "reason": "waiting_for_independent_labels",
        "safety": SAFETY,
    }
    if len(labels) < MIN_INDEPENDENT_LABELS:
        atomic_write_json(report_path, status, suffix=".verified-neural-report.tmp")
        return status
    if positives < MIN_CLASS_LABELS or negatives < MIN_CLASS_LABELS:
        status["reason"] = "waiting_for_class_balance"
        atomic_write_json(report_path, status, suffix=".verified-neural-report.tmp")
        return status

    train_rows, tune_rows, calibration_rows, final_test = _split(labels)
    if min(len(train_rows), len(tune_rows), len(calibration_rows), len(final_test)) < 100 or len(train_rows) < 400:
        status["reason"] = "insufficient_temporal_protocol_split"
        atomic_write_json(report_path, status, suffix=".verified-neural-report.tmp")
        return status

    baseline = _baseline_metrics(train_rows, final_test)
    candidates = []
    dataset_seed = int(
        hashlib.sha256("".join(sorted(row["sample_id"] for row in labels)).encode()).hexdigest()[:8],
        16,
    )
    best_family = None
    for hidden in HIDDEN_SIZES:
        members = []
        seed_metrics = []
        for seed in SEEDS:
            actual_seed = dataset_seed ^ hidden ^ seed
            member = _train(train_rows, hidden, actual_seed)
            metrics = _metrics(member, tune_rows)
            members.append((seed, member, metrics))
            seed_metrics.append({"seed": seed, "metrics": metrics})
        mean_logloss = sum(item[2]["logloss"] for item in members) / len(members)
        spread = max(item[2]["logloss"] for item in members) - min(item[2]["logloss"] for item in members)
        candidate = {"hidden": hidden, "seed_metrics": seed_metrics, "mean_tune_logloss": round(mean_logloss, 6),
                     "seed_logloss_range": round(spread, 6)}
        candidates.append(candidate)
        if best_family is None or (mean_logloss, hidden) < (best_family[0], best_family[1]):
            best_family = (mean_logloss, hidden, members)
    assert best_family is not None
    _family_score, selected_hidden, members = best_family
    selected_seed, best_model, tune_metrics = min(members, key=lambda item: (item[2]["logloss"], item[0]))
    slope, offset = _fit_calibration(best_model, calibration_rows)
    final_metrics = _metrics(best_model, final_test, slope=slope, offset=offset)
    best_meta = {"hidden": selected_hidden, "seed": selected_seed, "tune_metrics": tune_metrics, "metrics": final_metrics}
    gain = baseline["logloss"] - final_metrics["logloss"]
    activation_ok = (
        final_metrics["accuracy"] >= ACTIVATION_MIN_ACCURACY
        and gain >= ACTIVATION_MIN_LOGLOSS_GAIN
    )
    status.update({
        "protocol_version": PROTOCOL_VERSION,
        "seeds": list(SEEDS),
        "split_counts": {"train": len(train_rows), "tune": len(tune_rows),
                         "calibration": len(calibration_rows), "final_test": len(final_test)},
        "baseline": baseline,
        "candidates": candidates,
        "selected_hidden": best_meta["hidden"],
        "selected_seed": selected_seed,
        "selected_metrics": best_meta["metrics"],
        "logloss_gain": round(gain, 6),
        "final_test_used_for_selection": False,
        "active": activation_ok,
        "reason": "activated" if activation_ok else "holdout_gate_not_met",
    })
    if activation_ok:
        model_payload = {
            "schema": SCHEMA,
            "active": True,
            "trained_at": status["updated_at"],
            "label_count": len(labels),
            "feature_count": FEATURE_COUNT,
            "hidden": best_model["hidden"],
            "w1": best_model["w1"],
            "b1": best_model["b1"],
            "w2": best_model["w2"],
            "b2": best_model["b2"],
            "metrics": best_meta["metrics"],
            "protocol_version": PROTOCOL_VERSION,
            "selected_seed": selected_seed,
            "calibration_slope": slope,
            "calibration_offset": offset,
            "rule_fingerprints": fingerprints,
            "safety": SAFETY,
        }
        atomic_write_json(model_path, model_payload, suffix=".verified-neural-model.tmp")
    atomic_write_json(report_path, status, suffix=".verified-neural-report.tmp")
    return status


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    raw = _load_json(path, {})
    hidden = int(raw.get("hidden") or 0) if isinstance(raw, dict) else 0
    if (
        not isinstance(raw, dict)
        or raw.get("schema") != SCHEMA
        or raw.get("active") is not True
        or int(raw.get("feature_count") or 0) != FEATURE_COUNT
        or hidden not in HIDDEN_SIZES
    ):
        return None
    w1, b1, w2 = raw.get("w1"), raw.get("b1"), raw.get("w2")
    if not isinstance(w1, list) or len(w1) != hidden or not isinstance(b1, list) or len(b1) != hidden or not isinstance(w2, list) or len(w2) != hidden:
        return None
    if any(not isinstance(row, list) or len(row) != FEATURE_COUNT or not all(_finite_number(v) for v in row) for row in w1):
        return None
    if not all(_finite_number(v) for v in b1) or not all(_finite_number(v) for v in w2) or not _finite_number(raw.get("b2")):
        return None
    slope = raw.get("calibration_slope", 1.0)
    offset = raw.get("calibration_offset", 0.0)
    if not _finite_number(slope) or not 0.05 <= float(slope) <= 8.0 or not _finite_number(offset) or abs(float(offset)) > 8.0:
        return None
    metrics = raw.get("metrics")
    if not isinstance(metrics, dict) or not _finite_number(metrics.get("accuracy")) or not _finite_number(metrics.get("logloss")):
        return None
    return raw


def score_issue(
    issue: dict[str, Any],
    *,
    current_rule_fingerprints: dict[str, str] | None = None,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    rule_id = str(issue.get("auto_repair_rule") or issue.get("fix_rule") or "")
    if rule_id not in RULE_ORDER:
        return {"active": False, "score": 0.5, "reason": "rule_not_allowlisted"}
    model = _load_model(model_path)
    if model is None:
        return {"active": False, "score": 0.5, "reason": "model_inactive"}
    expected = model.get("rule_fingerprints")
    current = dict(sorted((current_rule_fingerprints or {}).items()))
    if not isinstance(expected, dict) or expected != current:
        return {"active": False, "score": 0.5, "reason": "rule_fingerprint_changed"}
    row = dict(issue)
    row["rule_id"] = rule_id
    probability = _calibrated_probability(model, _feature_vector(row))
    return {
        "active": True,
        "score": round(probability, 6),
        "reason": "verified_neural_priority",
        "neural_output_is_priority_only": True,
    }


def status(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
    current_rule_fingerprints: dict[str, str] | None = None,
) -> dict[str, Any]:
    all_labels = _load_labels(labels_path)["labels"]
    current = dict(sorted((current_rule_fingerprints or {}).items()))
    labels = [
        row for row in all_labels
        if current.get(str(row.get("rule_id") or "")) == str(row.get("rule_fingerprint") or "")
    ] if current else []
    model = _load_model(model_path)
    active = False
    reason = "model_inactive"
    if model is not None:
        expected = model.get("rule_fingerprints")
        if isinstance(expected, dict) and expected == current:
            active = True
            reason = "active"
        else:
            reason = "rule_fingerprint_changed"
    return {
        "ok": True,
        "active": active,
        "reason": reason,
        "label_count": len(labels),
        "stored_label_count": len(all_labels),
        "stale_rule_fingerprint_labels": max(0, len(all_labels) - len(labels)),
        "positive_labels": sum(bool(row["outcome"]) for row in labels),
        "negative_labels": sum(not bool(row["outcome"]) for row in labels),
        "minimum_labels": MIN_INDEPENDENT_LABELS,
        "hidden_sizes": list(HIDDEN_SIZES),
        "safety": SAFETY,
    }


def restore_from_directory(source: Path) -> dict[str, Any]:
    source = source.resolve()
    if not source.is_dir():
        return {"ok": True, "restored": [], "reason": "source_missing"}
    restored = []
    for name, target in ((LABELS_PATH.name, LABELS_PATH), (MODEL_PATH.name, MODEL_PATH)):
        candidate = source / name
        if candidate.is_file() and not candidate.is_symlink():
            raw = _load_json(candidate, {})
            if name == LABELS_PATH.name:
                temp = ROOT / (name + ".restore-source")
                atomic_write_json(temp, raw, suffix=".restore-source.tmp")
                clean = _load_labels(temp)
                temp.unlink(missing_ok=True)
                atomic_write_json(target, clean, suffix=".restore-labels.tmp")
                restored.append(name)
            elif _load_model(candidate) is not None:
                atomic_write_json(target, raw, suffix=".restore-model.tmp")
                restored.append(name)
    return {
        "ok": True,
        "restored": restored,
        "reason": "verified_state_restored" if restored else "no_verified_state",
    }


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        labels = root / "labels.json"
        model = root / "model.json"
        report = root / "report.json"
        state = root / "repair-state.json"
        state.write_text(json.dumps({
            "history": [{
                "rule_id": RULE_ORDER[0],
                "rule_fingerprint": "a" * 24,
                "path": ".github/workflows/a.yml",
                "stage": "CI_ACTION_RUNTIME_DEPRECATED",
                "outcome": "verified_pass",
                "before_hash": "1" * 20,
                "after_hash": "2" * 20,
            }]
        }), encoding="utf-8")
        first = ingest_full_regression_state(state, labels_path=labels)
        second = ingest_full_regression_state(state, labels_path=labels)
        assert first["added"] == 1 and second["added"] == 0
        waiting = train_if_ready(
            labels_path=labels,
            model_path=model,
            report_path=report,
            current_rule_fingerprints={RULE_ORDER[0]: "a" * 24},
        )
        assert waiting["active"] is False and waiting["label_count"] == 1
        fake_model = _init_model(4, 7)
        atomic_write_json(model, {
            "schema": SCHEMA,
            "active": True,
            "feature_count": FEATURE_COUNT,
            "hidden": 4,
            "w1": fake_model["w1"],
            "b1": fake_model["b1"],
            "w2": fake_model["w2"],
            "b2": fake_model["b2"],
            "rule_fingerprints": {RULE_ORDER[0]: "a" * 24},
            "safety": SAFETY,
        }, suffix=".selftest-model.tmp")
        ranked = score_issue(
            {
                "auto_repair_rule": RULE_ORDER[0],
                "path": ".github/workflows/a.yml",
                "stage": "CI_ACTION_RUNTIME_DEPRECATED",
            },
            current_rule_fingerprints={RULE_ORDER[0]: "a" * 24},
            model_path=model,
        )
        assert ranked["active"] is True and 0.0 <= ranked["score"] <= 1.0
        stale = score_issue(
            {
                "auto_repair_rule": RULE_ORDER[0],
                "path": ".github/workflows/a.yml",
                "stage": "CI_ACTION_RUNTIME_DEPRECATED",
            },
            current_rule_fingerprints={RULE_ORDER[0]: "b" * 24},
            model_path=model,
        )
        assert stale["active"] is False
    assert SAFETY["learned_text_executable"] is False
    assert SAFETY["source_patch_generation"] is False
    assert HIDDEN_SIZES == (4, 8, 12)
    assert MIN_INDEPENDENT_LABELS == 1000
    print("verified neural SELFREFINE: PASS")


def _rule_fingerprints() -> dict[str, str]:
    try:
        import verified_code_repair_rules as rules
        return {rule_id: rules.rule_fingerprint(rule_id) for rule_id in rules.ALL_RULE_IDS}
    except (ImportError, ValueError, TypeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--ingest-full-regression")
    parser.add_argument("--restore-from")
    args = parser.parse_args()
    fingerprints = _rule_fingerprints()
    if args.self_test:
        self_test()
        return 0
    if args.restore_from:
        print(json.dumps(restore_from_directory(Path(args.restore_from)), ensure_ascii=False, sort_keys=True))
        return 0
    if args.ingest_full_regression:
        ingest = ingest_full_regression_state(Path(args.ingest_full_regression))
        training = train_if_ready(current_rule_fingerprints=fingerprints)
        print(json.dumps({"ingest": ingest, "training": training}, ensure_ascii=False, sort_keys=True))
        return 0
    result = status(current_rule_fingerprints=fingerprints)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
