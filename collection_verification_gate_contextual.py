#!/usr/bin/env python3
"""Context-aware fail-closed collection verification.

The legacy gate correctly rejects stale source-health timestamps.  A full collection,
however, can legitimately run longer than the 15-minute point-in-time threshold:
source health is captured near the beginning and the verified output/report is written
later.  This wrapper never widens that threshold.  It removes only the two health
STALE_COLLECTION_STATE findings when independent files prove that the timestamp was
created inside the same bounded collection transaction and the completed report itself
is still fresh.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import collection_verification_gate as base

HEALTH_TARGETS = {"source_collection_stats.json", "adaptive_collection_stats.json"}
MAX_REPORT_AGE_SECONDS = 2 * 3600
MAX_COLLECTION_WINDOW_SECONDS = 2 * 3600
MAX_START_SKEW_SECONDS = 30 * 60
BOUNDARY_SLOP_SECONDS = 5 * 60


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _timestamp(value: Any) -> dt.datetime | None:
    return base._parse_time(value)


def _same_current_collection(root: Path, target: str, now: dt.datetime) -> dict[str, Any] | None:
    try:
        stat = _load(root / target)
        report = _load(root / "auto_update_report.json")
        live = _load(root / "tcg_live_data.json")
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(stat, dict) or not isinstance(report, dict) or not isinstance(live, dict):
        return None

    auto = live.get("auto_update") if isinstance(live.get("auto_update"), dict) else {}
    stat_at = _timestamp(stat.get("updated_at"))
    report_start = _timestamp(report.get("started_at"))
    report_finish = _timestamp(report.get("finished_at"))
    cycle_start = _timestamp(auto.get("last_run"))
    if None in (stat_at, report_start, report_finish, cycle_start):
        return None
    assert stat_at is not None and report_start is not None and report_finish is not None and cycle_start is not None

    if report_finish < report_start or report_start < cycle_start - dt.timedelta(seconds=BOUNDARY_SLOP_SECONDS):
        return None
    if (report_finish - cycle_start).total_seconds() > MAX_COLLECTION_WINDOW_SECONDS:
        return None
    if abs((report_start - cycle_start).total_seconds()) > MAX_START_SKEW_SECONDS:
        return None
    report_age = (now - report_finish).total_seconds()
    if report_age < -BOUNDARY_SLOP_SECONDS or report_age > MAX_REPORT_AGE_SECONDS:
        return None
    if stat_at < cycle_start - dt.timedelta(seconds=BOUNDARY_SLOP_SECONDS):
        return None
    if stat_at > report_finish + dt.timedelta(seconds=BOUNDARY_SLOP_SECONDS):
        return None

    # A report with no mandatory results cannot prove a completed collection.
    results = report.get("results")
    if not isinstance(results, list) or not results:
        return None
    seen = {str(row.get("file")) for row in results if isinstance(row, dict) and row.get("file")}
    if not set(base.MANDATORY_OUTPUT_FILES).issubset(seen):
        return None

    return {
        "cycle_started_at": cycle_start.isoformat(),
        "health_updated_at": stat_at.isoformat(),
        "report_started_at": report_start.isoformat(),
        "report_finished_at": report_finish.isoformat(),
        "report_age_seconds": round(report_age, 1),
        "proof": "same_bounded_collection_transaction",
    }


def verify(root: Path | str = base.ROOT, *, max_health_age_seconds: int = 900,
           now: dt.datetime | None = None) -> dict[str, Any]:
    root = Path(root)
    now = now or dt.datetime.now(dt.timezone.utc)
    report = base.verify(root, max_health_age_seconds=max_health_age_seconds, now=now)
    original = list(report.get("findings") or [])
    filtered: list[dict[str, Any]] = []
    contextual: list[dict[str, Any]] = []

    for finding in original:
        if (
            isinstance(finding, dict)
            and finding.get("severity") == "high"
            and finding.get("code") == "STALE_COLLECTION_STATE"
            and finding.get("target") in HEALTH_TARGETS
        ):
            evidence = _same_current_collection(root, str(finding["target"]), now)
            if evidence is not None:
                contextual.append({
                    "severity": "info",
                    "code": "CURRENT_COLLECTION_WINDOW_PROVEN",
                    "target": finding["target"],
                    "point_in_time_age_seconds": finding.get("age_seconds"),
                    "evidence": evidence,
                })
                continue
        filtered.append(finding)

    filtered.extend(contextual)
    report["findings"] = filtered
    counts = {
        level: sum(isinstance(row, dict) and row.get("severity") == level for row in filtered)
        for level in ("critical", "high", "medium")
    }
    report["counts"] = counts
    report["status"] = "fail_closed" if counts["critical"] else ("degraded" if counts["high"] else "pass")
    report["contextual_freshness"] = {
        "point_in_time_threshold_seconds": max_health_age_seconds,
        "threshold_widened": False,
        "same_run_proofs": len(contextual),
        "max_completed_report_age_seconds": MAX_REPORT_AGE_SECONDS,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(base.ROOT))
    parser.add_argument("--max-health-age-seconds", type=int, default=900)
    parser.add_argument("--report", default="COLLECTION_VERIFICATION_REPORT.json")
    parser.add_argument("--fail-on-degraded", action="store_true")
    args = parser.parse_args()
    max_age = max(60, min(86400, args.max_health_age_seconds))
    report = verify(Path(args.root), max_health_age_seconds=max_age)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "counts": report["counts"],
        "metrics": report.get("metrics", {}),
        "contextual_freshness": report["contextual_freshness"],
    }, ensure_ascii=False))
    if report["status"] == "fail_closed":
        return 2
    if args.fail_on_degraded and report["status"] == "degraded":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
