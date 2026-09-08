#!/usr/bin/env python3
"""Verified neural ranking for whole collection-job scheduling.

This model learns operational collection reliability, never factual truth.
It observes only completed, postflight-verified collection job outcomes and may
only influence the order in which already-mandatory collectors are started.
No collector is skipped, disabled, trusted, or promoted by neural output.

Eligible jobs:
- releases
- market watch
- market prices
- promo/events
- purchase sources
- exchange rates
- graded-photo candidates
- integrated discovery
- link audit

Activation is fail-closed:
- >= 1,000 independent six-hour-window observations
- >= 100 positive and >= 100 negative labels
- hidden sizes 4, 8, 12 compared on deterministic holdout
- holdout accuracy and log-loss must beat the baseline gate
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

from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text

ROOT = Path(__file__).resolve().parent
LABELS_PATH = ROOT / "VERIFIED_COLLECTION_JOB_NEURAL_LABELS.json"
LABELS_BACKUP_PATH = ROOT / "VERIFIED_COLLECTION_JOB_NEURAL_LABELS.json.bak"
MODEL_PATH = ROOT / "VERIFIED_COLLECTION_JOB_NEURAL_MODEL.json"
MODEL_BACKUP_PATH = ROOT / "VERIFIED_COLLECTION_JOB_NEURAL_MODEL.json.bak"
REPORT_PATH = ROOT / "VERIFIED_COLLECTION_JOB_NEURAL_REPORT.json"

SCHEMA = 1
RUNTIME_PATCH = 212
MIN_INDEPENDENT_LABELS = 1000
MIN_CLASS_LABELS = 100
MAX_LABELS = 8000
HIDDEN_SIZES = (4, 8, 12)
EPOCHS = 56
LEARNING_RATE = 0.032
L2 = 0.0005
RETRAIN_LABEL_DELTA = 100
ACTIVATION_MIN_ACCURACY = 0.60
ACTIVATION_MIN_LOGLOSS_GAIN = 0.01

JOB_KEYS = (
    "releases.json",
    "market_watch.json",
    "market_prices.json",
    "promo_events.json",
    "purchase_sources.json",
    "exchange_rates.json",
    "graded_photo_candidates.json",
    "__integration__",
    "__link_audit__",
)

NUMERIC_FEATURES = (
    "log_runs",
    "success_rate",
    "partial_rate",
    "recovered_rate",
    "timeout_rate",
    "failure_streak",
    "ewma_seconds",
    "planned_timeout_seconds",
)
FEATURE_SCHEMA = {"jobs": JOB_KEYS, "numeric": NUMERIC_FEATURES}
FEATURE_FINGERPRINT = hashlib.sha256(
    json.dumps(FEATURE_SCHEMA, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()[:24]
FEATURE_COUNT = len(JOB_KEYS) + len(NUMERIC_FEATURES)

SAFETY = {
    "learns_operational_strategy_not_facts": True,
    "completed_postflight_verified_outcomes_only": True,
    "minimum_independent_labels": MIN_INDEPENDENT_LABELS,
    "minimum_each_class": MIN_CLASS_LABELS,
    "hidden_sizes_compared": list(HIDDEN_SIZES),
    "collector_skip_allowed": False,
    "collector_disable_allowed": False,
    "verification_bypass": False,
    "official_trust_auto_promotion": False,
    "candidate_database_auto_promotion": False,
    "source_code_auto_rewrite": False,
    "git_write": False,
    "neural_output_is_priority_only": True,
    "all_mandatory_collectors_preserved": True,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _clip01(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 0.0)))


def _rate(numerator: Any, denominator: Any) -> float:
    den = max(1.0, _safe_float(denominator, 0.0))
    return _clip01(_safe_float(numerator, 0.0) / den)


def feature_vector(row: dict[str, Any]) -> list[float]:
    key = str(row.get("job_key") or "")
    values: list[float] = [1.0 if key == item else 0.0 for item in JOB_KEYS]
    runs = max(0.0, _safe_float(row.get("runs"), 0.0))
    successes = max(0.0, _safe_float(row.get("successes"), 0.0))
    partial = max(0.0, _safe_float(row.get("partial_successes"), 0.0))
    recovered = max(0.0, _safe_float(row.get("recovered_successes"), 0.0))
    timeouts = max(0.0, _safe_float(row.get("timeouts"), 0.0))
    failure_streak = max(0.0, _safe_float(row.get("consecutive_failures"), 0.0))
    ewma = max(0.0, _safe_float(row.get("success_ewma_seconds", row.get("ewma_seconds")), 0.0))
    planned_timeout = max(0.0, _safe_float(row.get("planned_timeout_seconds"), 0.0))
    values.extend(
        (
            min(1.0, math.log1p(runs) / math.log(2001.0)),
            _rate(successes, runs),
            _rate(partial, runs),
            _rate(recovered, runs),
            _rate(timeouts, runs),
            min(1.0, failure_streak / 10.0),
            min(1.0, ewma / 600.0),
            min(1.0, planned_timeout / 600.0),
        )
    )
    if len(values) != FEATURE_COUNT:
        raise AssertionError("collection job neural feature contract mismatch")
    return values


def _default_labels() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "updated_at": None,
        "labels": [],
        "safety": SAFETY,
    }


def _load_json(path: Path, fallback: dict[str, Any], max_bytes: int = 6_000_000) -> dict[str, Any]:
    try:
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return fallback
    return value if isinstance(value, dict) else fallback


def _backup_path(path: Path, primary: Path, backup: Path) -> Path:
    try:
        if path.resolve() == primary.resolve():
            return backup
    except OSError:
        pass
    return path.with_name(path.name + ".bak")


def _load_labels(path: Path = LABELS_PATH) -> dict[str, Any]:
    backup = _backup_path(path, LABELS_PATH, LABELS_BACKUP_PATH)
    raw = _load_json(path, {})
    if raw.get("feature_fingerprint") != FEATURE_FINGERPRINT:
        raw = _load_json(backup, _default_labels())
    if raw.get("feature_fingerprint") != FEATURE_FINGERPRINT:
        return _default_labels()
    clean: dict[str, dict[str, Any]] = {}
    rows = raw.get("labels") if isinstance(raw.get("labels"), list) else []
    for item in rows[-MAX_LABELS * 2:]:
        if not isinstance(item, dict):
            continue
        sample_id = str(item.get("sample_id") or "")
        job_key = str(item.get("job_key") or "")
        outcome = item.get("outcome")
        if len(sample_id) != 24 or job_key not in JOB_KEYS or type(outcome) is not bool:
            continue
        clean[sample_id] = {
            "sample_id": sample_id,
            "job_key": job_key,
            "runs": max(0, min(2_000_000, _safe_int(item.get("runs"), 0))),
            "successes": max(0, min(2_000_000, _safe_int(item.get("successes"), 0))),
            "partial_successes": max(0, min(2_000_000, _safe_int(item.get("partial_successes"), 0))),
            "recovered_successes": max(0, min(2_000_000, _safe_int(item.get("recovered_successes"), 0))),
            "timeouts": max(0, min(2_000_000, _safe_int(item.get("timeouts"), 0))),
            "consecutive_failures": max(0, min(1000, _safe_int(item.get("consecutive_failures"), 0))),
            "success_ewma_seconds": max(0.0, min(3600.0, _safe_float(item.get("success_ewma_seconds"), 0.0))),
            "planned_timeout_seconds": max(0.0, min(3600.0, _safe_float(item.get("planned_timeout_seconds"), 0.0))),
            "outcome": outcome,
            "evidence": str(item.get("evidence") or "")[:80],
            "observed_at": str(item.get("observed_at") or "")[:64],
        }
    ordered = sorted(clean.values(), key=lambda row: (row["observed_at"], row["sample_id"]))[-MAX_LABELS:]
    return {
        "schema": SCHEMA,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None,
        "labels": ordered,
        "safety": SAFETY,
    }


def _six_hour_slot(stamp: datetime | None = None) -> str:
    now = (stamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"{now:%Y-%m-%d}T{(now.hour // 6) * 6:02d}"


def _result_problem_details(result: dict[str, Any]) -> list[str]:
    if not isinstance(result, dict):
        return []
    key = "remaining_collection_errors" if "remaining_collection_errors" in result else "collection_errors"
    raw = result.get(key)
    if isinstance(raw, (list, tuple)):
        values = list(raw[:30])
    elif raw:
        values = [raw]
    else:
        values = []
    if not result.get("ok") and result.get("error"):
        values.append(result.get("error"))
    return [str(value)[:400] for value in values if str(value or "").strip()]


def _eligible_result(job_key: str, result: dict[str, Any]) -> bool:
    if job_key not in JOB_KEYS or not isinstance(result, dict):
        return False
    if result.get("preflight_blocked") is True:
        return False
    if _safe_int(result.get("max_attempts"), 1) == 0:
        return False
    status = str(result.get("status") or "").lower()
    if "사전검증 실패" in status or "cooldown" in status or "쿨다운" in status:
        return False
    return True


def _job_row(job_key: str, stats_row: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    details = _result_problem_details(result)
    clean = bool(result.get("ok")) and not details and not bool(result.get("recovered_after_retry")) and not bool(result.get("degraded"))
    return {
        "job_key": job_key,
        "runs": _safe_int(stats_row.get("runs"), 0),
        "successes": _safe_int(stats_row.get("successes"), 0),
        "partial_successes": _safe_int(stats_row.get("partial_successes"), 0),
        "recovered_successes": _safe_int(stats_row.get("recovered_successes"), 0),
        "timeouts": _safe_int(stats_row.get("timeouts"), 0),
        "consecutive_failures": _safe_int(stats_row.get("consecutive_failures"), 0),
        "success_ewma_seconds": _safe_float(stats_row.get("success_ewma_seconds", stats_row.get("ewma_seconds")), 0.0),
        "planned_timeout_seconds": _safe_float(result.get("adaptive_timeout_seconds"), 0.0),
        "outcome": clean,
        "evidence": "clean_verified_collection" if clean else "verified_operational_problem",
    }


def ingest_verified_report(
    report: dict[str, Any],
    stats: dict[str, Any],
    *,
    labels_path: Path = LABELS_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Learn only after postflight validation is known to be good."""
    if not isinstance(report, dict):
        return {"ok": True, "added": 0, "reason": "invalid_report"}
    postflight = report.get("postflight_monitor")
    if not isinstance(postflight, dict) or postflight.get("ok") is not True:
        return {"ok": True, "added": 0, "reason": "postflight_not_verified"}
    rows: list[tuple[str, dict[str, Any]]] = []
    for result in report.get("results") if isinstance(report.get("results"), list) else []:
        if isinstance(result, dict):
            rows.append((str(result.get("file") or ""), result))
    for key, field in (("__integration__", "integration"), ("__link_audit__", "link_audit")):
        result = report.get(field)
        if isinstance(result, dict):
            rows.append((key, result))

    try:
        with exclusive_file_lock(labels_path, timeout_seconds=3.0, stale_seconds=300):
            labels = _load_labels(labels_path)
            previous = {
                **labels,
                "labels": [dict(item) for item in labels.get("labels", []) if isinstance(item, dict)],
            }
            known = {row["sample_id"] for row in labels["labels"]}
            slot = _six_hour_slot(now)
            added = 0
            updated = 0
            eligible = 0
            stats_jobs = stats.get("jobs") if isinstance(stats.get("jobs"), dict) else {}
            observed_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")
            for job_key, result in rows:
                if not _eligible_result(job_key, result):
                    continue
                eligible += 1
                stats_row = stats_jobs.get(job_key) if isinstance(stats_jobs.get(job_key), dict) else {}
                row = _job_row(job_key, stats_row, result)
                signature = "|".join((slot, job_key))
                sample_id = hashlib.sha256(signature.encode("utf-8", "replace")).hexdigest()[:24]
                row.update({"sample_id": sample_id, "observed_at": observed_at})
                if sample_id in known:
                    for index, existing in enumerate(labels["labels"]):
                        if existing.get("sample_id") == sample_id:
                            if existing != row:
                                labels["labels"][index] = row
                                updated += 1
                            break
                    continue
                labels["labels"].append(row)
                known.add(sample_id)
                added += 1
            labels["labels"] = labels["labels"][-MAX_LABELS:]
            labels["updated_at"] = _now()
            backup_path = _backup_path(labels_path, LABELS_PATH, LABELS_BACKUP_PATH)
            if previous.get("labels"):
                atomic_write_json(backup_path, previous, suffix=".collection-job-neural-labels-bak.tmp")
            atomic_write_json(labels_path, labels, suffix=".collection-job-neural-labels.tmp")
            return {
                "ok": True,
                "added": added,
                "updated": updated,
                "eligible": eligible,
                "label_count": len(labels["labels"]),
                "reason": "postflight_verified_outcomes_ingested",
            }
    except TimeoutError:
        return {
            "ok": True,
            "added": 0,
            "updated": 0,
            "eligible": 0,
            "reason": "learning_lock_busy",
        }

