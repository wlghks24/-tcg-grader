#!/usr/bin/env python3
"""Runtime integrity/freshness guard for priority-only collection AI models.

The collection neural models are intentionally advisory: they may reorder already
allowed work but may not create facts, trust sources, skip mandatory collectors,
or bypass verification. This guard keeps that boundary observable at runtime.

It validates only model/report metadata and weights. It never retrains a model,
changes a score, writes learning state, or disables the non-AI collection path.
A stale/broken AI artifact therefore degrades the advisory AI surface while the
verified deterministic pipeline remains available.
"""
from __future__ import annotations

import importlib
import json
import math
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from safe_runtime import safe_read_text

ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = 1
MAX_ACTIVE_MODEL_AGE_SECONDS = 30 * 24 * 60 * 60
FUTURE_CLOCK_TOLERANCE_SECONDS = 5 * 60
MAX_JSON_BYTES = 3_000_000
MODEL_SPECS = (
    ("query_strategy", "verified_collection_neural"),
    ("job_strategy", "verified_collection_job_neural"),
)

_CACHE_LOCK = threading.Lock()
_CACHE_SIGNATURE: tuple[Any, ...] | None = None
_CACHE_VALUE: dict[str, Any] | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = safe_read_text(path, max_bytes=MAX_JSON_BYTES)
        value = json.loads(raw)
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _stat_signature(path: Path) -> tuple[str, int, int, bool]:
    try:
        stat = path.stat()
        return (str(path), int(stat.st_mtime_ns), int(stat.st_size), path.is_file() and not path.is_symlink())
    except OSError:
        return (str(path), -1, -1, False)


def _finite_tree(value: Any, *, max_nodes: int = 200_000) -> bool:
    stack = [value]
    seen = 0
    while stack:
        item = stack.pop()
        seen += 1
        if seen > max_nodes:
            return False
        if isinstance(item, bool) or item is None or isinstance(item, str):
            continue
        if isinstance(item, (int, float)):
            if not math.isfinite(float(item)):
                return False
            continue
        if isinstance(item, dict):
            stack.extend(item.values())
            continue
        if isinstance(item, (list, tuple)):
            stack.extend(item)
            continue
        return False
    return True


def _metric(value: Any, *, low: float, high: float) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not low <= number <= high:
        return None
    return number


def _safety_contract(module: Any) -> list[str]:
    safety = getattr(module, "SAFETY", {})
    if not isinstance(safety, dict):
        return ["safety_contract_missing"]
    issues: list[str] = []
    if safety.get("neural_output_is_priority_only") is not True:
        issues.append("safety_true_missing:neural_output_is_priority_only")
    for key in (
        "verification_bypass",
        "official_trust_auto_promotion",
        "candidate_database_auto_promotion",
        "source_code_auto_rewrite",
        "git_write",
    ):
        if key in safety and safety.get(key) is not False:
            issues.append(f"safety_false_missing:{key}")
    return issues


def inspect_module(module: Any, name: str, *, now: datetime | None = None) -> dict[str, Any]:
    moment = (now or _utc_now()).astimezone(timezone.utc)
    model_path = Path(getattr(module, "MODEL_PATH", ROOT / f"{name}.model.json"))
    report_path = Path(getattr(module, "REPORT_PATH", ROOT / f"{name}.report.json"))
    report = _read_json(report_path) if report_path.is_file() and not report_path.is_symlink() else None
    report_active = bool(isinstance(report, dict) and report.get("active") is True)

    base: dict[str, Any] = {
        "name": name,
        "module": str(getattr(module, "__name__", "")),
        "model_present": model_path.is_file() and not model_path.is_symlink(),
        "report_present": report_path.is_file() and not report_path.is_symlink(),
        "active": False,
        "healthy": True,
        "requires_attention": False,
        "status": "inactive",
        "reason": None,
        "model_age_seconds": None,
        "label_count": None,
        "metrics": None,
    }

    safety_issues = _safety_contract(module)
    if safety_issues:
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": safety_issues[0]})
        return base

    if not base["model_present"]:
        if report_active:
            base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "active_report_without_model"})
        else:
            base["reason"] = str(report.get("reason") if isinstance(report, dict) else "model_not_active")[:120]
        return base

    model = _read_json(model_path)
    if not isinstance(model, dict):
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "model_json_invalid"})
        return base
    if model.get("active") is not True:
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "stored_model_not_active"})
        return base
    if not _finite_tree(model):
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "model_nonfinite_or_oversized"})
        return base

    validator = getattr(module, "_validate_model_payload", None)
    if callable(validator):
        try:
            if validator(model) is not True:
                base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "module_model_validation_failed"})
                return base
        except (TypeError, ValueError, OverflowError, KeyError, IndexError):
            base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "module_model_validation_error"})
            return base

    expected_fp = getattr(module, "FEATURE_FINGERPRINT", None)
    if expected_fp is not None and model.get("feature_fingerprint") != expected_fp:
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "feature_fingerprint_mismatch"})
        return base
    expected_protocol = getattr(module, "PROTOCOL_VERSION", None)
    if expected_protocol is not None:
        try:
            protocol_ok = int(model.get("protocol_version", -1)) == int(expected_protocol)
        except (TypeError, ValueError, OverflowError):
            protocol_ok = False
        if not protocol_ok:
            base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "protocol_version_mismatch"})
            return base

    try:
        label_count = int(model.get("label_count", 0))
    except (TypeError, ValueError, OverflowError):
        label_count = -1
    minimum = int(getattr(module, "MIN_INDEPENDENT_LABELS", 0) or 0)
    if label_count < max(1, minimum):
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "label_count_below_activation_gate"})
        return base
    base["label_count"] = label_count

    metrics = model.get("metrics") if isinstance(model.get("metrics"), dict) else {}
    accuracy = _metric(metrics.get("accuracy"), low=0.0, high=1.0)
    logloss = _metric(metrics.get("logloss"), low=0.0, high=100.0)
    if accuracy is None or logloss is None:
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "invalid_model_metrics"})
        return base
    base["metrics"] = {"accuracy": round(accuracy, 6), "logloss": round(logloss, 6)}

    if "calibration_slope" in model:
        slope = _metric(model.get("calibration_slope"), low=0.05, high=8.0)
        offset = _metric(model.get("calibration_offset"), low=-8.0, high=8.0)
        if slope is None or offset is None:
            base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "invalid_calibration_parameters"})
            return base

    trained = _parse_time(model.get("trained_at"))
    if trained is None:
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "trained_at_invalid"})
        return base
    if trained > moment + timedelta(seconds=FUTURE_CLOCK_TOLERANCE_SECONDS):
        base.update({"healthy": False, "requires_attention": True, "status": "broken", "reason": "trained_at_in_future"})
        return base
    age = max(0, int((moment - trained).total_seconds()))
    base["model_age_seconds"] = age
    base["active"] = True
    if age > MAX_ACTIVE_MODEL_AGE_SECONDS:
        base.update({"healthy": True, "requires_attention": True, "status": "degraded", "reason": "active_model_stale"})
        return base

    base.update({"healthy": True, "requires_attention": False, "status": "active", "reason": None})
    return base


