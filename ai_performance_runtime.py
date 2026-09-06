#!/usr/bin/env python3
"""Performance-optimized execution path for the canonical AI tracker.

This module deliberately reuses ai_auto_tracker's state schema, safety contracts,
retry policy, quarantine handoff, and verified-learning logic. It does not create
a second tracker or learning store. The optimization is limited to eliminating
repeated pure work inside one observe() call:

- normalize hot event fields once;
- cache Graphify impact analysis by normalized origin path for the run;
- reuse the already-computed severity in handoffs;
- keep occurrence/state semantics identical to the canonical tracker.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import ai_auto_tracker as tracker
from code_map_intelligence import (
    CodeMapIndex,
    compact_context,
    event_priority,
    impact_context,
    merge_verified_learning,
    verified_learning_candidate,
)

MAX_BATCH_EVENTS = 5000


def _prepared(event: dict[str, Any]) -> dict[str, Any]:
    """Normalize repeatedly-used fields once without mutating the input event."""
    path = tracker._clean(event.get("path"), 240).replace("\\", "/")
    stage = tracker._clean(event.get("stage"), 80) or "UNKNOWN"
    error_type = tracker._clean(event.get("error_type") or "unknown", 100)
    message = tracker._clean(event.get("message") or event.get("evidence"), 240)
    evidence = tracker._clean(event.get("evidence") or event.get("message"), 240)
    return {
        "path": path,
        "stage": stage,
        "error_type": error_type,
        "message": message,
        "evidence": evidence,
    }


def _handoff_payload_fast(
    *,
    incident_id: str,
    domain: str,
    severity: str,
    prepared: dict[str, Any],
    map_context: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    return {
        "incident_id": incident_id,
        "domain": domain,
        "stage": prepared["stage"],
        "path": prepared["path"],
        "severity": severity,
        "error_type": prepared["error_type"],
        "evidence": prepared["evidence"],
        "observed_at": observed_at,
        "code_map": compact_context(map_context),
    }


def observe(
    events: Iterable[dict[str, Any]],
    *,
    state_path: Path = tracker.STATE,
    dry_run: bool = False,
    code_map_root: Path | None = None,
) -> dict[str, Any]:
    normalized = [dict(x) for x in events if isinstance(x, dict)][:MAX_BATCH_EVENTS]
    with tracker.exclusive_file_lock(state_path):
        state = tracker._load_state(state_path)
        observed: list[dict[str, Any]] = []
        handoffs: list[dict[str, Any]] = []
        selfrefine: list[dict[str, Any]] = []
        verified_learning: list[dict[str, Any]] = []
        map_root = Path(code_map_root) if code_map_root is not None else tracker.ROOT
        map_index = CodeMapIndex(map_root)
        map_cache: dict[str, dict[str, Any]] = {}
        cache_hits = 0
        now = tracker._now()
        learning_state = state.get("code_map_learning")

        for event in normalized:
            prepared = _prepared(event)
            domain = tracker.classify_domain(event)
            iid = tracker.fingerprint(event, domain)
            incident = state["incidents"].get(iid, {})
            count = min(1_000_000, int(incident.get("occurrences", 0) or 0) + 1)
            status = "new" if count == 1 else "recurring"
            severity = tracker.severity_for(event)

            cache_key = prepared["path"]
            if cache_key in map_cache:
                map_context = map_cache[cache_key]
                cache_hits += 1
            else:
                map_context = impact_context(
                    map_root,
                    cache_key,
                    depth=2,
                    index=map_index,
                    learning=learning_state,
                )
                map_cache[cache_key] = map_context

            compact_map = compact_context(map_context)
            row = {
                "incident_id": iid,
                "domain": domain,
                "severity": severity,
                "impact_priority": event_priority(severity, map_context),
                "status": status,
                "occurrences": count,
                "stage": prepared["stage"],
                "path": prepared["path"],
                "error_type": prepared["error_type"],
                "message": prepared["message"],
                "first_seen": incident.get("first_seen") or now,
                "last_seen": now,
                "code_map": compact_map,
            }
            observed.append(row)
            handoffs.append(_handoff_payload_fast(
                incident_id=iid,
                domain=domain,
                severity=severity,
                prepared=prepared,
                map_context=map_context,
                observed_at=now,
            ))

            changed_files = event.get("changed_files") if isinstance(event.get("changed_files"), list) else []
            verified = bool(event.get("verified")) or str(event.get("verification") or "").lower() in {
                "verified", "full_verified", "full_regression_verified",
            }
            candidate = verified_learning_candidate(
                origin_path=prepared["path"],
                changed_files=changed_files,
                impact=map_context,
                verified=verified,
                regression_pass=event.get("regression_pass") is True,
            )
            if candidate is not None:
                verified_learning.append(candidate)

            if not dry_run:
                state["incidents"][iid] = row
                state["history"].append({
                    "at": now,
                    "incident_id": iid,
                    "domain": domain,
                    "event": "incident_observed",
                    "status": status,
                })
            if domain == tracker.DOMAIN_GITHUB and not dry_run:
                result = tracker._main_selfrefine_observe(event)
                if result is not None:
                    selfrefine.append({"incident_id": iid, **result})

        if not dry_run:
            if verified_learning:
                merge_verified_learning(state, verified_learning)
            tracker._save_state(state, state_path)

    by_domain = {d: 0 for d in sorted(tracker.DOMAINS)}
    new_count = recurring_count = critical_high = map_available = high_risk = stale = 0
    for row in observed:
        by_domain[row["domain"]] += 1
        if row["status"] == "new":
            new_count += 1
        else:
            recurring_count += 1
        if row["severity"] in {"critical", "high"}:
            critical_high += 1
        map_info = row.get("code_map") or {}
        map_available += bool(map_info.get("available"))
        high_risk += map_info.get("structural_risk") == "high"
        stale += map_info.get("status") == "stale_for_origin"

    total_map_requests = len(observed)
    summary = {
        "observed": len(observed),
        "new": new_count,
        "recurring": recurring_count,
        "by_domain": by_domain,
        "critical_high": critical_high,
        "dry_run": dry_run,
        "code_map_available": map_available,
        "verified_code_map_learning": len(verified_learning),
        "code_map_high_risk": high_risk,
        "code_map_stale": stale,
        "performance": {
            "mode": "cached_hot_path_v1",
            "batch_events": len(normalized),
            "unique_code_map_paths": len(map_cache),
            "code_map_cache_hits": cache_hits,
            "code_map_cache_hit_ratio": round(cache_hits / total_map_requests, 4) if total_map_requests else 0.0,
            "event_field_normalization": "single_pass",
            "duplicate_severity_handoff_scan": False,
        },
    }
    return {
        "schema": tracker.SCHEMA,
        "generated_at": tracker._now(),
        "summary": summary,
        "incidents": observed,
        "handoffs": handoffs,
        "main_selfrefine": selfrefine,
        "code_map": {
            "mode": "graphify_read_only_impact_analysis_cached_per_origin",
            "verified_learning": verified_learning,
        },
        "safety": {
            "domain_state_isolation": True,
            "passive_cross_domain_handoff_only": True,
            "learned_text_executable": False,
            "unverified_patch_generation": False,
            "full_regression_required_for_verified_repair": True,
            "code_map_patch_generation": False,
            "code_map_learning_requires_full_regression": True,
            "same_tracker_state_schema": True,
            "performance_cache_run_scoped_only": True,
        },
    }
