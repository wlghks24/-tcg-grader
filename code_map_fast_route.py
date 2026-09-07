#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from code_map_intelligence import CodeMapIndex, impact_depth_for_severity, resolve_feature_query, validation_plan_for_route

ROOT = Path(__file__).resolve().parent


def route(
    query: str, *, severity: str = "low", max_seeds: int = 4, include_impact: bool = False,
) -> dict:
    started = time.perf_counter()
    depth = impact_depth_for_severity(severity)
    if include_impact:
        index = CodeMapIndex(ROOT)
        result = index.feature_impact(query, depth=depth, max_seed_files=max_seeds)
        result["graph_loaded"] = True
        result["diagnostic_strategy"] = "entrypoint_then_bounded_impact"
    else:
        result = resolve_feature_query(query)
        result["diagnostic_strategy"] = "entrypoint_first"
    result["validation_plan"] = validation_plan_for_route(result, severity)
    result["full_chain_after_fix"] = result["validation_plan"]["full_chain"]
    result["repository_search_policy"] = (
        "fallback_only"
        if result.get("repository_wide_search_avoided")
        else "fallback_required"
    )
    result["exploration_plan"] = {
        "1_entrypoint": list(result.get("entry_files") or []),
        "2_bounded_impact": {
            "requested": bool(include_impact),
            "depth": depth,
            "seed_files": list(result.get("seed_files") or result.get("entry_files") or []),
            "impacted_files": list(result.get("impacted_files") or []),
        },
        "3_recommended_tests": list(result.get("suggested_tests") or []),
        "4_validation_scope": result["validation_plan"]["initial_scope"],
        "fallback_repo_search": bool(result.get("repository_wide_search_required")),
    }
    result["route_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    result["severity"] = severity
    result["depth"] = depth
    result["purpose"] = "find-first-fix-fast"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+", help="feature/request text")
    parser.add_argument("--severity", default="low", choices=("low", "medium", "high", "critical"))
    parser.add_argument("--max-seeds", type=int, default=4)
    parser.add_argument("--impact", action="store_true", help="load Graphify and merge bounded impact")
    args = parser.parse_args()
    result = route(
        " ".join(args.query),
        severity=args.severity,
        max_seeds=args.max_seeds,
        include_impact=args.impact,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