def _load_modules() -> tuple[list[tuple[str, Any]], list[dict[str, Any]]]:
    loaded: list[tuple[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for name, module_name in MODEL_SPECS:
        try:
            loaded.append((name, importlib.import_module(module_name)))
        except (ImportError, OSError, ValueError, TypeError) as exc:
            failures.append({
                "name": name,
                "module": module_name,
                "model_present": False,
                "report_present": False,
                "active": False,
                "healthy": False,
                "requires_attention": True,
                "status": "broken",
                "reason": f"module_import_failed:{type(exc).__name__}",
                "model_age_seconds": None,
                "label_count": None,
                "metrics": None,
            })
    return loaded, failures


def _signature(modules: list[tuple[str, Any]]) -> tuple[Any, ...]:
    parts: list[Any] = [SCHEMA_VERSION, MAX_ACTIVE_MODEL_AGE_SECONDS]
    for name, module in modules:
        parts.append(name)
        parts.append(_stat_signature(Path(getattr(module, "MODEL_PATH", ROOT / f"{name}.model.json"))))
        parts.append(_stat_signature(Path(getattr(module, "REPORT_PATH", ROOT / f"{name}.report.json"))))
    return tuple(parts)


def public_status(*, now: datetime | None = None, use_cache: bool = True) -> dict[str, Any]:
    global _CACHE_SIGNATURE, _CACHE_VALUE
    modules, failures = _load_modules()
    signature = _signature(modules)
    if use_cache and now is None:
        with _CACHE_LOCK:
            if _CACHE_SIGNATURE == signature and isinstance(_CACHE_VALUE, dict):
                cached = dict(_CACHE_VALUE)
                cached["cache_hit"] = True
                return cached

    rows = [inspect_module(module, name, now=now) for name, module in modules]
    rows.extend(failures)
    broken = [row["name"] for row in rows if row.get("status") == "broken"]
    degraded = [row["name"] for row in rows if row.get("status") == "degraded"]
    active = [row["name"] for row in rows if row.get("status") == "active"]
    if broken:
        status = "broken"
    elif degraded:
        status = "degraded"
    elif active:
        status = "active"
    else:
        status = "inactive"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "healthy": not broken,
        "requires_attention": bool(broken or degraded),
        "active_models": active,
        "degraded_models": degraded,
        "broken_models": broken,
        "models": {row["name"]: row for row in rows},
        "max_active_model_age_seconds": MAX_ACTIVE_MODEL_AGE_SECONDS,
        "cache_hit": False,
    }
    if use_cache and now is None:
        with _CACHE_LOCK:
            _CACHE_SIGNATURE = signature
            _CACHE_VALUE = dict(payload)
    return payload


def self_test() -> None:
    result = public_status(use_cache=False)
    assert result["status"] in {"inactive", "active", "degraded", "broken"}
    assert isinstance(result["models"], dict)
    assert set(result["models"]).issuperset({"query_strategy", "job_strategy"})
    print("AI runtime model guard: PASS")


if __name__ == "__main__":
    self_test()
