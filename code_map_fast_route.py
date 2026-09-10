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
IG_COLLECTION_GROUP = "instagram_cardinfo_collection_health"
IG_COLLECTION_HEALTH = "instagram_tcg_content/collection_health.py"
IG_COLLECTION_GAP = "instagram_tcg_content/collection_freshness_gap_guard.py"
IG_COLLECTION_RECOVERY = "instagram_tcg_content/collection_recovery_runner.py"
IG_COLLECTION_TESTS = (
    "instagram_tcg_content/test_collection_freshness_gap_guard.py",
    "instagram_tcg_content/test_collection_recovery_runner.py",
    "instagram_tcg_content/test_collection_health.py",
)
IG_COLLECTION_TEST_NODES = (
    "instagram_tcg_content/test_collection_freshness_gap_guard.py::CollectionFreshnessGapGuardTests::test_fresh_shared_collection_plus_stale_ig_is_persistence_lag",
    "instagram_tcg_content/test_collection_recovery_runner.py::CollectionRecoveryRunnerTests::test_incremental_recovery_merges_only_fresh_verified_instagram_facts",
)


def _merge_unique(*values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for rows in values:
        for row in rows:
            value = str(row or "").strip()
            if value and value not in result:
                result.append(value)
    return result


def _instagram_collection_route_override(query: str, base: dict) -> dict:
    """Promote known IG collection gap/recovery requests without repo-wide search.

    The large static code-map stays generic; this public maintenance entrypoint owns
    the operational routing for the newly added freshness-gap and recovery runner.
    This is intentionally routing only and never grants verification authority.
    """
    text = " ".join(str(query or "").lower().split())
    scoped = any(marker in text for marker in (
        "인스타 카드정보",
        "instagram cardinfo",
        "instagram card info",
        "ig cardinfo",
    ))
    if not scoped:
        return dict(base)

    recovery_markers = (
        "수집 복구 실행",
        "복구수집 실행",
        "복구 실행",
        "capture packet",
        "recovery runner",
        "collection recovery runner",
        "ig-local capture",
        "ig local capture",
    )
    gap_markers = (
        "수집 단절",
        "스냅샷 stale",
        "snapshot stale",
        "스냅샷만 stale",
        "snapshot만 stale",
        "수집은 최신",
        "공용 수집은 최신",
        "freshness gap",
        "persistence lag",
        "ig snapshot stale",
        "스냅샷 지연",
        "snapshot 지연",
    )
    if any(marker in text for marker in recovery_markers):
        entry = IG_COLLECTION_RECOVERY
        alternates = [IG_COLLECTION_GAP, IG_COLLECTION_HEALTH]
        reason = "fast_route_instagram_collection_recovery_rule"
    elif any(marker in text for marker in gap_markers):
        entry = IG_COLLECTION_GAP
        alternates = [IG_COLLECTION_RECOVERY, IG_COLLECTION_HEALTH]
        reason = "fast_route_instagram_collection_gap_rule"
    else:
        return dict(base)

    result = dict(base)
    prior_groups = [
        row for row in (base.get("matched_feature_groups") or [])
        if isinstance(row, dict) and row.get("group") != IG_COLLECTION_GROUP
    ]
    result["matched_feature_groups"] = [
        {"group": IG_COLLECTION_GROUP, "score": 100.0},
        *prior_groups,
    ]
    result["entry_group"] = IG_COLLECTION_GROUP
    result["entry_file"] = entry
    result["entry_files"] = [entry]
    result["alternate_entry_files"] = alternates
    result["entrypoint_reason"] = reason
    result["primary_files"] = _merge_unique(
        [entry, *alternates],
        base.get("primary_files") or [],
    )
    result["support_files"] = [
        path for path in result["primary_files"]
        if path != entry and path not in alternates
    ]
    result["suggested_tests"] = _merge_unique(
        IG_COLLECTION_TESTS,
        base.get("suggested_tests") or [],
    )
    result["suggested_test_nodes"] = _merge_unique(
        IG_COLLECTION_TEST_NODES,
        base.get("suggested_test_nodes") or [],
    )
    result["repository_wide_search_required"] = False
    result["repository_wide_search_avoided"] = True
    result["route_decision"] = "direct_entrypoint"
    result["route_source"] = str(base.get("route_source") or "") + "+fast_ig_collection_override"
    result["code_map_override"] = True
    result["verification_authority"] = False
    return result


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

    # Cheap feature-name routing always comes first. Unknown features have no
    # bounded seed, so loading Graphify before fallback search only adds latency.
    fast_route = _instagram_collection_route_override(
        query,
        resolve_feature_query(query),
    )
    result = dict(fast_route)
    graph_load_attempted = False
    graph_load_ms = 0.0

    if include_impact and not fast_route.get("repository_wide_search_required") and fast_route.get("entry_files"):
        graph_load_attempted = True
        graph_started = time.perf_counter()
        index = CodeMapIndex(ROOT)
        graph_load_ms = round((time.perf_counter() - graph_started) * 1000.0, 3)
        if fast_route.get("code_map_override"):
            # Do not let the generic static resolver silently replace the explicit
            # IG gap/recovery entrypoint. Traverse from the promoted file itself.
            impact = index.impact(
                str(fast_route["entry_file"]),
                depth=depth,
                limit=max(1, min(24, int(max_seeds) * 6)),
            )
            result = dict(fast_route)
            result["seed_files"] = [str(fast_route["entry_file"])]
            result["impacted_files"] = list(impact.get("impacted_files") or [])
            result["suggested_tests"] = _merge_unique(
                fast_route.get("suggested_tests") or [],
                impact.get("suggested_tests") or [],
            )
            result["critical_runtime_files"] = list(impact.get("critical_runtime_files") or [])
            result["seed_results"] = [{
                "seed": str(fast_route["entry_file"]),
                "available": bool(impact.get("available")),
                "status": str(impact.get("status") or ""),
                "confidence": float(impact.get("confidence") or 0.0),
                "fanout_files": int(impact.get("fanout_files") or 0),
            }]
            result["graph_available"] = bool(index.available)
            result["map_signature"] = str(index.signature or "")
        else:
            result = index.feature_impact(query, depth=depth, max_seed_files=max_seeds)
        result["graph_loaded"] = bool(index.available)
        result["graph_load_attempted"] = True
        result["graph_load_ms"] = graph_load_ms
        result["diagnostic_strategy"] = "entrypoint_then_bounded_impact"
    elif include_impact:
        result["graph_loaded"] = False
        result["graph_load_attempted"] = False
        result["graph_load_ms"] = 0.0
        result["impact_skipped_reason"] = "feature_route_unknown_no_bounded_seed"
        result["diagnostic_strategy"] = "entrypoint_route_then_fallback_search"
    else:
        result["graph_loaded"] = False
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
        "1_entrypoint": result.get("entry_file"),
        "1a_alternate_entrypoints": list(result.get("alternate_entry_files") or []),
        "2_bounded_impact": {
            "requested": bool(include_impact),
            "graph_load_attempted": graph_load_attempted,
            "depth": depth,
            "seed_files": list(result.get("seed_files") or result.get("entry_files") or []),
            "impacted_files": list(result.get("impacted_files") or []),
            "skipped_reason": result.get("impact_skipped_reason"),
        },
        "3_recommended_tests": list(result.get("suggested_tests") or []),
        "3a_recommended_test_nodes": list(result.get("suggested_test_nodes") or []),
        "3b_deferred_related_tests": list(result.get("related_tests") or []),
        "3c_deferred_related_test_nodes": list(result.get("related_test_nodes") or []),
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
        help="actual changed file; repeat to make validation scope change-aware",
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
