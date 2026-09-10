#!/usr/bin/env python3
"""Bounded Instagram-card collection recovery orchestration.

This module closes the recovery loop between source capture, strict verification,
and factual-snapshot persistence. It deliberately does *not* scrape the web by
itself: the caller/automation supplies raw Instagram-local source observations.
Shared/Main snapshots can be used as discovery diagnostics elsewhere, but rows
from those scopes are rejected here and never become verified IG facts.

Two modes are provided:
- --plan: emit the exact capture matrix/provider requirements for a bounded run.
- --input: validate a raw capture packet, call source_verification_engine.verify_fact
  for each canonical group, merge only still-fresh previously verified IG facts,
  atomically persist the snapshot, and run collection_health on the result.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from instagram_tcg_content.collection_health import (
    EXPECTED_OUTPUTS,
    MAX_SNAPSHOT_AGE_HOURS,
    MIN_COMPLETED_SALES_PER_OUTPUT,
    audit_collection,
)
from instagram_tcg_content.persisted_crosscheck_export import (
    VERIFICATION_ENGINE,
    VERIFICATION_MODE,
    export_snapshot,
)
from instagram_tcg_content.source_verification_engine import Observation, verify_fact

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROUTES = ROOT / "instagram_tcg_content" / "source_routes.json"
DEFAULT_SNAPSHOT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"
PROJECT = "instagram_card"
TASK_ID = "6a9b8a22e72c8191849c273e1240378e"
EVIDENCE_SCOPE = "instagram_local_source_capture"
PERSISTABLE_FACT_TYPES = {
    "official_release",
    "official_reprint",
    "official_promo",
    "official_event",
    "official_movie_bonus",
    "completed_sale",
    "market_reference",
}


def _aware(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_routes(path: Path) -> dict[str, Any]:
    value = _load_json(path)
    if not isinstance(value, dict) or not isinstance(value.get("provider_groups"), dict):
        raise ValueError("invalid source route configuration")
    return value


def build_capture_plan(routes: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded capture contract; this grants no verification authority."""
    groups = routes.get("provider_groups") or {}
    cells: list[dict[str, Any]] = []
    for game, language in EXPECTED_OUTPUTS:
        group = groups.get(game) if isinstance(groups, dict) else None
        if not isinstance(group, dict):
            group = {}
        realized = list(dict.fromkeys(
            list(group.get("completed_sale_original") or [])
            + list(group.get("grading_auction_original") or [])
        ))
        cells.append({
            "game": game,
            "language": language,
            "official_primary_candidates": list(group.get("official_primary") or []),
            "completed_sale_candidates": realized,
            "market_reference_candidates": list(group.get("market_reference") or []),
            "required_general_verified_facts": 1,
            "required_completed_sales": MIN_COMPLETED_SALES_PER_OUTPUT,
            "required_independent_completed_sale_providers_per_fact": 2,
            "required_independent_market_reference_providers_per_fact": 2,
        })
    return {
        "schema_version": 1,
        "project": PROJECT,
        "task_id": TASK_ID,
        "mode": "BOUNDED_IG_LOCAL_CAPTURE_PLAN",
        "verification_mode": VERIFICATION_MODE,
        "evidence_scope_required": EVIDENCE_SCOPE,
        "output_cells": cells,
        "official_fact_types": [
            "official_release",
            "official_reprint",
            "official_promo",
            "official_event",
            "official_movie_bonus",
        ],
        "shared_or_main_rows_can_verify": False,
        "direct_promotion_of_shared_rows_allowed": False,
        "verification_entrypoint": "instagram_tcg_content.source_verification_engine.py::verify_fact",
        "persistence_entrypoint": "instagram_tcg_content.persisted_crosscheck_export.py",
    }


def _packet_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    if packet.get("project") != PROJECT:
        raise ValueError("capture packet project mismatch")
    if packet.get("task_id") != TASK_ID:
        raise ValueError("capture packet task_id mismatch")
    if packet.get("verification_mode") != VERIFICATION_MODE:
        raise ValueError("capture packet verification mode mismatch")
    rows = packet.get("observations")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("capture packet observations must be a list of objects")
    return rows


def _route_reason(row: dict[str, Any], routes: dict[str, Any]) -> str | None:
    if row.get("evidence_scope") != EVIDENCE_SCOPE:
        return "NON_IG_LOCAL_EVIDENCE_SCOPE"
    game = str(row.get("game") or "").strip().lower()
    fact_type = str(row.get("fact_type") or "").strip()
    source_tier = str(row.get("source_tier") or "").strip()
    provider_id = str(row.get("provider_id") or "").strip()
    language = str(row.get("language") or "").strip().upper()
    if game not in {game_name for game_name, _ in EXPECTED_OUTPUTS}:
        return "UNSUPPORTED_GAME"
    if language not in {language_name for _, language_name in EXPECTED_OUTPUTS}:
        return "UNSUPPORTED_LANGUAGE"
    if fact_type not in PERSISTABLE_FACT_TYPES:
        return "UNSUPPORTED_FACT_TYPE"
    allowed_tiers = routes.get("routes", {}).get(fact_type)
    if not isinstance(allowed_tiers, list) or source_tier not in allowed_tiers:
        return "SOURCE_TIER_NOT_ALLOWED_FOR_FACT"
    game_group = routes.get("provider_groups", {}).get(game)
    if not isinstance(game_group, dict):
        return "PROVIDER_GROUP_MISSING"
    configured = game_group.get(source_tier)
    if not isinstance(configured, list) or provider_id not in configured:
        return "PROVIDER_NOT_CONFIGURED_FOR_GAME_TIER"
    return None


