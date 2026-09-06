#!/usr/bin/env python3
"""Bounded multi-incident correlation for the existing AI tracker.

This module is stateless. It never executes learned text, never writes code, and
never merges GitHub/market/tablet learning state. It only correlates already
observed incidents inside one report to help choose the safest next validation.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from ai_reasoning_enhancer import enrich_incident

MAX_CLUSTERS = 32
MAX_MEMBERS = 20
MAX_CHAINS = 24
MAX_TESTS = 10

CAUSE_ORDER = {
    "deployment_sync": 10,
    "startup_runtime": 20,
    "network_dns_timeout": 25,
    "network_access_blocked": 25,
    "network_rate_limit": 25,
    "parser_schema": 30,
    "data_integrity": 40,
    "ui_cross_device": 50,
    "test_regression": 60,
    "security_boundary": 70,
    "unknown": 99,
}

CAUSE_TESTS = {
    "deployment_sync": ("verify origin/main SHA match", "run runtime delivery guard"),
    "startup_runtime": ("check /api/v135-health", "run Android startup/boot regression"),
    "network_dns_timeout": ("run bounded DNS/reachability probe", "verify retry exhaustion preserves state"),
    "network_access_blocked": ("verify 403 degraded fallback", "confirm no block-bypass path exists"),
    "network_rate_limit": ("verify Retry-After/backoff/circuit breaker", "confirm last verified data is retained"),
    "parser_schema": ("run parser fixture/schema regression", "run collection verification gate"),
    "data_integrity": ("run atomic-write/lock/corrupt-state tests", "verify rollback and persistence"),
    "ui_cross_device": ("run button/link/browser smoke tests", "compare tablet/iPhone/PC/Pages behavior"),
    "test_regression": ("run first failing targeted guard", "run full repository regression after fix"),
    "security_boundary": ("run defensive security audit", "verify secret redaction and path/URL boundaries"),
    "unknown": ("collect stage/path/error_type evidence", "require human review before repair"),
}


def _text(value: Any, limit: int = 200) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:limit]


def _contradictions(row: dict[str, Any]) -> list[str]:
    found: list[str] = []
    verification = _text(row.get("verification"), 40).lower()
    verified = row.get("verified") is True or verification in {
        "verified", "full_verified", "full_regression_verified",
    }
    if verified and row.get("regression_pass") is False:
        found.append("verified_but_regression_failed")
    status = _text(row.get("status"), 40).lower()
    message = _text(row.get("message") or row.get("evidence"), 400).lower()
    if status in {"ok", "healthy", "success", "passed"} and any(x in message for x in ("failed", "error", "crash", "unavailable")):
        found.append("healthy_status_with_failure_evidence")
    if row.get("resolved") is True and int(row.get("occurrences") or 1) > 1 and status in {"new", "recurring", "open"}:
        found.append("resolved_flag_with_active_recurrence")
    return found


def _enriched(row: dict[str, Any]) -> dict[str, Any]:
    current = row.get("intelligence")
    if isinstance(current, dict) and isinstance(current.get("assessment"), dict):
        return current
    return enrich_incident(
        row,
        occurrences=row.get("occurrences", 1),
        code_map=row.get("code_map") if isinstance(row.get("code_map"), dict) else None,
    )


def correlate(incidents: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [dict(x) for x in incidents if isinstance(x, dict)][:500]
    clusters: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    enriched_rows: list[dict[str, Any]] = []
    contradictions: list[dict[str, Any]] = []

    for row in rows:
        intel = _enriched(row)
        assessment = intel.get("assessment") or {}
        domain = str((assessment.get("domain") or {}).get("domain") or row.get("domain") or "github")
        cause = str((assessment.get("root_cause") or {}).get("family") or "unknown")
        enriched = dict(row)
        enriched["intelligence"] = intel
        enriched_rows.append(enriched)
        clusters[(domain, cause)].append(enriched)
        issues = _contradictions(row)
        if issues:
            contradictions.append({
                "incident_id": _text(row.get("incident_id"), 80),
                "domain": domain,
                "issues": issues,
            })

    cluster_rows: list[dict[str, Any]] = []
    for (domain, cause), members in sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:MAX_CLUSTERS]:
        priorities = [str(((m.get("intelligence") or {}).get("assessment") or {}).get("priority") or "P3") for m in members]
        highest = min(priorities, key=lambda p: {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(p, 9)) if priorities else "P3"
        cluster_rows.append({
            "cluster_id": f"{domain}:{cause}",
            "domain": domain,
            "root_cause": cause,
            "count": len(members),
            "highest_priority": highest,
            "member_ids": [_text(m.get("incident_id"), 80) for m in members[:MAX_MEMBERS]],
        })

    ordered = sorted(cluster_rows, key=lambda c: (CAUSE_ORDER.get(c["root_cause"], 99), -c["count"], c["cluster_id"]))
    chains: list[dict[str, Any]] = []
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in ordered:
        by_domain[cluster["domain"]].append(cluster)
    for domain, domain_clusters in sorted(by_domain.items()):
        for left, right in zip(domain_clusters, domain_clusters[1:]):
            if CAUSE_ORDER.get(left["root_cause"], 99) < CAUSE_ORDER.get(right["root_cause"], 99):
                chains.append({
                    "domain": domain,
                    "possible_upstream": left["cluster_id"],
                    "possible_downstream": right["cluster_id"],
                    "confidence": "bounded_heuristic",
                })
                if len(chains) >= MAX_CHAINS:
                    break

    tests: list[str] = []
    for cluster in sorted(cluster_rows, key=lambda c: ({"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(c["highest_priority"], 9), -c["count"])):
        for test in CAUSE_TESTS.get(cluster["root_cause"], CAUSE_TESTS["unknown"]):
            if test not in tests:
                tests.append(test)
            if len(tests) >= MAX_TESTS:
                break
        if len(tests) >= MAX_TESTS:
            break
    if contradictions and "resolve contradictory evidence before auto-repair" not in tests:
        tests.insert(0, "resolve contradictory evidence before auto-repair")
        tests = tests[:MAX_TESTS]

    return {
        "schema": 1,
        "incident_count": len(enriched_rows),
        "cluster_count": len(cluster_rows),
        "clusters": cluster_rows,
        "possible_causal_chains": chains,
        "contradictions": contradictions[:50],
        "recommended_test_plan": tests,
        "human_review_required": bool(contradictions) or any(
            bool(((row.get("intelligence") or {}).get("assessment") or {}).get("human_review_required"))
            for row in enriched_rows
        ),
        "safety": {
            "stateless": True,
            "cross_domain_state_merge": False,
            "learned_text_executable": False,
            "auto_patch": False,
            "correlation_is_proof": False,
        },
    }
