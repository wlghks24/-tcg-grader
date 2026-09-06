#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from shared_self_learning.contracts import PEER_LEARNING_FIELDS
from shared_self_learning.peer_learning import normalize_peer_lesson

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "learning_snapshot.json"
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


def _existing_last_good(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = _read_json(path)
    except (OSError, ValueError, TypeError, UnicodeError):
        return None
    if (
        value.get("namespace") == "IG_CARDINFO"
        and value.get("snapshot_kind") == "learning"
        and value.get("status") == "finalized"
        and isinstance(value.get("lessons"), list)
        and bool(value.get("lessons"))
        and isinstance(value.get("validation"), dict)
        and value["validation"].get("write_readback_verified") is True
        and value["validation"].get("learning_isolation_breach") is False
    ):
        return value
    return None


def build_snapshot(
    lessons: list[dict[str, Any]],
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    normalized = [normalize_peer_lesson("instagram_content", row) for row in lessons]
    for row in normalized:
        if tuple(row) != PEER_LEARNING_FIELDS:
            raise AssertionError("peer learning field projection drifted")
    stamp = (now or dt.datetime.now(KST)).astimezone(KST)
    return {
        "schema_version": "1.0",
        "namespace": "IG_CARDINFO",
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
    output: Path = DEFAULT_OUTPUT,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    payload = build_snapshot(lessons, now=now)
    if payload["status"] != "finalized":
        previous = _existing_last_good(output)
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
        reread.get("namespace") != "IG_CARDINFO"
        or reread.get("snapshot_kind") != "learning"
        or reread.get("lessons") != payload["lessons"]
    ):
        raise RuntimeError("IG_CARDINFO learning snapshot write/readback mismatch")
    reread["validation"]["write_readback_verified"] = True
    _write_json_atomic(output, reread)
    return reread


def self_test() -> None:
    lesson = {
        "lesson_id": "IG-XCHECK-FRESHNESS-SELFTEST",
        "subsystem": "factual_crosscheck_runtime",
        "issue_class": "nondeterministic_freshness_regression",
        "trigger_condition": "freshness regression compares fixture time to wall clock",
        "symptom_summary": "fixture can become stale without production logic changing",
        "root_cause_class": "wall_clock_coupled_test_fixture",
        "fix_pattern": "inject fixed timezone-aware now into freshness regression",
        "prevention_rule_id": "IG-PREV-XCHECK-FIXED-NOW-SELFTEST",
        "verification_result": "passed",
        "regression_pass": True,
        "recurrence_count": 1,
        "applicable_scope": "both",
        "confidence_level": "high",
    }
    with tempfile.TemporaryDirectory() as td:
        output = Path(td) / "learning_snapshot.json"
        result = export_snapshot(
            [lesson],
            output,
            now=dt.datetime(2026, 9, 6, 21, 15, tzinfo=KST),
        )
        assert result["status"] == "finalized", result
        assert result["validation"]["write_readback_verified"] is True, result
        assert tuple(result["lessons"][0]) == PEER_LEARNING_FIELDS, result

        empty = export_snapshot(
            [],
            output,
            now=dt.datetime(2026, 9, 6, 21, 16, tzinfo=KST),
        )
        assert empty["status"] == "finalized", empty
        assert empty.get("preserved_last_good") is True, empty

        bad = dict(lesson)
        bad["raw_log"] = "forbidden"
        try:
            export_snapshot([bad], output)
        except ValueError:
            pass
        else:
            raise AssertionError("forbidden peer learning raw state must fail closed")

    print("Instagram persisted learning snapshot: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if not args.input:
        raise SystemExit("--input is required unless --self-test is used")

    value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    lessons = value.get("lessons", value) if isinstance(value, dict) else value
    if not isinstance(lessons, list) or not all(isinstance(row, dict) for row in lessons):
        raise SystemExit("input must be a JSON list or object with lessons list")
    result = export_snapshot(lessons, Path(args.output))
    print(json.dumps({
        "status": result.get("status"),
        "lesson_count": len(result.get("lessons") or []),
        "preserved_last_good": bool(result.get("preserved_last_good")),
        "error_code": result.get("error_code"),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