def _to_observation(row: dict[str, Any]) -> Observation:
    quantity = row.get("quantity")
    if quantity is not None and (isinstance(quantity, bool) or not isinstance(quantity, int)):
        quantity = None
    return Observation(
        game=str(row.get("game") or "").strip().lower(),
        fact_type=str(row.get("fact_type") or "").strip(),
        canonical_key=str(row.get("canonical_key") or "").strip(),
        value=str(row.get("value") or "").strip(),
        source_code=str(row.get("source_code") or "").strip(),
        source_name=str(row.get("source_name") or "").strip(),
        source_locator=str(row.get("source_locator") or "").strip(),
        source_tier=str(row.get("source_tier") or "").strip(),
        collector_id=str(row.get("collector_id") or "").strip(),
        provider_id=str(row.get("provider_id") or "").strip(),
        fetched_at_kst=str(row.get("fetched_at_kst") or "").strip(),
        event_or_trade_time=(str(row.get("event_or_trade_time")).strip() if row.get("event_or_trade_time") else None),
        status=str(row.get("status") or "observed").strip(),
        original_currency=(str(row.get("original_currency")).strip() if row.get("original_currency") else None),
        condition=(str(row.get("condition")).strip() if row.get("condition") else None),
        grade=(str(row.get("grade")).strip() if row.get("grade") else None),
        finality=(str(row.get("finality")).strip() if row.get("finality") else None),
        price_basis=(str(row.get("price_basis")).strip() if row.get("price_basis") else None),
        quantity=quantity,
        unit=(str(row.get("unit")).strip() if row.get("unit") else None),
        lineage_key=(str(row.get("lineage_key")).strip() if row.get("lineage_key") else None),
    )


def _group_lineage(rows: Iterable[Observation]) -> str:
    parts = sorted(
        "|".join((
            row.provider_id,
            row.lineage_key or "",
            row.source_locator,
            row.value,
        ))
        for row in rows
    )
    return "ig-group:" + sha256("\n".join(parts).encode("utf-8", "replace")).hexdigest()[:24]


def _latest_representative(rows: list[tuple[dict[str, Any], Observation]], canonical_value: str | None) -> tuple[dict[str, Any], Observation]:
    matching = [pair for pair in rows if canonical_value is None or pair[1].value == canonical_value]
    if not matching:
        matching = rows

    def key(pair: tuple[dict[str, Any], Observation]) -> datetime:
        raw, obs = pair
        return (
            _aware(obs.event_or_trade_time)
            or _aware(obs.fetched_at_kst)
            or datetime.min.replace(tzinfo=timezone.utc)
        )

    return max(matching, key=key)


def _verified_record(
    pairs: list[tuple[dict[str, Any], Observation]],
    canonical_value: str | None,
) -> dict[str, Any]:
    raw, representative = _latest_representative(pairs, canonical_value)
    observations = [obs for _, obs in pairs]
    fetched = [stamp for obs in observations if (stamp := _aware(obs.fetched_at_kst)) is not None]
    observed_at = max(fetched).isoformat(timespec="seconds") if fetched else representative.fetched_at_kst
    event_stamp = _aware(representative.event_or_trade_time)
    effective_date = str(raw.get("effective_date") or "").strip()
    if not effective_date and event_stamp is not None:
        effective_date = event_stamp.date().isoformat()
    identity = raw.get("identity")
    if not isinstance(identity, dict):
        identity = {
            "game": representative.game,
            "name": representative.canonical_key,
            "language": str(raw.get("language") or "").strip().upper(),
        }
    else:
        identity = dict(identity)
    identity["game"] = representative.game
    identity["language"] = str(raw.get("language") or "").strip().upper()
    identity["verification_provider_count"] = len({obs.provider_id for obs in observations})
    return {
        "information_family": representative.fact_type,
        "canonical_key": representative.canonical_key,
        "lineage_key": _group_lineage(observations),
        "identity": identity,
        "value": canonical_value,
        "value_type": str(raw.get("value_type") or "text").strip(),
        "currency": str(representative.original_currency or raw.get("currency") or "").strip(),
        "region": str(raw.get("region") or "").strip().upper(),
        "language": str(raw.get("language") or "").strip().upper(),
        "condition": str(representative.condition or "").strip(),
        "grade_company": str(raw.get("grade_company") or "").strip(),
        "grade": str(representative.grade or "").strip(),
        "effective_date": effective_date,
        "checked_at_kst": observed_at,
        "source_role": "verified_observation_group",
        "source_locator": representative.source_locator,
        "verification": "verified",
        "verification_mode": VERIFICATION_MODE,
        "verification_engine": VERIFICATION_ENGINE,
    }


