#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import tempfile
from pathlib import Path
from typing import Any

from crosscheck_control_plane.persisted_learning_snapshot import export_snapshot as export_shared_snapshot

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "TCG_CROSSCHECK" / "MARKET_ANALYSIS" / "learning_snapshot.json"
KST = dt.timezone(dt.timedelta(hours=9))


def export_snapshot(
    lessons: list[dict[str, Any]],
    output: Path = DEFAULT_OUTPUT,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    return export_shared_snapshot(
        lessons,
        output,
        domain="main",
        namespace="MARKET_ANALYSIS",
        now=now,
    )


def self_test() -> None:
    lesson = {
        "lesson_id": "MAIN-XCHECK-FRESHNESS-SELFTEST",
        "subsystem": "factual_crosscheck_runtime",
        "issue_class": "nondeterministic_freshness_regression",
        "trigger_condition": "persisted snapshot freshness regression compares historical fixture timestamps against wall-clock now",
        "symptom_summary": "a valid regression fixture can become stale while production logic is unchanged",
        "root_cause_class": "wall_clock_coupled_test_fixture",
        "fix_pattern": "inject a fixed timezone-aware now into freshness regression tests while keeping the production 36-hour stale-evidence gate unchanged",
        "prevention_rule_id": "MAIN-PREV-XCHECK-FIXED-NOW-SELFTEST",
        "verification_result": "passed",
        "regression_pass": True,
        "recurrence_count": 1,
        "applicable_scope": "both",
        "confidence_level": "high",
    }
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "learning_snapshot.json"
        result = export_snapshot(
            [lesson],
            path,
            now=dt.datetime(2026, 9, 6, 21, 30, tzinfo=KST),
        )
        assert result["status"] == "finalized", result
        assert result["validation"]["write_readback_verified"] is True, result
        empty = export_snapshot(
            [],
            path,
            now=dt.datetime(2026, 9, 6, 21, 31, tzinfo=KST),
        )
        assert empty["status"] == "finalized", empty
        assert empty.get("preserved_last_good") is True, empty
    print("Main persisted learning snapshot: PASS")


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
