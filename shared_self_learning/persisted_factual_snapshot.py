from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json
from shared_self_learning.contracts import (
    CANONICAL_FACTUAL_TYPES,
    assert_passive_exchange_payload,
    canonicalize_factual_type,
)

KST = dt.timezone(dt.timedelta(hours=9))
DEFAULT_MAX_AGE_HOURS = 36.0
ALLOWED_OUTPUT_FIELDS = {
    "canonical_key", "fact_type", "lineage_key", "identity", "value",
    "value_type", "currency", "region", "language", "condition",
    "grade_company", "grade", "effective_date", "observed_at",
    "source_role", "source_locator", "verification_status",
}


def load_input_records(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    records = value.get("records", value) if isinstance(value, dict) else value
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise ValueError("input must be a JSON list or object with records list")
    return records


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _aware_utc(value: object, *, label: str) -> dt.datetime:
    text = _clean(value)
    if not text:
        raise ValueError(f"{label}: timezone-aware timestamp is required")
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}: invalid ISO-8601 timestamp {text!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label}: timestamp must be timezone-aware")
    return parsed.astimezone(dt.timezone.utc)


def _current_utc(now: dt.datetime | None) -> dt.datetime:
    if now is None:
        return dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(dt.timezone.utc)


def _age_hours(stamp: dt.datetime, now: dt.datetime) -> float:
    return (now - stamp).total_seconds() / 3600.0


def _normalize_verified_fact(
    row: dict[str, Any],
    *,
    default_source_role: str,
) -> dict[str, Any] | None:
    verification = _clean(row.get("verification") or row.get("verification_status")).lower()
    if verification != "verified":
        return None

    raw_type = row.get("information_family") or row.get("fact_type")
    fact_type = canonicalize_factual_type(raw_type)
    canonical_key = _clean(row.get("canonical_key"))
    lineage_key = _clean(row.get("lineage_key"))
    source_locator = _clean(row.get("source_locator"))
    observed_at = _clean(row.get("checked_at_kst") or row.get("observed_at"))
    if not all((canonical_key, lineage_key, source_locator, observed_at)):
        raise ValueError("verified factual row is missing canonical/provenance fields")
    _aware_utc(observed_at, label="observed_at")

    fact = {
        "canonical_key": canonical_key,
        "fact_type": fact_type,
        "lineage_key": lineage_key,
        "identity": row.get("identity") or canonical_key,
        "value": row.get("value"),
        "value_type": _clean(row.get("value_type") or "text"),
        "currency": _clean(row.get("currency")),
        "region": _clean(row.get("region")),
        "language": _clean(row.get("language")),
        "condition": _clean(row.get("condition")),
        "grade_company": _clean(row.get("grade_company")),
        "grade": _clean(row.get("grade")),
        "effective_date": _clean(row.get("effective_date")),
        "observed_at": observed_at,
        "source_role": _clean(row.get("source_role") or row.get("source_code") or default_source_role),
        "source_locator": source_locator,
        "verification_status": "verified",
    }
    return {key: value for key, value in fact.items() if key in ALLOWED_OUTPUT_FIELDS}


