#!/usr/bin/env python3
"""Performance-optimized execution path for the canonical AI tracker.

This module reuses ai_auto_tracker's state schema, safety contracts, retry policy,
quarantine handoff, and verified-learning logic. It does not create a second
tracker or learning store.

V6 optimizations are run-scoped and deterministic:
- normalize every hot event field once;
- derive domain, severity, and fingerprint from the same prepared feature set;
- prepare event features/domain/severity/fingerprint before the state lock;
- hold the persistent-state lock only for a short snapshot and final atomic commit;
- build/search the Graphify map outside the state lock;
- cache Graphify impact analysis by normalized origin path;
- choose one bounded map depth per path from the highest severity in the batch;
- execute SELF-REFINE quarantine handoff outside the state lock;
- reuse compact Code Map output and computed severity in handoffs;
- keep occurrence/state semantics identical to the canonical tracker.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import ai_auto_tracker as tracker
from code_map_intelligence import (
    CodeMapIndex,
    compact_context,
    dedupe_learning_rows,
    event_priority,
    impact_context,
    impact_depth_for_severity,
    learning_health,
    merge_verified_learning,
    verified_learning_candidate,
)

MAX_BATCH_EVENTS = 5000


@dataclass(frozen=True)
class EventFeatures:
    path: str
    stage: str
    fingerprint_stage_lower: str
    error_type: str
    fingerprint_error: str
    message: str
    evidence: str
    source: str
    explicit_domain: str
    explicit_severity: str
    domain_haystack: str
    severity_haystack: str


def _features(event: dict[str, Any]) -> EventFeatures:
    """Normalize all strings needed by routing, severity, fingerprint and handoff once."""
    path = tracker._clean(event.get("path"), 240).replace("\\", "/")
    stage_raw = tracker._clean(event.get("stage"), 500)
    stage = stage_raw[:80] or "UNKNOWN"
    message_raw = tracker._clean(event.get("message"), 500)
    evidence_raw = tracker._clean(event.get("evidence"), 500)
    source = tracker._clean(event.get("source"), 500)
    error_value = event.get("error_type") or "unknown"
    error_type = tracker._clean(error_value, 100)
    fingerprint_error = tracker._clean(event.get("error_type") or event.get("message"), 220).lower()
    explicit_domain = tracker._clean(event.get("domain"), 20).lower()
    explicit_severity = tracker._clean(event.get("severity"), 20).lower()
    domain_haystack = " ".join((stage_raw.lower(), path.lower(), message_raw.lower(), evidence_raw.lower(), source.lower()))
    severity_haystack = " ".join((stage_raw[:300].lower(), message_raw[:300].lower(), evidence_raw[:300].lower()))
    return EventFeatures(
        path=path,
        stage=stage,
        fingerprint_stage_lower=stage_raw[:80].lower(),
        error_type=error_type,
        fingerprint_error=fingerprint_error,
        message=(message_raw or evidence_raw)[:240],
        evidence=(evidence_raw or message_raw)[:240],
        source=source,
        explicit_domain=explicit_domain,
        explicit_severity=explicit_severity,
        domain_haystack=domain_haystack,
        severity_haystack=severity_haystack,
    )


def _domain_from_features(features: EventFeatures) -> str:
    if features.explicit_domain in tracker.DOMAINS:
        return features.explicit_domain
    scores = {
        tracker.DOMAIN_MARKET: sum(token in features.domain_haystack for token in tracker.MARKET_HINTS),
        tracker.DOMAIN_TABLET: sum(token in features.domain_haystack for token in tracker.TABLET_HINTS),
        tracker.DOMAIN_GITHUB: sum(token in features.domain_haystack for token in tracker.GITHUB_HINTS),
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else tracker.DOMAIN_GITHUB


def _severity_from_features(features: EventFeatures) -> str:
    if features.explicit_severity in {"critical", "high", "medium", "low"}:
        return features.explicit_severity
    text = features.severity_haystack
    if any(x in text for x in ("security_high", "data loss", "corrupt", "credential", "secret leak")):
        return "critical"
    if any(x in text for x in ("syntax", "startup", "deploy", "unavailable", "crash", "403", "429")):
        return "high"
    if any(x in text for x in ("timeout", "stale", "mismatch", "failed", "error")):
        return "medium"
    return "low"


def _fingerprint_from_features(features: EventFeatures, domain: str) -> str:
    parts = (
        domain,
        features.fingerprint_stage_lower,
        features.path.lower(),
        features.fingerprint_error,
    )
    return hashlib.sha256("|".join(parts).encode("utf-8", "replace")).hexdigest()[:24]


def _handoff_payload_fast(
    *,
    incident_id: str,
    domain: str,
    severity: str,
    features: EventFeatures,
    compact_map: dict[str, Any],
    observed_at: str,
) -> dict[str, Any]:
    return {
        "incident_id": incident_id,
        "domain": domain,
        "stage": features.stage,
        "path": features.path,
        "severity": severity,
        "error_type": features.error_type,
        "evidence": features.evidence,
        "observed_at": observed_at,
        "code_map": compact_map,
    }


def observe(
    events: Iterable[dict[str, Any]],
    *,
    state_path: Path = tracker.STATE,
    dry_run: bool = False,
    code_map_root: Path | None = None,
) -> dict[str, Any]:
    normalized = [dict(x) for x in events if isinstance(x, dict)][:MAX_BATCH_EVENTS]

    prepared: list[tuple[dict[str, Any], EventFeatures, str, str, str]] = []
    path_depth: dict[str, int] = {}
    for event in normalized:
        features = _features(event)
        domain = _domain_from_features(features)
        severity = _severity_from_features(features)
        iid = _fingerprint_from_features(features, domain)
        prepared.append((event, features, domain, severity, iid))
        depth = impact_depth_for_severity(severity)
        path_depth[features.path] = max(depth, path_depth.get(features.path, 0))

    with tracker.exclusive_file_lock(state_path):
        state_snapshot = tracker._load_state(state_path)
        learning_state = state_snapshot.get("code_map_learning")

    map_root = Path(code_map_root) if code_map_root is not None else tracker.ROOT
    map_index = CodeMapIndex(map_root)
    map_cache: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    cache_hits = 0
    verified_learning: list[dict[str, Any]] = []
    analyzed: list[
        tuple[
            dict[str, Any], EventFeatures, str, str, str,
            dict[str, Any], dict[str, Any],
        ]
    ] = []

    for event, features, domain, severity, iid in prepared:
        cache_key = features.path
        cached = map_cache.get(cache_key)
        if cached is not None:
            map_context, compact_map = cached
            cache_hits += 1
        else:
            map_context = impact_context(
                map_root,
                cache_key,
                depth=path_depth.get(cache_key, 2),
                index=map_index,
                learning=learning_state,
            )
            compact_map = compact_context(map_context)
            map_cache[cache_key] = (map_context, compact_map)

        analyzed.append((
            event, features, domain, severity, iid, map_context, compact_map,
        ))

        changed_files = event.get("changed_files") if isinstance(event.get("changed_files"), list) else []
        verified = bool(event.get("verified")) or str(event.get("verification") or "").lower() in {
            "verified", "full_verified", "full_regression_verified",
        }
        candidate = verified_learning_candidate(
            origin_path=features.path,
            changed_files=changed_files,
            impact=map_context,
            verified=verified,
            regression_pass=event.get("regression_pass") is True,
        )
        if candidate is not None:
            verified_learning.append(candidate)

    verified_learning = dedupe_learning_rows(verified_learning)
    now = tracker._now()
    observed: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    selfrefine: list[dict[str, Any]] = []

    def append_rows(active_state: dict[str, Any], *, persist: bool) -> None:
        for event, features, domain, severity, iid, map_context, compact_map in analyzed:
            incident = active_state["incidents"].get(iid, {})
            count = min(1_000_000, int(incident.get("occurrences", 0) or 0) + 1)
            status = "new" if count == 1 else "recurring"
            row = {
                "incident_id": iid,
                "domain": domain,
                "severity": severity,
                "impact_priority": event_priority(severity, map_context),
                "status": status,
                "occurrences": count,
                "stage": features.stage,
                "path": features.path,
                "error_type": features.error_type,
                "message": features.message,
                "first_seen": incident.get("first_seen") or now,
                "last_seen": now,
                "code_map": compact_map,
            }
            observed.append(row)
            handoffs.append(_handoff_payload_fast(
                incident_id=iid,
                domain=domain,
                severity=severity,
                features=features,
                compact_map=compact_map,
                observed_at=now,
            ))
            active_state["incidents"][iid] = row
            if persist:
                active_state["history"].append({
                    "at": now,
                    "incident_id": iid,
                    "domain": domain,
                    "event": "incident_observed",
                    "status": status,
                })

    if dry_run:
        state = state_snapshot
        append_rows(state, persist=False)
    else:
        with tracker.exclusive_file_lock(state_path):
            state = tracker._load_state(state_path)
            append_rows(state, persist=True)
            if verified_learning:
                merge_verified_learning(state, verified_learning)
            tracker._save_state(state, state_path)

        for event, _features_row, domain, _severity, iid, _map_context, _compact_map in analyzed:
            if domain == tracker.DOMAIN_GITHUB:
                result = tracker._main_selfrefine_observe(event)
                if result is not None:
                    selfrefine.append({"incident_id": iid, **result})

    total_map_requests = len(observed)
    summary = {
        "observed": len(observed),
        "new": sum(row["status"] == "new" for row in observed),
        "recurring": sum(row["status"] == "recurring" for row in observed),
        "by_domain": {
            domain: sum(row["domain"] == domain for row in observed)
            for domain in sorted(tracker.DOMAINS)
        },
        "critical_high": sum(row["severity"] in {"critical", "high"} for row in observed),
        "dry_run": dry_run,
        "code_map_available": sum(bool(row.get("code_map", {}).get("available")) for row in observed),
        "verified_code_map_learning": len(verified_learning),
        "code_map_high_risk": sum(
            row.get("code_map", {}).get("structural_risk") == "high" for row in observed
        ),
        "code_map_stale": sum(
            row.get("code_map", {}).get("status") == "stale_for_origin" for row in observed
        ),
        "performance": {
            "mode": "cached_hot_path_v6",
            "batch_events": len(normalized),
            "prepared_events": len(prepared),
            "unique_code_map_paths": len(map_cache),
            "code_map_cache_hits": cache_hits,
            "code_map_cache_hit_ratio": round(cache_hits / total_map_requests, 4) if total_map_requests else 0.0,
            "event_feature_extraction": "single_pass",
            "feature_extraction_outside_state_lock": True,
            "map_index_build_outside_state_lock": True,
            "map_analysis_outside_state_lock": True,
            "selfrefine_outside_state_lock": True,
            "state_lock_scope": "snapshot_and_commit_only",
            "state_lock_phases": 1 if dry_run else 2,
            "adaptive_code_map_depth": True,
            "max_code_map_depth": max(path_depth.values(), default=0),
            "basename_indexed_code_map": True,
            "domain_rescan": False,
            "severity_rescan": False,
            "fingerprint_reclean": False,
            "compact_code_map_rebuild_on_hit": False,
            "verified_learning_deduped_per_run": True,
            "verified_learning_unique_outcomes": len(verified_learning),
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
            "mode": "graphify_read_only_impact_analysis_cached_per_origin_adaptive_depth",
            "verified_learning": verified_learning,
            "self_refine": learning_health(
                state.get("code_map_learning") if isinstance(state, dict) else None,
                map_signature=map_index.signature,
            ),
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
            "state_commit_reloads_fresh_state": True,
        },
    }
