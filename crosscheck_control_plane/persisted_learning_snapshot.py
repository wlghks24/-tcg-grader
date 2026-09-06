from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from shared_self_learning.contracts import PEER_LEARNING_FIELDS
from shared_self_learning.peer_learning import normalize_peer_lesson, validate_peer_snapshot_lesson

KST = dt.timezone(dt.timedelta(hours=9))


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp = Path(handle.name)
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink(missing_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("learning snapshot root must be an object")
    return value


def _existing_last_good(path: Path, namespace: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = _read_json(path)
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
    validation = value.get("validation")
    if (
        value.get("namespace") == namespace
        and value.get("snapshot_kind") == "learning"
        and value.get("status") == "finalized"
        and isinstance(value.get("lessons"), list)
        and bool(value.get("lessons"))
        and isinstance(validation, dict)
        and validation.get("write_readback_verified") is True
        and validation.get("learning_isolation_breach") is False
    ):
        return value
    return None


def build_snapshot(
    lessons: list[dict[str, Any]],
    *,
    domain: str,
    namespace: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    normalized = [normalize_peer_lesson(domain, row) for row in lessons]
    for row in normalized:
        if tuple(row) != PEER_LEARNING_FIELDS:
            raise AssertionError("peer learning field projection drifted")
    stamp = now or dt.datetime.now(KST)
    if stamp.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    stamp = stamp.astimezone(KST)
    return {
        "schema_version": "1.0",
        "namespace": namespace,
        "snapshot_kind": "learning",
        "run_date_kst": stamp.date().isoformat(),
        "status": "finalized" if normalized else "building",
        "built_at": stamp.isoformat(timespec="seconds"),
        "finalized_at": stamp.isoformat(timespec="seconds") if normalized else None,
        "lessons": normalized,
        "validation": {
            "manifest_validated": True,
            "learning_fields_only": True,
            "peer_prevention_rule_copy_count": 0,
            "raw_grading_share_count": 0,
            "write_readback_verified": False,
            "learning_isolation_breach": False,
        },
        "error_code": None if normalized else "NO_VERIFIED_LESSONS",
    }


def export_snapshot(
    lessons: list[dict[str, Any]],
    output: Path,
    *,
    domain: str,
    namespace: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    payload = build_snapshot(lessons, domain=domain, namespace=namespace, now=now)
    if payload["status"] != "finalized":
        previous = _existing_last_good(output, namespace)
        if previous is not None:
            return {
                **previous,
                "preserved_last_good": True,
                "latest_attempt_status": payload["error_code"],
            }
        _write_json_atomic(output, payload)
        return payload

    _write_json_atomic(output, payload)
    reread = _read_json(output)
    if (
        reread.get("namespace") != namespace
        or reread.get("snapshot_kind") != "learning"
        or reread.get("lessons") != payload["lessons"]
    ):
        raise RuntimeError(f"{namespace} learning snapshot write/readback mismatch")
    reread["validation"]["write_readback_verified"] = True
    _write_json_atomic(output, reread)
    return reread


def load_finalized_snapshot(
    path: Path,
    *,
    expected_namespace: str,
    domain: str,
) -> tuple[list[dict[str, Any]], str]:
    if not path.exists():
        return [], "missing"
    value = _read_json(path)
    if value.get("schema_version") != "1.0":
        raise ValueError(f"{path}: schema_version must be '1.0'")
    if value.get("namespace") != expected_namespace:
        raise ValueError(
            f"{path}: namespace mismatch; expected={expected_namespace!r} actual={value.get('namespace')!r}"
        )
    if value.get("snapshot_kind") != "learning":
        raise ValueError(f"{path}: snapshot_kind must be 'learning'")
    status = str(value.get("status") or "").strip()
    if status != "finalized":
        return [], status or "unknown"
    finalized_at = str(value.get("finalized_at") or "").strip()
    try:
        parsed = dt.datetime.fromisoformat(finalized_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{path}: invalid finalized_at") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{path}: finalized_at must be timezone-aware")

    validation = value.get("validation")
    if not isinstance(validation, dict):
        raise ValueError(f"{path}: validation object is required")
    expected_validation = {
        "manifest_validated": True,
        "learning_fields_only": True,
        "peer_prevention_rule_copy_count": 0,
        "raw_grading_share_count": 0,
        "write_readback_verified": True,
        "learning_isolation_breach": False,
    }
    mismatches = {
        key: {"expected": expected, "actual": validation.get(key)}
        for key, expected in expected_validation.items()
        if validation.get(key) != expected
    }
    if mismatches:
        raise ValueError(f"{path}: persisted learning validation mismatch: {mismatches}")

    lessons = value.get("lessons")
    if not isinstance(lessons, list) or not all(isinstance(row, dict) for row in lessons):
        raise ValueError(f"{path}: lessons must be a list of objects")
    if not lessons:
        return [], "finalized_empty"

    normalized = [validate_peer_snapshot_lesson(domain, row) for row in lessons]
    return normalized, "finalized"
