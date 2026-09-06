#!/usr/bin/env python3
"""Canonical intelligence wrapper around the existing AI auto tracker.

Uses the same tracker state/report files. No second state store is created.
The execution hot path uses a run-scoped performance cache that preserves the
canonical state schema and safety contracts while avoiding duplicate analysis.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import ai_auto_tracker as tracker
import ai_performance_runtime as performance_runtime
from ai_reasoning_enhancer import enrich_incident
from ai_correlation_engine import correlate


def run(events: list[dict], *, state_path: Path = tracker.STATE, dry_run: bool = False,
        code_map_root: Path | None = None) -> dict:
    report = performance_runtime.observe(
        events,
        state_path=state_path,
        dry_run=dry_run,
        code_map_root=code_map_root,
    )
    enriched = []
    for row in report.get("incidents", []):
        item = dict(row)
        item["intelligence"] = enrich_incident(
            item,
            occurrences=item.get("occurrences", 1),
            code_map=item.get("code_map") if isinstance(item.get("code_map"), dict) else None,
        )
        enriched.append(item)
    report["incidents"] = enriched
    report["intelligence"] = {
        "mode": "bounded_reasoning_plus_multi_incident_correlation_cached_runtime",
        "correlation": correlate(enriched),
        "safety": {
            "same_tracker_state": True,
            "separate_learning_store": False,
            "cross_domain_state_merge": False,
            "auto_patch_from_reasoning": False,
            "full_regression_required": True,
            "run_scoped_performance_cache": True,
        },
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI tracker + bounded reasoning/correlation")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--state", type=Path, default=tracker.STATE)
    parser.add_argument("--report", type=Path, default=tracker.REPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    events = tracker.events_from_json(args.input) if args.input else []
    result = run(events, state_path=args.state, dry_run=args.dry_run)
    if not args.dry_run:
        tracker.atomic_write_json(args.report, result, suffix=".ai-intelligence-report.tmp")
    performance = result.get("summary", {}).get("performance", {})
    print(json.dumps({
        **result.get("summary", {}),
        "clusters": result["intelligence"]["correlation"]["cluster_count"],
        "contradictions": len(result["intelligence"]["correlation"]["contradictions"]),
        "code_map_cache_hits": performance.get("code_map_cache_hits", 0),
    }, ensure_ascii=False, sort_keys=True))
    return 1 if result.get("summary", {}).get("critical_high") else 0


if __name__ == "__main__":
    raise SystemExit(main())
