#!/usr/bin/env python3
"""Diagnose freshness gaps between shared discovery and Instagram-local evidence.

The shared release/promo collectors are useful *signals* that upstream discovery is
alive, but they are not Instagram-card verification authority. This module therefore
never copies, promotes, or marks a shared fact as verified. It only distinguishes:

1. upstream collection itself is stale/unavailable; and
2. upstream collection is fresh while the strict IG_CARDINFO factual snapshot is stale.

Case (2) is an actionable Instagram-local capture/persistence gap and should trigger a
bounded IG source recapture followed by ``source_verification_engine.verify_fact`` and
``persisted_crosscheck_export``. Verification standards are never relaxed.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASES = ROOT / "releases.json"
DEFAULT_PROMOS = ROOT / "promo_events.json"
DEFAULT_IG_SNAPSHOT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"

MAX_SHARED_AGE_HOURS = 12.0
MAX_IG_SNAPSHOT_AGE_HOURS = 36.0


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"root must be object: {path}")
    return value


def _parse_aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _age_hours(value: object, now: datetime) -> float | None:
    parsed = _parse_aware(value)
    if parsed is None:
        return None
    return max(0.0, (now.astimezone(timezone.utc) - parsed).total_seconds() / 3600.0)


def _fresh(age: float | None, limit: float) -> bool:
    return age is not None and age <= limit


def audit_freshness_gap(
    releases: dict[str, Any],
    promos: dict[str, Any],
    ig_snapshot: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    releases_age = _age_hours(releases.get("updated_at"), current)
    promos_age = _age_hours(promos.get("updated_at"), current)
    ig_age = _age_hours(ig_snapshot.get("built_at"), current)

    shared_fresh = (
        _fresh(releases_age, MAX_SHARED_AGE_HOURS)
        and _fresh(promos_age, MAX_SHARED_AGE_HOURS)
    )
    ig_fresh = (
        ig_snapshot.get("namespace") == "IG_CARDINFO"
        and ig_snapshot.get("status") == "finalized"
        and _fresh(ig_age, MAX_IG_SNAPSHOT_AGE_HOURS)
    )

    if ig_fresh:
        status = "NO_IG_FRESHNESS_GAP"
        error_code = None
        next_action = "CONTINUE_NORMAL_IG_COLLECTION_HEALTH_GATE"
        ig_local_refresh_required = False
    elif shared_fresh:
        status = "IG_LOCAL_CAPTURE_PERSISTENCE_LAG"
        error_code = "IG_SNAPSHOT_STALE_WHILE_SHARED_COLLECTION_FRESH"
        next_action = (
            "RUN_BOUNDED_IG_LOCAL_SOURCE_CAPTURE_VERIFY_AND_PERSIST; "
            "DO_NOT_PROMOTE_SHARED_ROWS_DIRECTLY"
        )
        ig_local_refresh_required = True
    else:
        status = "UPSTREAM_AND_IG_FRESHNESS_UNRESOLVED"
        error_code = "IG_AND_SHARED_COLLECTION_NOT_FRESH"
        next_action = (
            "REFRESH_SHARED_DISCOVERY_IF_NEEDED_THEN_RUN_BOUNDED_IG_LOCAL_CAPTURE; "
            "KEEP_VERIFICATION_FAIL_CLOSED"
        )
        ig_local_refresh_required = True

    return {
        "schema_version": 1,
        "project": "instagram_card",
        "status": status,
        "error_code": error_code,
        "checked_at": current.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "shared_collection": {
            "releases_updated_at": releases.get("updated_at"),
            "releases_age_hours": None if releases_age is None else round(releases_age, 2),
            "promo_events_updated_at": promos.get("updated_at"),
            "promo_events_age_hours": None if promos_age is None else round(promos_age, 2),
            "fresh": shared_fresh,
            "verification_authority": False,
            "promotion_to_ig_verified_fact_allowed": False,
        },
        "ig_snapshot": {
            "built_at": ig_snapshot.get("built_at"),
            "age_hours": None if ig_age is None else round(ig_age, 2),
            "fresh": ig_fresh,
            "fact_count": len(ig_snapshot.get("facts") or [])
            if isinstance(ig_snapshot.get("facts"), list)
            else 0,
        },
        "ig_local_refresh_required": ig_local_refresh_required,
        "verification_mode_must_remain": "INSTAGRAM_LOCAL_EVIDENCE_ONLY",
        "required_verification_entrypoint": (
            "instagram_tcg_content.source_verification_engine.py::verify_fact"
        ),
        "required_persistence_entrypoint": (
            "instagram_tcg_content/persisted_crosscheck_export.py"
        ),
        "next_action": next_action,
    }


def audit_files(
    releases_path: Path = DEFAULT_RELEASES,
    promos_path: Path = DEFAULT_PROMOS,
    ig_snapshot_path: Path = DEFAULT_IG_SNAPSHOT,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    return audit_freshness_gap(
        _load(releases_path),
        _load(promos_path),
        _load(ig_snapshot_path),
        now=now,
    )


def self_test() -> None:
    now = datetime(2026, 9, 10, 11, 30, tzinfo=timezone.utc)
    shared_release = {"updated_at": "2026-09-10T08:25:54+00:00"}
    shared_promo = {"updated_at": "2026-09-10T08:26:28+00:00"}
    stale_ig = {
        "namespace": "IG_CARDINFO",
        "status": "finalized",
        "built_at": "2026-09-06T21:25:43+09:00",
        "facts": [{}],
    }
    lag = audit_freshness_gap(shared_release, shared_promo, stale_ig, now=now)
    assert lag["status"] == "IG_LOCAL_CAPTURE_PERSISTENCE_LAG", lag
    assert lag["ig_local_refresh_required"] is True, lag
    assert lag["shared_collection"]["promotion_to_ig_verified_fact_allowed"] is False, lag

    fresh_ig = dict(stale_ig)
    fresh_ig["built_at"] = "2026-09-10T19:00:00+09:00"
    good = audit_freshness_gap(shared_release, shared_promo, fresh_ig, now=now)
    assert good["status"] == "NO_IG_FRESHNESS_GAP", good
    assert good["ig_local_refresh_required"] is False, good

    stale_shared = {"updated_at": "2026-09-08T00:00:00+00:00"}
    unresolved = audit_freshness_gap(stale_shared, stale_shared, stale_ig, now=now)
    assert unresolved["status"] == "UPSTREAM_AND_IG_FRESHNESS_UNRESOLVED", unresolved
    assert unresolved["ig_local_refresh_required"] is True, unresolved
    print("Instagram card collection freshness gap guard: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--releases", default=str(DEFAULT_RELEASES))
    parser.add_argument("--promos", default=str(DEFAULT_PROMOS))
    parser.add_argument("--snapshot", default=str(DEFAULT_IG_SNAPSHOT))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    report = audit_files(
        Path(args.releases),
        Path(args.promos),
        Path(args.snapshot),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if args.strict and report["ig_local_refresh_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
