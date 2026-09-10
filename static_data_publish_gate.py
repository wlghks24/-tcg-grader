#!/usr/bin/env python3
"""Publish gate for scheduled GitHub Pages TCG data refreshes.

This gate does not collect data. It runs after tcg_updater.update_cycle() and blocks
publishing when a generated public snapshot is structurally invalid, the event-topic
matrix was not actually attempted, or the social candidate snapshot is stale.

Transient provider errors may remain as warnings because each collector preserves its
last verified rows. A failed collector result or an incomplete collection-attempt matrix
is still fail-closed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import auto_update_all
import update_promo_events
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
PUBLIC_OUTPUTS = (
    "releases.json",
    "market_watch.json",
    "market_prices.json",
    "promo_events.json",
    "purchase_sources.json",
    "exchange_rates.json",
    "graded_photo_candidates.json",
)
AUX_OUTPUTS = ("supplementary_candidates.json", "social_event_candidates.json")
EXPECTED_TOPIC_CELLS = len(update_promo_events.social_topic_expected_keys())


def _load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path.name}: {type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"invalid root object: {path.name}")
    return data


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def audit_topic_contract(promo: dict, social: dict) -> list[dict]:
    findings: list[dict] = []
    expected = int(promo.get("social_topic_expected_cells") or 0)
    attempted = int(promo.get("social_topic_attempted_cells") or 0)
    social_expected = int(social.get("topic_query_expected_cells") or 0)
    social_attempted = int(social.get("topic_query_attempted_cells") or 0)
    if expected != EXPECTED_TOPIC_CELLS:
        findings.append({"severity": "critical", "code": "TOPIC_EXPECTED_CELL_MISMATCH",
                         "expected": EXPECTED_TOPIC_CELLS, "actual": expected})
    if attempted < expected:
        findings.append({"severity": "critical", "code": "TOPIC_COLLECTION_NOT_FULLY_ATTEMPTED",
                         "expected": expected, "attempted": attempted})
    if social_expected != EXPECTED_TOPIC_CELLS or social_attempted < social_expected:
        findings.append({"severity": "critical", "code": "SOCIAL_TOPIC_ATTEMPT_CONTRACT_MISMATCH",
                         "expected": EXPECTED_TOPIC_CELLS,
                         "social_expected": social_expected, "social_attempted": social_attempted})
    failed = promo.get("social_topic_failed_cells")
    if isinstance(failed, list) and failed:
        findings.append({"severity": "warning", "code": "TOPIC_PROVIDER_FAILURES_PRESERVED",
                         "count": len(failed), "cells": failed[:20]})
    undiscovered = promo.get("social_topic_undiscovered_cells")
    if isinstance(undiscovered, list) and undiscovered:
        findings.append({"severity": "info", "code": "TOPIC_NO_LEAD_FOUND",
                         "count": len(undiscovered)})
    return findings


def verify(root: Path = ROOT, *, now: dt.datetime | None = None,
           max_social_age_hours: float = 12.0,
           max_report_age_hours: float = 2.0) -> dict:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    findings: list[dict] = []

    for filename in PUBLIC_OUTPUTS:
        path = root / filename
        try:
            payload = _load(path)
            auto_update_all.validate_json(filename, payload)
        except (OSError, ValueError, TypeError) as exc:
            findings.append({"severity": "critical", "code": "INVALID_PUBLIC_OUTPUT",
                             "target": filename, "error": f"{type(exc).__name__}: {exc}"})

    for filename in AUX_OUTPUTS:
        try:
            payload = _load(root / filename)
        except ValueError as exc:
            findings.append({"severity": "critical", "code": "INVALID_AUX_OUTPUT",
                             "target": filename, "error": str(exc)})
            continue
        if not isinstance(payload.get("items"), list):
            findings.append({"severity": "critical", "code": "INVALID_AUX_ITEMS",
                             "target": filename})

    try:
        releases = _load(root / "releases.json")
        if int(releases.get("archive_grace_days") or -1) != 5:
            findings.append({"severity": "critical", "code": "RELEASE_ARCHIVE_POLICY_MISMATCH"})
    except ValueError:
        releases = {}

    try:
        promo = _load(root / "promo_events.json")
        if int(promo.get("archive_grace_days") or -1) != 5:
            findings.append({"severity": "critical", "code": "EVENT_ARCHIVE_POLICY_MISMATCH"})
    except ValueError:
        promo = {}

    try:
        social = _load(root / "social_event_candidates.json")
    except ValueError:
        social = {}

    if promo and social:
        findings.extend(audit_topic_contract(promo, social))
        source_stamp = _parse_time(promo.get("social_topic_source_updated_at"))
        social_stamp = _parse_time(social.get("updated_at"))
        if source_stamp is None or social_stamp is None or source_stamp != social_stamp:
            findings.append({"severity": "critical", "code": "SOCIAL_COVERAGE_SYNC_MISMATCH"})
        if social_stamp is None:
            findings.append({"severity": "critical", "code": "MISSING_SOCIAL_TIMESTAMP"})
        elif (now - social_stamp).total_seconds() > max_social_age_hours * 3600:
            findings.append({"severity": "critical", "code": "STALE_SOCIAL_SNAPSHOT",
                             "age_hours": round((now - social_stamp).total_seconds() / 3600, 2)})
        if social.get("fresh_collection_ok") is not True:
            findings.append({"severity": "critical", "code": "SOCIAL_FRESH_COLLECTION_NOT_CONFIRMED"})

    try:
        report = _load(root / "auto_update_report.json")
    except ValueError as exc:
        report = {}
        findings.append({"severity": "critical", "code": "INVALID_AUTO_UPDATE_REPORT",
                         "error": str(exc)})

    if report:
        finished = _parse_time(report.get("finished_at"))
        if finished is None:
            findings.append({"severity": "critical", "code": "MISSING_REPORT_TIMESTAMP"})
        elif (now - finished).total_seconds() > max_report_age_hours * 3600:
            findings.append({"severity": "critical", "code": "STALE_AUTO_UPDATE_REPORT",
                             "age_hours": round((now - finished).total_seconds() / 3600, 2)})
        rows = report.get("results")
        if not isinstance(rows, list):
            findings.append({"severity": "critical", "code": "INVALID_REPORT_RESULTS"})
        else:
            by_file = {str(row.get("file")): row for row in rows if isinstance(row, dict)}
            for filename in PUBLIC_OUTPUTS:
                row = by_file.get(filename)
                if row is None:
                    findings.append({"severity": "critical", "code": "PUBLIC_OUTPUT_NOT_REPORTED",
                                     "target": filename})
                elif row.get("ok") is not True:
                    findings.append({"severity": "critical", "code": "PUBLIC_OUTPUT_COLLECTION_FAILED",
                                     "target": filename, "error": str(row.get("error") or "")[:500]})
        sync = report.get("auxiliary_coverage_sync")
        if not isinstance(sync, dict) or sync.get("ok") is not True:
            findings.append({"severity": "critical", "code": "AUXILIARY_COVERAGE_SYNC_FAILED"})

    counts = {
        "critical": sum(x.get("severity") == "critical" for x in findings),
        "warning": sum(x.get("severity") == "warning" for x in findings),
        "info": sum(x.get("severity") == "info" for x in findings),
    }
    return {
        "schema_version": 1,
        "checked_at": now.isoformat(timespec="seconds"),
        "status": "pass" if counts["critical"] == 0 else "fail_closed",
        "counts": counts,
        "expected_topic_cells": EXPECTED_TOPIC_CELLS,
        "findings": findings,
        "publish_allowed": counts["critical"] == 0,
        "policy": "검증된 기존행 보존 + 전체 토픽 수집시도 + 최신 후보 동기화 후에만 Pages 정적자료 커밋",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--report", default="STATIC_DATA_PUBLISH_REPORT.json")
    parser.add_argument("--max-social-age-hours", type=float, default=12.0)
    parser.add_argument("--max-report-age-hours", type=float, default=2.0)
    args = parser.parse_args()
    report = verify(Path(args.root), max_social_age_hours=args.max_social_age_hours,
                    max_report_age_hours=args.max_report_age_hours)
    atomic_write_json(Path(args.report), report, suffix=".publish-gate.tmp")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["publish_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