def build_snapshot(
    records: list[dict[str, Any]],
    *,
    namespace: str,
    default_source_role: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    stamp = now or dt.datetime.now(KST)
    if stamp.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    facts: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in records:
        fact = _normalize_verified_fact(row, default_source_role=default_source_role)
        if fact is None:
            continue
        key = (fact["canonical_key"], fact["fact_type"], fact["lineage_key"])
        prior = seen.get(key)
        if prior is not None:
            if prior != fact:
                raise ValueError(f"local persisted factual conflict for {key}")
            continue
        seen[key] = fact
        facts.append(fact)

    finalized = bool(facts)
    local = stamp.astimezone(KST)
    return {
        "schema_version": "1.0",
        "namespace": namespace,
        "snapshot_kind": "factual",
        "run_date_kst": local.date().isoformat(),
        "status": "finalized" if finalized else "building",
        "built_at": local.isoformat(timespec="seconds"),
        "finalized_at": local.isoformat(timespec="seconds") if finalized else None,
        "facts": facts,
        "validation": {
            "manifest_validated": True,
            "allowed_fields_only": True,
            "exact_factual_types_enforced": True,
            "write_readback_verified": False,
            "isolation_breach": False,
        },
        "error_code": None if finalized else "NO_VERIFIED_FACTS",
    }


def export_snapshot(
    records: list[dict[str, Any]],
    output: Path,
    *,
    namespace: str,
    default_source_role: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    payload = build_snapshot(
        records,
        namespace=namespace,
        default_source_role=default_source_role,
        now=now,
    )
    atomic_write_json(output, payload, suffix=f".{namespace.lower()}-persisted.tmp")
    reread = json.loads(output.read_text(encoding="utf-8"))
    if reread.get("namespace") != namespace or reread.get("facts") != payload.get("facts"):
        raise RuntimeError(f"{namespace} snapshot write/readback mismatch")
    reread["validation"]["write_readback_verified"] = True
    atomic_write_json(output, reread, suffix=f".{namespace.lower()}-persisted.tmp")
    return reread


def load_finalized_snapshot(
    path: Path,
    *,
    expected_namespace: str,
    now: dt.datetime | None = None,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    current = _current_utc(now)
    if not path.exists():
        return [], {"available": False, "reason": "missing", "namespace": expected_namespace}

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: persisted snapshot root must be an object")
    assert_passive_exchange_payload(payload)
    if str(payload.get("schema_version") or "") != "1.0":
        raise ValueError(f"{path}: schema_version must be '1.0'")
    if payload.get("namespace") != expected_namespace:
        raise ValueError(
            f"{path}: namespace mismatch: expected {expected_namespace!r}, got {payload.get('namespace')!r}"
        )
    if payload.get("snapshot_kind") != "factual":
        raise ValueError(f"{path}: snapshot_kind must be factual")

    status = _clean(payload.get("status"))
    if status != "finalized":
        return [], {
            "available": False,
            "reason": "not_finalized",
            "status": status or "missing",
            "namespace": expected_namespace,
        }

    finalized_at = _aware_utc(payload.get("finalized_at"), label=f"{path}:finalized_at")
    snapshot_age = _age_hours(finalized_at, current)
    if snapshot_age < -(5.0 / 60.0):
        raise ValueError(f"{path}: finalized_at is more than 5 minutes in the future")
    if snapshot_age > max_age_hours:
        return [], {
            "available": False,
            "reason": "stale_snapshot",
            "snapshot_age_hours": round(snapshot_age, 3),
            "namespace": expected_namespace,
        }

    validation = payload.get("validation")
    if not isinstance(validation, dict):
        raise ValueError(f"{path}: validation object is required")
    required_true = (
        "manifest_validated",
        "allowed_fields_only",
        "exact_factual_types_enforced",
        "write_readback_verified",
    )
    failed = [key for key in required_true if validation.get(key) is not True]
    if failed:
        raise ValueError(f"{path}: persisted validation flags are not PASS: {failed}")
    if validation.get("isolation_breach") is True:
        raise ValueError(f"{path}: isolation_breach=true")

    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list) or not all(isinstance(row, dict) for row in raw_facts):
        raise ValueError(f"{path}: facts must be a list of objects")
    if not raw_facts:
        return [], {
            "available": False,
            "reason": "empty_facts",
            "snapshot_age_hours": round(snapshot_age, 3),
            "namespace": expected_namespace,
        }

    fresh: list[dict[str, Any]] = []
    stale_count = 0
    seen: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, fact in enumerate(raw_facts):
        extra = sorted(set(fact) - ALLOWED_OUTPUT_FIELDS)
        if extra:
            raise ValueError(f"{path}: facts[{index}] has unknown fields: {extra}")
        factual_type = canonicalize_factual_type(fact.get("fact_type"), label=f"{path}:facts[{index}].fact_type")
        if factual_type not in CANONICAL_FACTUAL_TYPES:
            raise ValueError(f"{path}: facts[{index}] unsupported factual type")
        if _clean(fact.get("verification_status")).lower() != "verified":
            raise ValueError(f"{path}: finalized facts[{index}] must be verified")

        canonical_key = _clean(fact.get("canonical_key"))
        lineage_key = _clean(fact.get("lineage_key"))
        source_locator = _clean(fact.get("source_locator"))
        observed_text = _clean(fact.get("observed_at"))
        if not all((canonical_key, lineage_key, source_locator, observed_text)):
            raise ValueError(f"{path}: facts[{index}] missing canonical/provenance fields")
        observed = _aware_utc(observed_text, label=f"{path}:facts[{index}].observed_at")
        observed_age = _age_hours(observed, current)
        if observed_age < -(5.0 / 60.0):
            raise ValueError(f"{path}: facts[{index}].observed_at is in the future")
        if observed_age > max_age_hours:
            stale_count += 1
            continue

        normalized = dict(fact)
        normalized["fact_type"] = factual_type
        key = (canonical_key, factual_type, lineage_key)
        prior = seen.get(key)
        if prior is not None and prior != normalized:
            raise ValueError(f"{path}: local finalized factual conflict for {key}")
        if prior is None:
            seen[key] = normalized
            fresh.append(normalized)

    if not fresh:
        return [], {
            "available": False,
            "reason": "no_fresh_verified_facts",
            "stale_facts": stale_count,
            "snapshot_age_hours": round(snapshot_age, 3),
            "namespace": expected_namespace,
        }
    return fresh, {
        "available": True,
        "reason": "ready",
        "records": len(fresh),
        "stale_facts": stale_count,
        "snapshot_age_hours": round(snapshot_age, 3),
        "finalized_at": finalized_at.isoformat(),
        "namespace": expected_namespace,
    }