def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-min(60.0, value))
        return 1.0 / (1.0 + z)
    z = math.exp(max(-60.0, value))
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


def _predict(model: dict[str, Any], features: list[float]) -> tuple[list[float], float]:
    hidden = [
        math.tanh(sum(weight * value for weight, value in zip(weights, features)) + bias)
        for weights, bias in zip(model["w1"], model["b1"])
    ]
    score = sum(weight * value for weight, value in zip(model["w2"], hidden)) + float(model["b2"])
    return hidden, _sigmoid(score)


def _train(rows: list[dict[str, Any]], hidden: int, seed: int) -> dict[str, Any]:
    model = _init_model(hidden, seed)
    data = [(feature_vector(row), 1.0 if row["outcome"] else 0.0) for row in rows]
    rng = random.Random(seed ^ 0xA5A5A5A5)
    for epoch in range(EPOCHS):
        rng.shuffle(data)
        lr = LEARNING_RATE * (0.65 + 0.35 * (1.0 - epoch / max(1, EPOCHS - 1)))
        for features, target in data:
            hidden_values, probability = _predict(model, features)
            delta_out = probability - target
            old_w2 = list(model["w2"])
            for index in range(hidden):
                model["w2"][index] -= lr * (delta_out * hidden_values[index] + L2 * model["w2"][index])
            model["b2"] -= lr * delta_out
            for index in range(hidden):
                delta_hidden = delta_out * old_w2[index] * (1.0 - hidden_values[index] ** 2)
                for feature_index in range(FEATURE_COUNT):
                    model["w1"][index][feature_index] -= lr * (
                        delta_hidden * features[feature_index] + L2 * model["w1"][index][feature_index]
                    )
                model["b1"][index] -= lr * delta_hidden
    return model


