#!/usr/bin/env python3
"""Verified collection-strategy neural ranking.

This model learns search *strategy*, never factual truth. It may only rank
queries already produced by AdaptiveCollectionLearner. It cannot mark a source
official, promote a candidate into a database, generate search text, bypass
verification, write git, or change the reserved regional/verified-gap/exploration
slots.

Training labels come only from real completed search observations:
- positive: at least one result matched the code-defined official source policy
- negative: a successful, non-error search returned no results
- ambiguous community-only results are excluded

Identical observations are de-duplicated within the same six-hour UTC collection
window. The neural model stays inactive until at least 1,000 independent
eligible observations exist, with at least 100 labels in each class. Hidden
sizes 4, 8 and 12 are compared on a deterministic holdout set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from safe_runtime import atomic_write_json, safe_read_text

ROOT = Path(__file__).resolve().parent
LABELS_PATH = ROOT / "VERIFIED_COLLECTION_NEURAL_LABELS.json"
MODEL_PATH = ROOT / "VERIFIED_COLLECTION_NEURAL_MODEL.json"
REPORT_PATH = ROOT / "VERIFIED_COLLECTION_NEURAL_REPORT.json"

SCHEMA = 1
MIN_INDEPENDENT_LABELS = 1000
MIN_CLASS_LABELS = 100
MAX_LABELS = 6000
HIDDEN_SIZES = (4, 8, 12)
EPOCHS = 56
LEARNING_RATE = 0.032
L2 = 0.0005
RETRAIN_LABEL_DELTA = 100
ACTIVATION_MIN_ACCURACY = 0.60
ACTIVATION_MIN_LOGLOSS_GAIN = 0.01

GAMES = ("포켓몬", "원피스", "나루토")
REGIONS = ("KR", "JP", "US", "ASIA")
FAMILIES = (
    "regional",
    "official-site",
    "social",
    "topic",
    "exploration",
    "verified-gap",
    "coverage-gap",
    "learned-host",
    "other",
)

SAFETY = {
    "learns_strategy_not_facts": True,
    "verified_observed_outcomes_only": True,
    "minimum_independent_labels": MIN_INDEPENDENT_LABELS,
    "minimum_each_class": MIN_CLASS_LABELS,
    "hidden_sizes_compared": list(HIDDEN_SIZES),
    "official_trust_auto_promotion": False,
    "candidate_database_auto_promotion": False,
    "query_text_generation": False,
    "verification_bypass": False,
    "learned_text_executable": False,
    "source_code_auto_rewrite": False,
    "git_write": False,
    "neural_output_is_priority_only": True,
    "reserved_exploration_slots_unchanged": True,
}

FEATURE_SCHEMA = {
    "games": GAMES,
    "regions": REGIONS,
    "families": FAMILIES,
    "numeric": (
        "log_runs",
        "relevant_rate",
        "official_rate",
        "error_rate",
        "empty_rate",
        "learned_score",
        "verified_gap_priority",
        "coverage_gap_score",
    ),
}
FEATURE_FINGERPRINT = hashlib.sha256(
    json.dumps(FEATURE_SCHEMA, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()[:24]
FEATURE_COUNT = len(GAMES) + len(REGIONS) + len(FAMILIES) + len(FEATURE_SCHEMA["numeric"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(number):
        return default
    return number


def _clip01(value: Any) -> float:
    return max(0.0, min(1.0, _safe_float(value, 0.0)))


def _game(value: Any) -> str:
    text = str(value or "")
    low = text.lower()
    if "포켓몬" in text or "pokemon" in low or "pokémon" in low:
        return "포켓몬"
    if "원피스" in text or "one piece" in low:
        return "원피스"
    if "나루토" in text or "naruto" in low:
        return "나루토"
    return ""


def _family(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "regional":
        return "regional"
    if text == "official-site":
        return "official-site"
    if text.startswith("social:"):
        return "social"
    if text.startswith("topic:"):
        return "topic"
    if text == "exploration":
        return "exploration"
    if text.startswith("verified-gap:"):
        return "verified-gap"
    if text.startswith("coverage-gap:"):
        return "coverage-gap"
    if text == "learned-host":
        return "learned-host"
    return "other"


def _bounded_rate(numerator: Any, denominator: Any) -> float:
    den = max(1.0, _safe_float(denominator, 0.0))
    return _clip01(_safe_float(numerator, 0.0) / den)


def feature_vector(row: dict[str, Any]) -> list[float]:
    game = _game(row.get("game"))
    region = str(row.get("region") or "KR").upper()
    family = _family(row.get("family"))
    values: list[float] = [1.0 if game == item else 0.0 for item in GAMES]
    values.extend(1.0 if region == item else 0.0 for item in REGIONS)
    values.extend(1.0 if family == item else 0.0 for item in FAMILIES)

    runs = max(0.0, _safe_float(row.get("runs"), 0.0))
    hits = max(0.0, _safe_float(row.get("hits"), 0.0))
    relevant = max(0.0, _safe_float(row.get("relevant"), 0.0))
    official = max(0.0, _safe_float(row.get("official"), 0.0))
    errors = max(0.0, _safe_float(row.get("errors"), 0.0))
    empty = max(0.0, _safe_float(row.get("empty"), 0.0))
    values.extend(
        (
            min(1.0, math.log1p(runs) / math.log(1001.0)),
            _bounded_rate(relevant, hits),
            _bounded_rate(official, max(1.0, relevant)),
            _bounded_rate(errors, runs),
            _bounded_rate(empty, runs),
            max(0.0, min(1.0, (_safe_float(row.get("learned_score"), 0.0) + 5.0) / 15.0)),
            _clip01(_safe_float(row.get("verified_gap_priority"), 0.0) / 10.0),
            _clip01(_safe_float(row.get("coverage_gap_score"), 0.0) / 10.0),
        )
    )
    if len(values) != FEATURE_COUNT:
        raise AssertionError("collection neural feature contract mismatch")
    return values


def _default_labels() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "updated_at": None,
        "labels": [],
        "safety": SAFETY,
    }


def _load_json(path: Path, fallback: dict[str, Any], *, max_bytes: int = 5_000_000) -> dict[str, Any]:
    try:
        value = json.loads(safe_read_text(path, max_bytes=max_bytes))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return fallback
    return value if isinstance(value, dict) else fallback


def _load_labels(path: Path = LABELS_PATH) -> dict[str, Any]:
    raw = _load_json(path, _default_labels())
    if raw.get("feature_fingerprint") != FEATURE_FINGERPRINT:
        return _default_labels()
    clean: dict[str, dict[str, Any]] = {}
    rows = raw.get("labels") if isinstance(raw.get("labels"), list) else []
    for item in rows[-MAX_LABELS * 2 :]:
        if not isinstance(item, dict):
            continue
        sample_id = str(item.get("sample_id") or "")
        if len(sample_id) != 24 or type(item.get("outcome")) is not bool:
            continue
        game = _game(item.get("game"))
        region = str(item.get("region") or "").upper()
        if game not in GAMES or region not in REGIONS:
            continue
        clean[sample_id] = {
            "sample_id": sample_id,
            "game": game,
            "region": region,
            "family": _family(item.get("family")),
            "runs": max(0, min(1_000_000, int(_safe_float(item.get("runs"), 0)))),
            "hits": max(0, min(1_000_000, int(_safe_float(item.get("hits"), 0)))),
            "relevant": max(0, min(1_000_000, int(_safe_float(item.get("relevant"), 0)))),
            "official": max(0, min(1_000_000, int(_safe_float(item.get("official"), 0)))),
            "errors": max(0, min(1_000_000, int(_safe_float(item.get("errors"), 0)))),
            "empty": max(0, min(1_000_000, int(_safe_float(item.get("empty"), 0)))),
            "learned_score": max(-5.0, min(10.0, _safe_float(item.get("learned_score"), 0.0))),
            "verified_gap_priority": max(0.0, min(10.0, _safe_float(item.get("verified_gap_priority"), 0.0))),
            "coverage_gap_score": max(0.0, min(10.0, _safe_float(item.get("coverage_gap_score"), 0.0))),
            "outcome": item["outcome"],
            "evidence": str(item.get("evidence") or "")[:40],
            "observed_at": str(item.get("observed_at") or "")[:64],
        }
    ordered = sorted(clean.values(), key=lambda x: (x["observed_at"], x["sample_id"]))[-MAX_LABELS:]
    return {
        "schema": SCHEMA,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "updated_at": raw.get("updated_at") if isinstance(raw.get("updated_at"), str) else None,
        "labels": ordered,
        "safety": SAFETY,
    }


def _six_hour_slot(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    hour = (stamp.hour // 6) * 6
    return f"{stamp:%Y-%m-%d}T{hour:02d}"


def _result_fingerprint(rows: Iterable[dict[str, Any]]) -> str:
    values = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or row.get("source") or "")[:500]
        title = str(row.get("title") or row.get("name_ko") or "")[:160]
        if url or title:
            values.append(f"{url}|{title}")
    return hashlib.sha256("\n".join(sorted(set(values))[:50]).encode("utf-8", "replace")).hexdigest()[:16]


def observe_search_outcome(
    *,
    game: str,
    region: str,
    family: str,
    query: str,
    rows: Iterable[dict[str, Any]],
    relevant_count: int,
    official_count: int,
    error: str = "",
    query_stats: dict[str, Any] | None = None,
    verified_gap_priority: float = 0.0,
    coverage_gap_score: float = 0.0,
    labels_path: Path = LABELS_PATH,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Record one eligible real search outcome without learning factual content."""
    material = [row for row in rows if isinstance(row, dict)]
    if str(error or "").strip():
        return {"eligible": False, "added": 0, "reason": "error_observation_excluded"}
    official_count = max(0, int(official_count or 0))
    relevant_count = max(0, int(relevant_count or 0))
    if official_count > 0:
        outcome = True
        evidence = "official_result_observed"
    elif not material and relevant_count == 0:
        outcome = False
        evidence = "successful_empty_search"
    else:
        return {"eligible": False, "added": 0, "reason": "ambiguous_nonofficial_results_excluded"}

    canonical_game = _game(game)
    normalized_region = str(region or "KR").upper()
    if canonical_game not in GAMES or normalized_region not in REGIONS:
        return {"eligible": False, "added": 0, "reason": "unsupported_game_or_region"}

    stats = query_stats if isinstance(query_stats, dict) else {}
    slot = _six_hour_slot(now)
    result_fp = _result_fingerprint(material)
    sample_raw = "|".join(
        (
            slot,
            canonical_game,
            normalized_region,
            _family(family),
            str(query or "")[:320],
            result_fp,
            "1" if outcome else "0",
        )
    )
    sample_id = hashlib.sha256(sample_raw.encode("utf-8", "replace")).hexdigest()[:24]
    labels = _load_labels(labels_path)
    if any(row.get("sample_id") == sample_id for row in labels["labels"]):
        return {
            "eligible": True,
            "added": 0,
            "reason": "duplicate_same_collection_window",
            "sample_id": sample_id,
            "label_count": len(labels["labels"]),
        }

    row = {
        "sample_id": sample_id,
        "game": canonical_game,
        "region": normalized_region,
        "family": _family(family),
        "runs": int(max(0, _safe_float(stats.get("runs"), 0))),
        "hits": int(max(0, _safe_float(stats.get("hits"), 0))),
        "relevant": int(max(0, _safe_float(stats.get("relevant"), relevant_count))),
        "official": int(max(0, _safe_float(stats.get("official"), official_count))),
        "errors": int(max(0, _safe_float(stats.get("errors"), 0))),
        "empty": int(max(0, _safe_float(stats.get("empty"), 0))),
        "learned_score": max(-5.0, min(10.0, _safe_float(stats.get("learned_score"), _safe_float(stats.get("score"), 0.0)))),
        "verified_gap_priority": max(0.0, min(10.0, _safe_float(verified_gap_priority, 0.0))),
        "coverage_gap_score": max(0.0, min(10.0, _safe_float(coverage_gap_score, 0.0))),
        "outcome": outcome,
        "evidence": evidence,
        "observed_at": (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds"),
    }
    labels["labels"].append(row)
    labels["labels"] = labels["labels"][-MAX_LABELS:]
    labels["updated_at"] = _now()
    atomic_write_json(labels_path, labels, suffix=".collection-neural-labels.tmp")
    return {
        "eligible": True,
        "added": 1,
        "reason": evidence,
        "sample_id": sample_id,
        "label_count": len(labels["labels"]),
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
    hidden_values = [
        math.tanh(sum(weight * value for weight, value in zip(weights, features)) + bias)
        for weights, bias in zip(model["w1"], model["b1"])
    ]
    score = sum(weight * value for weight, value in zip(model["w2"], hidden_values)) + float(model["b2"])
    return hidden_values, _sigmoid(score)


def _train(rows: list[dict[str, Any]], hidden: int, seed: int) -> dict[str, Any]:
    model = _init_model(hidden, seed)
    data = [(feature_vector(row), 1.0 if row["outcome"] else 0.0) for row in rows]
    rng = random.Random(seed ^ 0x9E3779B9)
    for epoch in range(EPOCHS):
        rng.shuffle(data)
        lr = LEARNING_RATE * (0.65 + 0.35 * (1.0 - epoch / max(1, EPOCHS - 1)))
        for features, target in data:
            hidden_values, probability = _predict(model, features)
            delta_out = probability - target
            old_w2 = list(model["w2"])
            for index in range(hidden):
                model["w2"][index] -= lr * (
                    delta_out * hidden_values[index] + L2 * model["w2"][index]
                )
            model["b2"] -= lr * delta_out
            for index in range(hidden):
                delta_hidden = delta_out * old_w2[index] * (1.0 - hidden_values[index] ** 2)
                for feature_index in range(FEATURE_COUNT):
                    model["w1"][index][feature_index] -= lr * (
                        delta_hidden * features[feature_index] + L2 * model["w1"][index][feature_index]
                    )
                model["b1"][index] -= lr * delta_hidden
    return model


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
    return {
        "accuracy": round(correct / len(rows), 6),
        "logloss": round(loss / len(rows), 6),
    }


def _split(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train: list[dict[str, Any]] = []
    holdout: list[dict[str, Any]] = []
    for row in rows:
        bucket = int(str(row["sample_id"])[:8], 16) % 5
        (holdout if bucket == 0 else train).append(row)
    if not holdout and train:
        holdout.append(train.pop())
    return train, holdout


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


def _load_model(path: Path = MODEL_PATH) -> dict[str, Any] | None:
    raw = _load_json(path, {})
    if (
        raw.get("schema") != SCHEMA
        or raw.get("active") is not True
        or raw.get("feature_fingerprint") != FEATURE_FINGERPRINT
        or int(raw.get("feature_count") or 0) != FEATURE_COUNT
        or int(raw.get("hidden") or 0) not in HIDDEN_SIZES
        or not isinstance(raw.get("w1"), list)
        or not isinstance(raw.get("w2"), list)
    ):
        return None
    return raw


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
    existing = _load_model(model_path)
    existing_count = int(existing.get("label_count") or 0) if existing else 0
    status: dict[str, Any] = {
        "schema": SCHEMA,
        "feature_fingerprint": FEATURE_FINGERPRINT,
        "updated_at": _now(),
        "active": existing is not None,
        "label_count": len(labels),
        "positive_labels": positives,
        "negative_labels": negatives,
        "minimum_labels": MIN_INDEPENDENT_LABELS,
        "hidden_sizes": list(HIDDEN_SIZES),
        "reason": "waiting_for_independent_labels",
        "safety": SAFETY,
    }
    if len(labels) < MIN_INDEPENDENT_LABELS:
        atomic_write_json(report_path, status, suffix=".collection-neural-report.tmp")
        return status
    if positives < MIN_CLASS_LABELS or negatives < MIN_CLASS_LABELS:
        status["reason"] = "waiting_for_class_balance"
        atomic_write_json(report_path, status, suffix=".collection-neural-report.tmp")
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
        atomic_write_json(report_path, status, suffix=".collection-neural-report.tmp")
        return status

    train_rows, holdout = _split(labels)
    if len(train_rows) < 800 or len(holdout) < 100:
        status["reason"] = "insufficient_deterministic_holdout"
        atomic_write_json(report_path, status, suffix=".collection-neural-report.tmp")
        return status

    baseline = _baseline(train_rows, holdout)
    seed = int(hashlib.sha256("".join(sorted(row["sample_id"] for row in labels)).encode()).hexdigest()[:8], 16)
    candidates = []
    best: tuple[dict[str, Any], dict[str, Any]] | None = None
    for hidden in HIDDEN_SIZES:
        model = _train(train_rows, hidden, seed ^ hidden)
        metrics = _metrics(model, holdout)
        meta = {"hidden": hidden, "metrics": metrics}
        candidates.append(meta)
        if best is None or metrics["logloss"] < best[0]["metrics"]["logloss"]:
            best = (meta, model)
    assert best is not None
    selected, model = best
    gain = baseline["logloss"] - selected["metrics"]["logloss"]
    active = (
        selected["metrics"]["accuracy"] >= ACTIVATION_MIN_ACCURACY
        and gain >= ACTIVATION_MIN_LOGLOSS_GAIN
    )
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
        atomic_write_json(
            model_path,
            {
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
            },
            suffix=".collection-neural-model.tmp",
        )
    atomic_write_json(report_path, status, suffix=".collection-neural-report.tmp")
    return status


def score_query(
    row: dict[str, Any],
    *,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    model = _load_model(model_path)
    if model is None:
        return {
            "active": False,
            "score": 0.5,
            "reason": "model_inactive",
            "neural_output_is_priority_only": True,
        }
    _hidden, probability = _predict(model, feature_vector(row))
    return {
        "active": True,
        "score": round(probability, 6),
        "reason": "verified_collection_priority",
        "neural_output_is_priority_only": True,
    }


def status(
    *,
    labels_path: Path = LABELS_PATH,
    model_path: Path = MODEL_PATH,
) -> dict[str, Any]:
    labels = _load_labels(labels_path)["labels"]
    model = _load_model(model_path)
    return {
        "ok": True,
        "active": model is not None,
        "reason": "active" if model is not None else "model_inactive",
        "label_count": len(labels),
        "positive_labels": sum(bool(row["outcome"]) for row in labels),
        "negative_labels": sum(not bool(row["outcome"]) for row in labels),
        "minimum_labels": MIN_INDEPENDENT_LABELS,
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