def _fresh_existing_facts(snapshot_path: Path, *, now: datetime) -> list[dict[str, Any]]:
    if not snapshot_path.is_file():
        return []
    try:
        value = _load_json(snapshot_path)
    except (OSError, ValueError, UnicodeError, TypeError):
        return []
    if not isinstance(value, dict) or value.get("namespace") != "IG_CARDINFO":
        return []
    validation = value.get("validation")
    if not isinstance(validation, dict) or validation.get("write_readback_verified") is not True:
        return []
    rows = value.get("facts")
    if not isinstance(rows, list):
        return []
    current = now.astimezone(timezone.utc)
    fresh: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("verification_status") != "verified":
            continue
        if row.get("verification_mode") != VERIFICATION_MODE or row.get("verification_engine") != VERIFICATION_ENGINE:
            continue
        observed = _aware(row.get("observed_at"))
        if observed is None:
            continue
        age_hours = (current - observed.astimezone(timezone.utc)).total_seconds() / 3600.0
        if age_hours < 0 or age_hours > MAX_SNAPSHOT_AGE_HOURS:
            continue
        fresh.append(dict(row))
    return fresh


def _dedupe_records(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("canonical_key") or ""),
            str(row.get("information_family") or row.get("fact_type") or ""),
            str(row.get("lineage_key") or ""),
        )
        if not all(key) or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def run_recovery(
    packet: dict[str, Any],
    *,
    routes: dict[str, Any],
    output: Path = DEFAULT_SNAPSHOT,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    rows = _packet_rows(packet)
    accepted: list[tuple[dict[str, Any], Observation]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        reason = _route_reason(raw, routes)
        if reason:
            rejected.append({"index": index, "reason": reason})
            continue
        accepted.append((raw, _to_observation(raw)))

    grouped: dict[tuple[str, str, str], list[tuple[dict[str, Any], Observation]]] = defaultdict(list)
    for raw, obs in accepted:
        grouped[(obs.game, obs.fact_type, obs.canonical_key)].append((raw, obs))

    verified_records: list[dict[str, Any]] = []
    verification_rows: list[dict[str, Any]] = []
    for group_key, pairs in sorted(grouped.items()):
        languages = {str(raw.get("language") or "").strip().upper() for raw, _ in pairs}
        regions = {str(raw.get("region") or "").strip().upper() for raw, _ in pairs}
        if len(languages) != 1 or len(regions) > 1:
            verification_rows.append({
                "group": list(group_key),
                "status": "conflict",
                "reason": "GROUP_LANGUAGE_OR_REGION_MISMATCH",
            })
            continue
        result = verify_fact([obs for _, obs in pairs], now=current)
        verification_rows.append({
            "group": list(group_key),
            "status": result.status,
            "canonical_value": result.canonical_value,
            "source_count": result.source_count,
            "independent_source_count": result.independent_source_count,
            "uncertainty_reason": result.uncertainty_reason,
        })
        if result.status == "verified":
            verified_records.append(_verified_record(pairs, result.canonical_value))

    existing = _fresh_existing_facts(output, now=current)
    combined = _dedupe_records([*existing, *verified_records])
    snapshot = export_snapshot(combined, output)
    health = audit_collection(snapshot, routes, now=current)
    return {
        "schema_version": 1,
        "project": PROJECT,
        "task_id": TASK_ID,
        "status": "READY" if health.get("general_cardinfo_ready") else "NOT_READY",
        "attempted_observation_count": len(rows),
        "accepted_observation_count": len(accepted),
        "rejected_observations": rejected,
        "verification_group_count": len(grouped),
        "verified_group_count": len(verified_records),
        "fresh_existing_fact_count": len(existing),
        "persisted_fact_count": len(snapshot.get("facts") or []),
        "collection_health": health,
        "verification_results": verification_rows,
        "verification_mode": VERIFICATION_MODE,
        "shared_or_main_rows_promoted": False,
        "next_action": health.get("next_action"),
    }


def self_test() -> None:
    routes = _load_routes(DEFAULT_ROUTES)
    plan = build_capture_plan(routes)
    assert len(plan["output_cells"]) == 6
    assert plan["shared_or_main_rows_can_verify"] is False
    print("Instagram collection recovery runner: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--routes", default=str(DEFAULT_ROUTES))
    parser.add_argument("--output", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    routes = _load_routes(Path(args.routes))
    if args.self_test:
        self_test()
        return 0
    if args.plan:
        print(json.dumps(build_capture_plan(routes), ensure_ascii=False, indent=2))
        return 0
    if not args.input:
        raise SystemExit("--input or --plan is required")
    packet = _load_json(Path(args.input))
    if not isinstance(packet, dict):
        raise SystemExit("capture packet must be a JSON object")
    report = run_recovery(packet, routes=routes, output=Path(args.output))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