def _split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministic exact 80/20 split once the 1,000-label gate is met.

    Hash-bucket modulo splitting is deterministic but only approximate. At the
    exact activation threshold it can randomly leave fewer than 800 training
    rows, contradicting the documented 1,000-label activation contract.
    Sorting by independent sample_id and taking every fifth item gives exactly
    20% holdout (for 1,000 rows: 800 train / 200 holdout).
    """
    ordered = sorted(rows, key=lambda row: str(row.get("sample_id") or ""))
    holdout = [row for index, row in enumerate(ordered) if index % 5 == 0]
    train = [row for index, row in enumerate(ordered) if index % 5 != 0]
    return train, holdout


def _metrics(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {"accuracy": 0.0, "logloss": 99.0}
    correct = 0
    loss = 0.0
    for row in rows:
        _hidden, probability = _predict(model, feature_vector(row))
        probability = max(1e-7, min(1.0 - 1e-7, probability))
        target = 1.0 if row["outcome"] else 0.0
        correct += int((probability >= 0.5) == bool(row["outcome"]))
        loss += -(target * math.log(probability) + (1.0 - target) * math.log(1.0 - probability))
    return {"accuracy": round(correct / len(rows), 6), "logloss": round(loss / len(rows), 6)}


def _baseline(train: list[dict[str, Any]], holdout: list[dict[str, Any]]) -> dict[str, float]:
    rate = (sum(bool(row["outcome"]) for row in train) + 1) / (len(train) + 2)
    rate = max(1e-7, min(1.0 - 1e-7, rate))
    correct = 0
    loss = 0.0
    for row in holdout:
        target = 1.0 if row["outcome"] else 0.0
        correct += int((rate >= 0.5) == bool(row["outcome"]))
        loss += -(target * math.log(rate) + (1.0 - target) * math.log(1.0 - rate))
    return {
        "positive_rate": round(rate, 6),
        "accuracy": round(correct / max(1, len(holdout)), 6),
        "logloss": round(loss / max(1, len(holdout)), 6),
    }


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _validate_model_payload(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    hidden = _safe_int(raw.get("hidden"), 0)
    if (
        raw.get("schema") != SCHEMA
        or raw.get("active") is not True
        or raw.get("feature_fingerprint") != FEATURE_FINGERPRINT
        or _safe_int(raw.get("feature_count"), 0) != FEATURE_COUNT
        or hidden not in HIDDEN_SIZES
    ):
        return False
    w1, b1, w2 = raw.get("w1"), raw.get("b1"), raw.get("w2")
    if not isinstance(w1, list) or len(w1) != hidden:
        return False
    if not isinstance(b1, list) or len(b1) != hidden:
        return False
    if not isinstance(w2, list) or len(w2) != hidden:
        return False
    for row in w1:
        if not isinstance(row, list) or len(row) != FEATURE_COUNT or not all(_finite_number(v) for v in row):
            return False
    if not all(_finite_number(v) for v in b1) or not all(_finite_number(v) for v in w2):
        return False
    if not _finite_number(raw.get("b2")):
        return False
    metrics = raw.get("metrics")
    if not isinstance(metrics, dict):
        return False
    return _finite_number(metrics.get("accuracy")) and _finite_number(metrics.get("logloss"))


def _load_model_with_source(path: Path = MODEL_PATH) -> tuple[dict[str, Any] | None, str, bool]:
    primary = _load_json(path, {})
    if (
        isinstance(primary, dict)
        and primary.get("schema") == SCHEMA
        and primary.get("feature_fingerprint") == FEATURE_FINGERPRINT
        and primary.get("active") is False
    ):
        return None, "disabled", False
    if _validate_model_payload(primary):
        return primary, "primary", False
    backup = _backup_path(path, MODEL_PATH, MODEL_BACKUP_PATH)
    fallback = _load_json(backup, {})
    if _validate_model_payload(fallback):
        return fallback, "backup", True
    return None, "none", False


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    return _load_model_with_source(path)[0]


def train_if_ready(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
    report_path: Path = REPORT_PATH,
    force: bool = False,
) -> dict[str, Any]:
    labels = _load_labels(labels_path)["labels"]
    positives = sum(bool(row["outcome"]) for row in labels)
    negatives = len(labels) - positives
    existing, model_source, model_recovered = _load_model_with_source(model_path)
    existing_count = _safe_int(existing.get("label_count"), 0) if existing else 0
    status: dict[str, Any] = {
        "schema": SCHEMA,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "updated_at": _now(),
        "active": existing is not None,
        "label_count": len(labels),
        "positive_labels": positives,
        "negative_labels": negatives,
        "minimum_labels": MIN_INDEPENDENT_LABELS,
        "labels_remaining": max(0, MIN_INDEPENDENT_LABELS - len(labels)),
        "progress_percent": round(min(100.0, len(labels) * 100.0 / MIN_INDEPENDENT_LABELS), 2),
        "hidden_sizes": list(HIDDEN_SIZES),
        "labels_remaining": max(0, MIN_INDEPENDENT_LABELS - len(labels)),
        "progress_percent": round(min(100.0, len(labels) * 100.0 / MIN_INDEPENDENT_LABELS), 2),
        "model_source": model_source,
        "model_recovered_from_backup": model_recovered,
        "reason": "waiting_for_independent_labels",
        "safety": SAFETY,
    }
    if len(labels) < MIN_INDEPENDENT_LABELS:
        atomic_write_json(report_path, status, suffix=".collection-job-neural-report.tmp")
        return status
    if positives < MIN_CLASS_LABELS or negatives < MIN_CLASS_LABELS:
        status["reason"] = "waiting_for_class_balance"
        atomic_write_json(report_path, status, suffix=".collection-job-neural-report.tmp")
        return status
    if existing is not None and not force and len(labels) < existing_count + RETRAIN_LABEL_DELTA:
        status.update(
            {
                "active": True,
                "reason": "active_model_reused_until_retrain_delta",
                "selected_hidden": existing.get("hidden"),
                "selected_metrics": existing.get("metrics"),
            }
        )
        atomic_write_json(report_path, status, suffix=".collection-job-neural-report.tmp")
        return status

    train_rows, holdout = _split(labels)
    if len(train_rows) < 800 or len(holdout) < 100:
        status["reason"] = "insufficient_deterministic_holdout"
        atomic_write_json(report_path, status, suffix=".collection-job-neural-report.tmp")
        return status

    baseline = _baseline(train_rows, holdout)
    seed = int(hashlib.sha256("".join(sorted(row["sample_id"] for row in labels)).encode()).hexdigest()[:8], 16)
    candidates = []
    best: tuple[dict[str, Any], dict[str, Any]] | None = None
    for hidden in HIDDEN_SIZES:
        model = _train(train_rows, hidden, seed ^ hidden)
        metrics = _metrics(model, holdout)
        metadata = {"hidden": hidden, "metrics": metrics}
        candidates.append(metadata)
        if best is None or metrics["logloss"] < best[0]["metrics"]["logloss"]:
            best = (metadata, model)
    assert best is not None
    selected, model = best
    gain = baseline["logloss"] - selected["metrics"]["logloss"]
    active = selected["metrics"]["accuracy"] >= ACTIVATION_MIN_ACCURACY and gain >= ACTIVATION_MIN_LOGLOSS_GAIN
    status.update(
        {
            "baseline": baseline,
            "candidates": candidates,
            "selected_hidden": selected["hidden"],
            "selected_metrics": selected["metrics"],
            "logloss_gain": round(gain, 6),
            "active": active,
            "reason": "activated" if active else "holdout_gate_not_met",
        }
    )
    if active:
        payload = {
            "schema": SCHEMA,
            "active": True,
            "feature_fingerprint": FEATURE_FINGERPRINT,
            "feature_count": FEATURE_COUNT,
            "trained_at": status["updated_at"],
            "label_count": len(labels),
            "hidden": model["hidden"],
            "w1": model["w1"],
            "b1": model["b1"],
            "w2": model["w2"],
            "b2": model["b2"],
            "metrics": selected["metrics"],
            "safety": SAFETY,
        }
        model_backup = _backup_path(model_path, MODEL_PATH, MODEL_BACKUP_PATH)
        if existing is not None:
            atomic_write_json(model_backup, existing, suffix=".collection-job-neural-model-bak.tmp")
        atomic_write_json(model_path, payload, suffix=".collection-job-neural-model.tmp")
        status["model_source"] = "primary"
        status["model_recovered_from_backup"] = False
    elif existing is not None:
        existing_metrics = _metrics(existing, holdout)
        existing_gain = baseline["logloss"] - existing_metrics["logloss"]
        existing_ok = (
            existing_metrics["accuracy"] >= ACTIVATION_MIN_ACCURACY
            and existing_gain >= ACTIVATION_MIN_LOGLOSS_GAIN
        )
        status["existing_model_current_metrics"] = existing_metrics
        status["existing_model_current_logloss_gain"] = round(existing_gain, 6)
        if existing_ok:
            status.update({
                "active": True,
                "reason": "last_known_good_retained_after_retrain_reject",
                "selected_hidden": existing.get("hidden"),
                "selected_metrics": existing_metrics,
                "logloss_gain": round(existing_gain, 6),
            })
        else:
            disabled = {
                "schema": SCHEMA,
                "active": False,
                "feature_fingerprint": FEATURE_FINGERPRINT,
                "disabled_at": status["updated_at"],
                "reason": "current_holdout_gate_failed",
                "label_count": len(labels),
                "safety": SAFETY,
            }
            model_backup = _backup_path(model_path, MODEL_PATH, MODEL_BACKUP_PATH)
            atomic_write_json(model_backup, existing, suffix=".collection-job-neural-model-lkg.tmp")
            atomic_write_json(model_path, disabled, suffix=".collection-job-neural-model-disable.tmp")
            status.update({
                "active": False,
                "reason": "model_deactivated_after_current_holdout_failure",
                "model_source": "disabled",
                "model_recovered_from_backup": False,
            })
    atomic_write_json(report_path, status, suffix=".collection-job-neural-report.tmp")
    return status


def score_job(
    job_key: str,
    stats_row: dict[str, Any],
    *,
    planned_timeout_seconds: float = 0.0,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    if job_key not in JOB_KEYS:
        return {"active": False, "clean_success_probability": 0.5, "risk_priority": 0.5, "reason": "unknown_job"}
    model = _load_model(model_path)
    if model is None:
        return {
            "active": False,
            "clean_success_probability": 0.5,
            "risk_priority": 0.5,
            "reason": "model_inactive",
            "neural_output_is_priority_only": True,
        }
    row = dict(stats_row if isinstance(stats_row, dict) else {})
    row["job_key"] = job_key
    row["planned_timeout_seconds"] = planned_timeout_seconds
    _hidden, probability = _predict(model, feature_vector(row))
    probability = max(0.0, min(1.0, probability))
    return {
        "active": True,
        "clean_success_probability": round(probability, 6),
        "risk_priority": round(1.0 - probability, 6),
        "reason": "verified_job_risk_priority",
        "neural_output_is_priority_only": True,
    }


def status(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    labels = _load_labels(labels_path)["labels"]
    model, model_source, model_recovered = _load_model_with_source(model_path)
    return {
        "ok": True,
        "active": model is not None,
        "reason": "active" if model is not None else "model_inactive",
        "model_source": model_source,
        "model_recovered_from_backup": model_recovered,
        "label_count": len(labels),
        "positive_labels": sum(bool(row["outcome"]) for row in labels),
        "negative_labels": sum(not bool(row["outcome"]) for row in labels),
        "minimum_labels": MIN_INDEPENDENT_LABELS,
        "labels_remaining": max(0, MIN_INDEPENDENT_LABELS - len(labels)),
        "progress_percent": round(min(100.0, len(labels) * 100.0 / MIN_INDEPENDENT_LABELS), 2),
        "hidden_sizes": list(HIDDEN_SIZES),
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "safety": SAFETY,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = train_if_ready(force=args.force) if args.train else status()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
