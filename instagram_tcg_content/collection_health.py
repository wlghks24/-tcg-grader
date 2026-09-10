#!/usr/bin/env python3
"""Instagram-card collection readiness audit.

This module is read-only. It never fetches sources and never mutates scheduler
state. It exposes two independent readiness levels:
- general_cardinfo_ready: verified release/rerelease/promo/event/movie/card news
  may be produced even when completed-sale coverage is still incomplete.
- market_price_ready: strict completed-sale and market-reference coverage.

Unverified facts never become production-ready in either mode.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "factual_snapshot.json"
DEFAULT_ROUTES = ROOT / "instagram_tcg_content" / "source_routes.json"
KST = timezone(timedelta(hours=9))
EXPECTED_OUTPUTS = (
    ("pokemon", "KR"),
    ("pokemon", "EN"),
    ("one_piece", "KR"),
    ("one_piece", "EN"),
    ("naruto", "KR"),
    ("naruto", "EN"),
)
MAX_SNAPSHOT_AGE_HOURS = 36.0
MIN_COMPLETED_SALES_PER_OUTPUT = 10
VERIFICATION_MODE = "INSTAGRAM_LOCAL_EVIDENCE_ONLY"
VERIFICATION_ENGINE = "instagram_tcg_content.source_verification_engine.py::verify_fact"

MARKET_ONLY_REASON_PREFIXES = (
    "COMPLETED_SALE_COVERAGE_INSUFFICIENT",
    "COMPLETED_SALE_ROUTE_SHORTAGE:",
    "MARKET_ROUTE_SHORTAGE:",
)


def _parse_aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _game_of(row: dict[str, Any]) -> str:
    identity = row.get("identity")
    if isinstance(identity, dict):
        game = identity.get("game")
        if isinstance(game, str) and game.strip():
            return game.strip().lower()
    canonical = row.get("canonical_key")
    if isinstance(canonical, str) and canonical.strip():
        return canonical.split("|", 1)[0].strip().lower()
    return ""


def _language_of(row: dict[str, Any]) -> str:
    value = row.get("language")
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    identity = row.get("identity")
    if isinstance(identity, dict):
        value = identity.get("language")
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return ""


def _validate_routes(routes: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    groups = routes.get("provider_groups")
    if not isinstance(groups, dict):
        return ["PROVIDER_GROUPS_MISSING"]
    for game in ("pokemon", "one_piece", "naruto"):
        group = groups.get(game)
        if not isinstance(group, dict):
            problems.append(f"PROVIDER_GROUP_MISSING:{game}")
            continue
        official = set(group.get("official_primary") or [])
        realized = set(group.get("completed_sale_original") or []) | set(
            group.get("grading_auction_original") or []
        )
        market = set(group.get("market_reference") or [])
        if len(official) < 1:
            problems.append(f"OFFICIAL_ROUTE_SHORTAGE:{game}:{len(official)}/1")
        if len(realized) < 2:
            problems.append(f"COMPLETED_SALE_ROUTE_SHORTAGE:{game}:{len(realized)}/2")
        if len(market) < 2:
            problems.append(f"MARKET_ROUTE_SHORTAGE:{game}:{len(market)}/2")
    return problems


def _is_market_only_reason(reason: str) -> bool:
    return any(reason == prefix or reason.startswith(prefix) for prefix in MARKET_ONLY_REASON_PREFIXES)


def audit_collection(
    snapshot: dict[str, Any],
    routes: dict[str, Any],
    *,
    now: datetime | None = None,
    min_completed_sales_per_output: int = MIN_COMPLETED_SALES_PER_OUTPUT,
) -> dict[str, Any]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if isinstance(min_completed_sales_per_output, bool) or min_completed_sales_per_output < 1:
        raise ValueError("min_completed_sales_per_output must be >=1")

    reasons: list[str] = []
    if snapshot.get("namespace") != "IG_CARDINFO":
        reasons.append("SNAPSHOT_NAMESPACE_INVALID")
    if snapshot.get("status") != "finalized":
        reasons.append("SNAPSHOT_NOT_FINALIZED")
    validation = snapshot.get("validation")
    if not isinstance(validation, dict) or validation.get("write_readback_verified") is not True:
        reasons.append("SNAPSHOT_WRITE_READBACK_UNVERIFIED")

    built_at = _parse_aware(snapshot.get("built_at"))
    age_hours: float | None = None
    if built_at is None:
        reasons.append("SNAPSHOT_BUILT_AT_INVALID")
    else:
        age_hours = max(0.0, (current.astimezone(timezone.utc) - built_at.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if age_hours > MAX_SNAPSHOT_AGE_HOURS:
            reasons.append(f"SNAPSHOT_STALE:{age_hours:.1f}h>{MAX_SNAPSHOT_AGE_HOURS:.0f}h")

    latest_attempt = snapshot.get("latest_attempt")
    if isinstance(latest_attempt, dict):
        attempt_status = str(latest_attempt.get("status") or "")
        if attempt_status not in {"", "finalized", "verified_facts_written"}:
            reasons.append(f"LATEST_COLLECTION_ATTEMPT_NOT_READY:{attempt_status}")

    facts = snapshot.get("facts")
    if not isinstance(facts, list):
        facts = []
        reasons.append("SNAPSHOT_FACTS_INVALID")

    duplicate_keys: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    matrix_counts: Counter[tuple[str, str]] = Counter()
    completed_counts: Counter[tuple[str, str]] = Counter()
    malformed_count = 0
    for raw in facts:
        if not isinstance(raw, dict):
            malformed_count += 1
            continue
        key = str(raw.get("canonical_key") or "")
        fact_type = str(raw.get("fact_type") or "")
        lineage = str(raw.get("lineage_key") or "")
        if not key or not fact_type or not lineage or raw.get("verification_status") != "verified":
            malformed_count += 1
            continue
        if raw.get("verification_mode") != VERIFICATION_MODE or raw.get("verification_engine") != VERIFICATION_ENGINE:
            malformed_count += 1
            continue
        dedupe_key = (key, fact_type, lineage)
        if dedupe_key in seen:
            duplicate_keys.append("|".join(dedupe_key))
            continue
        seen.add(dedupe_key)
        game = _game_of(raw)
        language = _language_of(raw)
        if game and language:
            matrix_counts[(game, language)] += 1
            if fact_type == "completed_sale":
                completed_counts[(game, language)] += 1
        if not str(raw.get("source_locator") or "").strip():
            malformed_count += 1

    if malformed_count:
        reasons.append(f"MALFORMED_VERIFIED_FACTS:{malformed_count}")
    if duplicate_keys:
        reasons.append(f"DUPLICATE_FACT_LINEAGE:{len(duplicate_keys)}")
    if not facts:
        reasons.append("NO_VERIFIED_FACTS")

    missing_outputs = []
    completed_sale_shortage = {}
    for game, language in EXPECTED_OUTPUTS:
        count = matrix_counts[(game, language)]
        if count < 1:
            missing_outputs.append(f"{game}:{language}")
        completed = completed_counts[(game, language)]
        if completed < min_completed_sales_per_output:
            completed_sale_shortage[f"{game}:{language}"] = {
                "verified_completed_sales": completed,
                "required": min_completed_sales_per_output,
            }
    if missing_outputs:
        reasons.append("OUTPUT_MATRIX_COVERAGE_MISSING:" + ",".join(missing_outputs))
    if completed_sale_shortage:
        reasons.append("COMPLETED_SALE_COVERAGE_INSUFFICIENT")

    route_problems = _validate_routes(routes)
    reasons.extend(route_problems)

    unique_reasons = list(dict.fromkeys(reasons))
    general_blocking_reasons = [r for r in unique_reasons if not _is_market_only_reason(r)]
    market_blocking_reasons = list(unique_reasons)
    general_cardinfo_ready = not general_blocking_reasons
    market_price_ready = not market_blocking_reasons

    if general_cardinfo_ready and not market_price_ready:
        status = "GENERAL_READY_MARKET_NOT_READY"
        next_action = "PROCEED_GENERAL_CARDINFO_WITHOUT_UNVERIFIED_MARKET_SECTIONS"
    elif general_cardinfo_ready and market_price_ready:
        status = "READY"
        next_action = "PROCEED_TO_PRODUCTION_PREFLIGHT"
    else:
        status = "NOT_READY"
        next_action = "RUN_BOUNDED_FULL_COLLECTION_AND_PERSIST_VERIFIED_IG_FACTS"

    return {
        "status": status,
        "production_ready": general_cardinfo_ready,
        "general_cardinfo_ready": general_cardinfo_ready,
        "market_price_ready": market_price_ready,
        "snapshot_built_at": snapshot.get("built_at"),
        "snapshot_age_hours": None if age_hours is None else round(age_hours, 2),
        "fact_count": len(facts),
        "unique_fact_count": len(seen),
        "matrix_counts": {
            f"{game}:{language}": matrix_counts[(game, language)]
            for game, language in EXPECTED_OUTPUTS
        },
        "completed_sale_counts": {
            f"{game}:{language}": completed_counts[(game, language)]
            for game, language in EXPECTED_OUTPUTS
        },
        "completed_sale_shortage": completed_sale_shortage,
        "route_problems": route_problems,
        "reasons": unique_reasons,
        "general_blocking_reasons": general_blocking_reasons,
        "market_blocking_reasons": market_blocking_reasons,
        "next_action": next_action,
    }


def self_test() -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    routes = {
        "provider_groups": {
            game: {
                "official_primary": ["official"],
                "completed_sale_original": ["sale-a", "sale-b"],
                "grading_auction_original": [],
                "market_reference": ["market-a", "market-b"],
            }
            for game in ("pokemon", "one_piece", "naruto")
        }
    }
    facts = []
    official_only = []
    for game, language in EXPECTED_OUTPUTS:
        official = {
            "canonical_key": f"{game}|release|{language.lower()}",
            "fact_type": "release",
            "lineage_key": f"{game}:{language}:release",
            "identity": {"game": game, "language": language},
            "source_locator": "https://example.invalid/official",
            "verification_status": "verified",
            "verification_mode": VERIFICATION_MODE,
            "verification_engine": VERIFICATION_ENGINE,
        }
        facts.append(official)
        official_only.append(dict(official))
        for index in range(MIN_COMPLETED_SALES_PER_OUTPUT):
            facts.append({
                "canonical_key": f"{game}|sale-{index}|{language.lower()}",
                "fact_type": "completed_sale",
                "lineage_key": f"{game}:{language}:sale:{index}",
                "identity": {"game": game},
                "language": language,
                "source_locator": "https://example.invalid/sale",
                "verification_status": "verified",
                "verification_mode": VERIFICATION_MODE,
                "verification_engine": VERIFICATION_ENGINE,
            })
    snapshot = {
        "namespace": "IG_CARDINFO",
        "status": "finalized",
        "built_at": "2026-09-09T20:30:00+09:00",
        "facts": facts,
        "validation": {"write_readback_verified": True},
        "latest_attempt": {"status": "verified_facts_written"},
    }
    ready = audit_collection(snapshot, routes, now=now)
    assert ready["production_ready"] is True, ready
    assert ready["general_cardinfo_ready"] is True, ready
    assert ready["market_price_ready"] is True, ready

    general_snapshot = dict(snapshot)
    general_snapshot["facts"] = official_only
    general = audit_collection(general_snapshot, routes, now=now)
    assert general["production_ready"] is True, general
    assert general["general_cardinfo_ready"] is True, general
    assert general["market_price_ready"] is False, general
    assert general["status"] == "GENERAL_READY_MARKET_NOT_READY", general

    stale = dict(snapshot)
    stale["built_at"] = "2026-09-06T20:30:00+09:00"
    stale_report = audit_collection(stale, routes, now=now)
    assert stale_report["production_ready"] is False, stale_report
    assert stale_report["general_cardinfo_ready"] is False, stale_report
    assert any(reason.startswith("SNAPSHOT_STALE:") for reason in stale_report["reasons"])

    thin = dict(snapshot)
    thin["facts"] = facts[:1]
    thin_report = audit_collection(thin, routes, now=now)
    assert thin_report["production_ready"] is False, thin_report
    assert "COMPLETED_SALE_COVERAGE_INSUFFICIENT" in thin_report["reasons"], thin_report
    assert any(reason.startswith("OUTPUT_MATRIX_COVERAGE_MISSING:") for reason in thin_report["reasons"])

    print("Instagram TCG collection health: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--routes", default=str(DEFAULT_ROUTES))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    routes = json.loads(Path(args.routes).read_text(encoding="utf-8"))
    report = audit_collection(snapshot, routes)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if args.strict and not report["production_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
