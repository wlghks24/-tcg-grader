#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Iterable

from code_map_intelligence import (
    CodeMapIndex,
    impact_depth_for_severity,
    resolve_feature_query,
    validation_plan_for_changes,
    validation_plan_for_route,
)

ROOT = Path(__file__).resolve().parent


def route(
    query: str,
    *,
    severity: str = "low",
    max_seeds: int = 4,
    include_impact: bool = False,
    changed_files: Iterable[str] = (),
) -> dict:
    started = time.perf_counter()
    depth = impact_depth_for_severity(severity)

    # Always do the cheap feature-name route first.  Unknown features have no
    # bounded seed, so loading the full graph before fallback search only adds
    # latency without producing useful impact information.
    fast_route = resolve_feature_query(query)
    result = fast_route
    graph_load_attempted = False
    graph_load_ms = 0.0

    if include_impact and not fast_route.get("repository_wide_search_required") and fast_route.get("entry_files"):
        graph_load_attempted = True
        graph_started = time.perf_counter()
        index = CodeMapIndex(ROOT)
        graph_load_ms = round((time.perf_counter() - graph_started) * 1000.0, 3)
        result = index.feature_impact(query, depth=depth, max_seed_files=max_seeds)
        result["graph_loaded"] = bool(index.available)
        result["graph_load_attempted"] = True
        result["graph_load_ms"] = graph_load_ms
        result["diagnostic_strategy"] = "entrypoint_then_bounded_impact"
    elif include_impact:
        result = dict(fast_route)
        result["graph_loaded"] = False
        result["graph_load_attempted"] = False
        result["graph_load_ms"] = 0.0
        result["impact_skipped_reason"] = "feature_route_unknown_no_bounded_seed"
        result["diagnostic_strategy"] = "entrypoint_route_then_fallback_search"
    else:
        result = dict(fast_route)
        result["graph_load_attempted"] = False
        result["graph_load_ms"] = 0.0
        result["diagnostic_strategy"] = "entrypoint_first"

    changed = list(dict.fromkeys(str(path).strip() for path in changed_files if str(path).strip()))
    if changed:
        plan = validation_plan_for_changes(result, changed, severity)
    else:
        plan = validation_plan_for_route(result, severity)
        plan["run_now"] = list(plan["initial_checks"])
        plan["full_chain_required_now"] = bool(plan["full_chain_immediate"])
        plan["deferred_full_chain"] = [] if plan["full_chain_immediate"] else list(plan["full_chain"])
        plan["change_boundary"] = {
            "changed_files": [],
            "changed_file_count": 0,
            "route_local_files": [],
            "outside_route_files": [],
            "workflow_files": [],
            "critical_runtime_files": [],
            "domain_boundary_files": [],
            "security_files": [],
        }
        plan["escalation_reasons"] = []

    result["validation_plan"] = plan
    result["full_chain_after_fix"] = plan["full_chain"]
    result["repository_search_policy"] = (
        "fallback_only"
        if result.get("repository_wide_search_avoided")
        else "fallback_required"
    )
    result["ci_execution_plan"] = {
        "run_now": list(plan.get("run_now") or plan.get("initial_checks") or []),
        "full_chain_required_now": bool(plan.get("full_chain_required_now")),
        "deferred_full_chain": list(plan.get("deferred_full_chain") or []),
        "reason": list(plan.get("escalation_reasons") or []),
    }
    result["exploration_plan"] = {
        "1_entrypoint": list(result.get("entry_files") or []),
        "2_bounded_impact": {
            "requested": bool(include_impact),
            "graph_load_attempted": graph_load_attempted,
            "depth": depth,
            "seed_files": list(result.get("seed_files") or result.get("entry_files") or []),
            "impacted_files": list(result.get("impacted_files") or []),
            "skipped_reason": result.get("impact_skipped_reason"),
        },
        "3_recommended_tests": list(result.get("suggested_tests") or []),
        "4_validation_scope": plan["initial_scope"],
        "5_ci_execution": result["ci_execution_plan"],
        "fallback_repo_search": bool(result.get("repository_wide_search_required")),
    }
    result["route_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    result["severity"] = severity
    result["depth"] = depth
    result["changed_files"] = changed
    result["purpose"] = "find-first-fix-fast"
    result["bottleneck_analysis"] = {
        "feature_route_ms_budget": 100.0,
        "graph_load_ms": graph_load_ms,
        "candidate_files_scanned": int(result.get("candidate_files_scanned") or 0),
        "graph_loaded_only_when_bounded_impact_requested": not (
            result.get("graph_load_attempted") and not include_impact
        ),
        "unknown_feature_graph_load_avoided": not (
            include_impact
            and result.get("repository_wide_search_required")
            and result.get("graph_load_attempted")
        ),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="+", help="feature/request text")
    parser.add_argument("--severity", default="low", choices=("low", "medium", "high", "critical"))
    parser.add_argument("--max-seeds", type=int, default=4)
    parser.add_argument("--impact", action="store_true", help="load Graphify only after a known feature route and merge bounded impact")
    parser.add_argument(
        "--changed",
        action="append",
        default=[],
        metavar="PATH",
        help="actual changed file; repeat to make CI scope change-aware",
    )
    args = parser.parse_args()
    result = route(
        " ".join(args.query),
        severity=args.severity,
        max_seeds=args.max_seeds,
        include_impact=args.impact,
        changed_files=args.changed,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
