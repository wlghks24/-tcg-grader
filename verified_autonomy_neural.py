#!/usr/bin/env python3
"""Verified-only neural policy for bounded Tablet GPT autonomy.

The model learns which *allowlisted maintenance action* should receive priority.
It never creates facts, source trust, executable code, shell commands, file paths,
or Git operations. Training labels are accepted only after a postflight-verified
outcome. The deterministic autonomy engine remains authoritative and the neural
score can only make a bounded ranking adjustment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text

ROOT = Path(__file__).resolve().parent
LABELS_PATH = ROOT / "VERIFIED_AUTONOMY_NEURAL_LABELS.json"
LABELS_BACKUP_PATH = ROOT / "VERIFIED_AUTONOMY_NEURAL_LABELS.json.bak"
MODEL_PATH = ROOT / "VERIFIED_AUTONOMY_NEURAL_MODEL.json"
MODEL_BACKUP_PATH = ROOT / "VERIFIED_AUTONOMY_NEURAL_MODEL.json.bak"
REPORT_PATH = ROOT / "VERIFIED_AUTONOMY_NEURAL_REPORT.json"

SCHEMA = 1
PROTOCOL_VERSION = 1
MIN_INDEPENDENT_LABELS = 1000
MIN_CLASS_LABELS = 100
MAX_LABELS = 7000
HIDDEN_SIZES = (4, 8, 12)
SEEDS = (20261001, 20261011, 20261021)
EPOCHS = 48
LEARNING_RATE = 0.03
L2 = 0.0005
RETRAIN_LABEL_DELTA = 100
ACTIVATION_MIN_ACCURACY = 0.62
ACTIVATION_MIN_LOGLOSS_GAIN = 0.01
MAX_RUNTIME_MODEL_AGE_SECONDS = 30 * 24 * 60 * 60
RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS = 5 * 60

ACTIONS = (
    "refresh_market_data",
    "increase_source_exploration",
    "retrain_query_neural",
    "retrain_job_neural",
    "run_selfrefine_audit",
    "rebalance_market_priority",
    "propose_capability",
)
NUMERIC_FEATURES = (
    "data_staleness",
    "market_shift",
    "coverage_gap",
    "provider_error_rate",
    "query_model_gap",
    "job_model_gap",
    "repair_pressure",
    "tablet_sync_risk",
    "learning_backlog",
    "market_uncertainty",
)
FEATURE_SCHEMA = {"actions": ACTIONS, "numeric": NUMERIC_FEATURES}
FEATURE_FINGERPRINT = hashlib.sha256(
    json.dumps(FEATURE_SCHEMA, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()[:24]
FEATURE_COUNT = len(ACTIONS) + len(NUMERIC_FEATURES)

SAFETY = {
    "verified_outcomes_only": True,
    "minimum_independent_labels": MIN_INDEPENDENT_LABELS,
    "minimum_each_class": MIN_CLASS_LABELS,
    "hidden_sizes_compared": list(HIDDEN_SIZES),
    "neural_output_is_priority_only": True,
    "allowlisted_actions_only": True,
    "verification_bypass": False,
    "official_trust_auto_promotion": False,
    "candidate_database_auto_promotion": False,
    "source_code_auto_rewrite": False,
    "git_write": False,
    "learned_text_executable": False,
    "new_capability_auto_execution": False,
    "market_facts_generated": False,
    "mandatory_collectors_skippable": False,
    "runtime_stale_model_priority_allowed": False,
    "runtime_future_model_priority_allowed": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _clip01(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 0.0)))


def feature_vector(action: str, signals: dict[str, Any]) -> list[float]:
    if action not in ACTIONS:
        raise ValueError("unknown autonomy action")
    values = [1.0 if action == item else 0.0 for item in ACTIONS]
    values.extend(_clip01(signals.get(name, 0.0)) for name in NUMERIC_FEATURES)
    if len(values) != FEATURE_COUNT:
        raise AssertionError("autonomy neural feature contract mismatch")
    return values


def _default_labels() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "updated_at": None,
        "labels": [],
        "safety": SAFETY,
    }


def _read_json(path: Path, fallback: dict[str, Any], *, max_bytes: int = 6_000_000) -> dict[str, Any]:
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


def _sanitize_labels(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("feature_fingerprint") != FEATURE_FINGERPRINT:
        return None
    source_rows = raw.get("labels") if isinstance(raw.get("labels"), list) else []
    clean: dict[str, dict[str, Any]] = {}
    for item in source_rows[-MAX_LABELS * 2 :]:
        if not isinstance(item, dict):
            continue
        sample_id = str(item.get("sample_id") or "")
        action = str(item.get("action") or "")
        outcome = item.get("outcome")
        if len(sample_id) != 24 or action not in ACTIONS or type(outcome) is not bool:
            continue
        if item.get("verification_level") != "postflight_verified":
            continue
        signals = item.get("signals") if isinstance(item.get("signals"), dict) else {}
        clean[sample_id] = {
            "sample_id": sample_id,
            "action": action,
            "signals": {name: _clip01(signals.get(name, 0.0)) for name in NUMERIC_FEATURES},
            "outcome": outcome,
            "verification_level": "postflight_verified",
            "evidence": str(item.get("evidence") or "")[:240],
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


def _load_labels_with_source(path: Path = LABELS_PATH) -> tuple[dict[str, Any], str, bool]:
    backup = _backup_path(path, LABELS_PATH, LABELS_BACKUP_PATH)
    for candidate, source in ((path, "primary"), (backup, "backup")):
        clean = _sanitize_labels(_read_json(candidate, {}))
        if clean is not None:
            return clean, source, source == "backup"
    return _default_labels(), "empty", False


def _load_labels(path: Path = LABELS_PATH) -> dict[str, Any]:
    return _load_labels_with_source(path)[0]


def _six_hour_slot(stamp: datetime | None = None) -> str:
    now = (stamp or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return f"{now:%Y-%m-%d}T{(now.hour // 6) * 6:02d}"


def record_verified_outcome(
    action: str,
    signals: dict[str, Any],
    *,
    outcome: bool,
    evidence: str,
    verification_level: str,
    labels_path: Path = LABELS_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist one bounded learning label only after postflight verification."""
    if action not in ACTIONS:
        return {"accepted": False, "reason": "unknown_action", "added": 0}
    if type(outcome) is not bool:
        return {"accepted": False, "reason": "outcome_not_boolean", "added": 0}
    if verification_level != "postflight_verified" or not str(evidence or "").strip():
        return {"accepted": False, "reason": "unverified_outcome_rejected", "added": 0}
    vector = feature_vector(action, signals)
    fingerprint = hashlib.sha256(
        json.dumps(vector, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    material = "|".join((_six_hour_slot(now), action, fingerprint))
    sample_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
    row = {
        "sample_id": sample_id,
        "action": action,
        "signals": {name: _clip01(signals.get(name, 0.0)) for name in NUMERIC_FEATURES},
        "outcome": outcome,
        "verification_level": "postflight_verified",
        "evidence": str(evidence)[:240],
        "observed_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        with exclusive_file_lock(labels_path, timeout_seconds=3.0, stale_seconds=300):
            payload = _load_labels(labels_path)
            if any(item.get("sample_id") == sample_id for item in payload["labels"]):
                return {"accepted": True, "reason": "duplicate_same_window", "added": 0, "sample_id": sample_id}
            previous = {**payload, "labels": [dict(item) for item in payload["labels"]]}
            payload["labels"].append(row)
            payload["labels"] = payload["labels"][-MAX_LABELS:]
            payload["updated_at"] = _now()
            backup = _backup_path(labels_path, LABELS_PATH, LABELS_BACKUP_PATH)
            if previous["labels"]:
                atomic_write_json(backup, previous, suffix=".autonomy-labels-bak.tmp")
            atomic_write_json(labels_path, payload, suffix=".autonomy-labels.tmp")
            return {"accepted": True, "reason": "postflight_verified", "added": 1, "sample_id": sample_id}
    except TimeoutError:
        return {"accepted": False, "reason": "learning_lock_busy", "added": 0, "sample_id": sample_id}


def _sigmoid(value: float) -> float:
    value = max(-60.0, min(60.0, value))
    return 1.0 / (1.0 + math.exp(-value))


def _init_model(hidden: int, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    s1 = 1.0 / math.sqrt(max(1, FEATURE_COUNT))
    s2 = 1.0 / math.sqrt(max(1, hidden))
    return {
        "hidden": hidden,
        "w1": [[rng.uniform(-s1, s1) for _ in range(FEATURE_COUNT)] for _ in range(hidden)],
        "b1": [0.0] * hidden,
        "w2": [rng.uniform(-s2, s2) for _ in range(hidden)],
        "b2": 0.0,
    }


def _predict(model: dict[str, Any], features: list[float]) -> float:
    hidden = [
        math.tanh(sum(w * x for w, x in zip(weights, features)) + bias)
        for weights, bias in zip(model["w1"], model["b1"])
    ]
    return _sigmoid(sum(w * x for w, x in zip(model["w2"], hidden)) + float(model["b2"]))


def _train(rows: list[dict[str, Any]], hidden: int, seed: int) -> dict[str, Any]:
    model = _init_model(hidden, seed)
    data = [(feature_vector(row["action"], row["signals"]), 1.0 if row["outcome"] else 0.0) for row in rows]
    rng = random.Random(seed ^ 0x9E3779B9)
    for epoch in range(EPOCHS):
        rng.shuffle(data)
        lr = LEARNING_RATE * (0.7 + 0.3 * (1.0 - epoch / max(1, EPOCHS - 1)))
        for features, target in data:
            hidden_values = [
                math.tanh(sum(w * x for w, x in zip(weights, features)) + bias)
                for weights, bias in zip(model["w1"], model["b1"])
            ]
            probability = _sigmoid(sum(w * x for w, x in zip(model["w2"], hidden_values)) + float(model["b2"]))
            delta_out = probability - target
            old_w2 = list(model["w2"])
            for idx in range(hidden):
                model["w2"][idx] -= lr * (delta_out * hidden_values[idx] + L2 * model["w2"][idx])
            model["b2"] -= lr * delta_out
            for idx in range(hidden):
                delta_hidden = delta_out * old_w2[idx] * (1.0 - hidden_values[idx] ** 2)
                for fidx in range(FEATURE_COUNT):
                    model["w1"][idx][fidx] -= lr * (
                        delta_hidden * features[fidx] + L2 * model["w1"][idx][fidx]
                    )
                model["b1"][idx] -= lr * delta_hidden
    return model


def _metrics(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {"accuracy": 0.0, "logloss": 99.0}
    correct = 0
    loss = 0.0
    for row in rows:
        probability = max(1e-7, min(1.0 - 1e-7, _predict(model, feature_vector(row["action"], row["signals"]))))
        target = 1.0 if row["outcome"] else 0.0
        correct += int((probability >= 0.5) == bool(row["outcome"]))
        loss += -(target * math.log(probability) + (1.0 - target) * math.log(1.0 - probability))
    return {"accuracy": round(correct / len(rows), 6), "logloss": round(loss / len(rows), 6)}


def _baseline(train: list[dict[str, Any]], test: list[dict[str, Any]]) -> dict[str, float]:
    rate = (sum(bool(row["outcome"]) for row in train) + 1) / (len(train) + 2)
    rate = max(1e-7, min(1.0 - 1e-7, rate))
    correct = 0
    loss = 0.0
    for row in test:
        target = 1.0 if row["outcome"] else 0.0
        correct += int((rate >= 0.5) == bool(row["outcome"]))
        loss += -(target * math.log(rate) + (1.0 - target) * math.log(1.0 - rate))
    return {"accuracy": round(correct / max(1, len(test)), 6), "logloss": round(loss / max(1, len(test)), 6)}


def _finite_vector(value: object, expected: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == expected
        and all(
            isinstance(item, (int, float))
            and not isinstance(item, bool)
            and math.isfinite(float(item))
            and abs(float(item)) <= 1000.0
            for item in value
        )
    )


def _validate_model_payload(raw: object, *, require_active: bool = True) -> bool:
    if not isinstance(raw, dict):
        return False
    if raw.get("schema") != SCHEMA or raw.get("feature_fingerprint") != FEATURE_FINGERPRINT:
        return False
    if require_active and raw.get("active") is not True:
        return False
    hidden = int(raw.get("hidden", 0) or 0)
    if hidden not in HIDDEN_SIZES or int(raw.get("feature_count", 0) or 0) != FEATURE_COUNT:
        return False
    if int(raw.get("label_count", 0) or 0) < MIN_INDEPENDENT_LABELS:
        return False
    if int(raw.get("protocol_version", -1) or -1) != PROTOCOL_VERSION:
        return False
    w1 = raw.get("w1")
    if not isinstance(w1, list) or len(w1) != hidden or any(not _finite_vector(row, FEATURE_COUNT) for row in w1):
        return False
    if not _finite_vector(raw.get("b1"), hidden) or not _finite_vector(raw.get("w2"), hidden):
        return False
    b2 = raw.get("b2")
    if not isinstance(b2, (int, float)) or isinstance(b2, bool) or not math.isfinite(float(b2)):
        return False
    metrics = raw.get("metrics")
    if not isinstance(metrics, dict):
        return False
    for key in ("accuracy", "logloss"):
        value = metrics.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            return False
    return True


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    raw = _read_json(path, {})
    if _validate_model_payload(raw):
        return raw
    backup = _backup_path(path, MODEL_PATH, MODEL_BACKUP_PATH)
    raw = _read_json(backup, {})
    return raw if _validate_model_payload(raw) else None


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _runtime_model_reason(model: dict[str, Any], *, now: datetime | None = None) -> str | None:
    trained = _parse_time(model.get("trained_at"))
    if trained is None:
        return "trained_at_invalid"
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if trained > moment + timedelta(seconds=RUNTIME_FUTURE_CLOCK_TOLERANCE_SECONDS):
        return "trained_at_in_future"
    if (moment - trained).total_seconds() > MAX_RUNTIME_MODEL_AGE_SECONDS:
        return "model_stale"
    return None


def train_if_ready(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
    report_path: Path = REPORT_PATH,
    force: bool = False,
) -> dict[str, Any]:
    try:
        with exclusive_file_lock(model_path, timeout_seconds=3.0, stale_seconds=1800):
            labels = _load_labels(labels_path)["labels"]
            positives = sum(bool(row["outcome"]) for row in labels)
            negatives = len(labels) - positives
            status: dict[str, Any] = {
                "schema": SCHEMA,
                "feature_fingerprint": FEATURE_FINGERPRINT,
                "protocol_version": PROTOCOL_VERSION,
                "updated_at": _now(),
                "active": False,
                "label_count": len(labels),
                "positive_labels": positives,
                "negative_labels": negatives,
                "safety": SAFETY,
            }
            if len(labels) < MIN_INDEPENDENT_LABELS or min(positives, negatives) < MIN_CLASS_LABELS:
                status["reason"] = "insufficient_verified_labels"
                atomic_write_json(report_path, status, suffix=".autonomy-report.tmp")
                return status
            existing = _load_model(model_path)
            if existing and not force and len(labels) < int(existing.get("label_count", 0)) + RETRAIN_LABEL_DELTA:
                status.update({"active": True, "reason": "active_model_reused_until_retrain_delta",
                               "selected_hidden": existing.get("hidden"), "selected_metrics": existing.get("metrics")})
                atomic_write_json(report_path, status, suffix=".autonomy-report.tmp")
                return status
            ordered = sorted(labels, key=lambda row: (row["observed_at"], row["sample_id"]))
            cut = max(1, min(len(ordered) - 1, int(len(ordered) * 0.8)))
            train_rows, test_rows = ordered[:cut], ordered[cut:]
            if len(test_rows) < 100:
                status["reason"] = "insufficient_temporal_holdout"
                atomic_write_json(report_path, status, suffix=".autonomy-report.tmp")
                return status
            baseline = _baseline(train_rows, test_rows)
            dataset_seed = int(hashlib.sha256("".join(row["sample_id"] for row in ordered).encode()).hexdigest()[:8], 16)
            candidates = []
            best = None
            for hidden in HIDDEN_SIZES:
                members = []
                for seed in SEEDS:
                    model = _train(train_rows, hidden, dataset_seed ^ hidden ^ seed)
                    metrics = _metrics(model, test_rows)
                    members.append((metrics["logloss"], seed, model, metrics))
                member = min(members, key=lambda x: (x[0], x[1]))
                candidates.append({"hidden": hidden, "seed": member[1], "metrics": member[3]})
                if best is None or (member[0], hidden) < (best[0], best[1]):
                    best = (member[0], hidden, member[1], member[2], member[3])
            assert best is not None
            _, hidden, selected_seed, model, metrics = best
            gain = baseline["logloss"] - metrics["logloss"]
            active = metrics["accuracy"] >= ACTIVATION_MIN_ACCURACY and gain >= ACTIVATION_MIN_LOGLOSS_GAIN
            status.update({"baseline": baseline, "candidates": candidates, "selected_hidden": hidden,
                           "selected_seed": selected_seed, "selected_metrics": metrics,
                           "logloss_gain": round(gain, 6)})
            if active:
                payload = {
                    "schema": SCHEMA, "active": True, "feature_fingerprint": FEATURE_FINGERPRINT,
                    "feature_count": FEATURE_COUNT, "protocol_version": PROTOCOL_VERSION,
                    "trained_at": status["updated_at"], "label_count": len(labels),
                    "hidden": hidden, "w1": model["w1"], "b1": model["b1"],
                    "w2": model["w2"], "b2": model["b2"], "metrics": metrics,
                    "selected_seed": selected_seed, "safety": SAFETY,
                }
                backup = _backup_path(model_path, MODEL_PATH, MODEL_BACKUP_PATH)
                if existing:
                    atomic_write_json(backup, existing, suffix=".autonomy-model-bak.tmp")
                atomic_write_json(model_path, payload, suffix=".autonomy-model.tmp")
                status.update({"active": True, "reason": "activated"})
            elif existing:
                status.update({"active": True, "reason": "last_known_good_retained_after_retrain_reject",
                               "selected_hidden": existing.get("hidden"), "selected_metrics": existing.get("metrics")})
            else:
                status["reason"] = "holdout_gate_not_met"
            atomic_write_json(report_path, status, suffix=".autonomy-report.tmp")
            return status
    except TimeoutError:
        return {"schema": SCHEMA, "active": False, "reason": "training_lock_busy", "safety": SAFETY}


def score_action(
    action: str,
    signals: dict[str, Any],
    *,
    model_path: Path = MODEL_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    if action not in ACTIONS:
        return {"active": False, "score": 0.5, "reason": "unknown_action",
                "neural_output_is_priority_only": True}
    model = _load_model(model_path)
    if model is None:
        return {"active": False, "score": 0.5, "reason": "model_inactive",
                "neural_output_is_priority_only": True}
    reason = _runtime_model_reason(model, now=now)
    if reason:
        return {"active": False, "score": 0.5, "reason": reason,
                "neural_output_is_priority_only": True}
    return {"active": True, "score": round(_predict(model, feature_vector(action, signals)), 6),
            "reason": "verified_autonomy_priority", "neural_output_is_priority_only": True}


def status(*, labels_path: Path = LABELS_PATH, model_path: Path = MODEL_PATH) -> dict[str, Any]:
    payload, label_source, recovered = _load_labels_with_source(labels_path)
    labels = payload["labels"]
    positives = sum(bool(row["outcome"]) for row in labels)
    negatives = len(labels) - positives
    model = _load_model(model_path)
    runtime_reason = _runtime_model_reason(model) if model else None
    active = model is not None and runtime_reason is None
    return {
        "ok": True, "active": active, "reason": "active" if active else (runtime_reason or "model_inactive"),
        "label_count": len(labels), "positive_labels": positives, "negative_labels": negatives,
        "minimum_labels": MIN_INDEPENDENT_LABELS,
        "labels_remaining": max(0, MIN_INDEPENDENT_LABELS - len(labels)),
        "progress_percent": round(min(100.0, len(labels) * 100.0 / MIN_INDEPENDENT_LABELS), 2),
        "label_source": label_source, "label_recovered_from_backup": recovered,
        "selected_hidden": model.get("hidden") if model else None,
        "selected_metrics": model.get("metrics") if model else None,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "scope": "bounded_tablet_autonomy_priority_only", "safety": SAFETY,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = train_if_ready(force=args.force) if args.train else status()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
