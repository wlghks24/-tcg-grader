#!/usr/bin/env python3
"""Fail-closed operational guard for persisted Main ↔ Instagram factual crosscheck.

This does not fabricate missing snapshots. It runs the existing neutral bridge,
checks that both persisted domains are finalized with real rows, and verifies
that a crosschecked report was produced. Missing inputs remain SNAPSHOT_UNAVAILABLE.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from crosscheck_runtime_bridge import DEFAULT_REPORT, run_from_persisted


def evaluate(*, report: Path = DEFAULT_REPORT) -> tuple[int, dict]:
    result = run_from_persisted(report_output=report)
    ready = (
        result.get("engine_available") is True
        and result.get("operational_ready") is True
        and result.get("status") == "crosschecked"
        and int(result.get("main_records") or 0) > 0
        and int(result.get("instagram_records") or 0) > 0
    )
    payload = {
        "crosscheck_engine_available": bool(result.get("engine_available")),
        "crosscheck_operational_ready": bool(result.get("operational_ready")),
        "status": result.get("status"),
        "error_code": None if ready else "SNAPSHOT_UNAVAILABLE",
        "persisted_main_status": result.get("persisted_main_status"),
        "persisted_instagram_status": result.get("persisted_instagram_status"),
        "main_records": int(result.get("main_records") or 0),
        "instagram_records": int(result.get("instagram_records") or 0),
        "agree": int(result.get("agree") or 0),
        "conflict": int(result.get("conflict") or 0),
        "reverification_required": int(result.get("reverification_required") or 0),
    }
    return (0 if ready else 2, payload)


def self_test() -> None:
    # The bridge owns detailed positive/conflict/missing regressions. This guard
    # asserts only its strict readiness predicate, without creating fake runtime data.
    good = {
        "engine_available": True,
        "operational_ready": True,
        "status": "crosschecked",
        "main_records": 1,
        "instagram_records": 1,
    }
    bad = {**good, "instagram_records": 0, "operational_ready": False, "status": "snapshot_missing"}
    def is_ready(r: dict) -> bool:
        return (
            r.get("engine_available") is True
            and r.get("operational_ready") is True
            and r.get("status") == "crosschecked"
            and int(r.get("main_records") or 0) > 0
            and int(r.get("instagram_records") or 0) > 0
        )
    assert is_ready(good)
    assert not is_ready(bad)
    print("Crosscheck operational guard: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--soft", action="store_true", help="report degraded state without non-zero exit")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    code, payload = evaluate(report=Path(args.report))
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if args.soft else code


if __name__ == "__main__":
    raise SystemExit(main())
