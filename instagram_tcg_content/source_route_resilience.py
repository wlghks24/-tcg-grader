#!/usr/bin/env python3
"""Resilient multi-route planner for Instagram TCG content.

403/429 are never bypassed. Affected providers are cooled down and independent
routes are substituted while the failed route remains auditable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

KST = timezone(timedelta(hours=9))
HEALTHY = {"ok", "fresh"}
SOFT_FAIL = {"timeout", "parser_error", "stale", "empty", "rate_limited", "forbidden"}
HARD_FAIL = {"invalid_provenance", "identity_mismatch", "security_block", "quarantined"}
KNOWN_STATUSES = HEALTHY | SOFT_FAIL | HARD_FAIL
KNOWN_TIERS = {
    "official_primary",
    "official_secondary",
    "completed_sale_original",
    "grading_auction_original",
    "market_reference",
    "discovery_lead",
}


@dataclass(frozen=True)
class ProviderState:
    provider_id: str
    tier: str
    status: str = "ok"
    failure_count: int = 0
    cooldown_until_kst: str | None = None
    parser_id: str = "default"


@dataclass(frozen=True)
class RouteDecision:
    selected: tuple[str, ...]
    skipped: tuple[str, ...]
    reason: str
    independent_target: int


def required_independent_sources(fact_type: str) -> int:
    if fact_type in {"completed_sale", "market_reference"}:
        return 2
    if fact_type.startswith("official_") or fact_type == "fx":
        return 1
    return 2


def tier_satisfies_fact(fact_type: str, tier: str) -> bool:
    if fact_type == "completed_sale":
        return tier in {"completed_sale_original", "grading_auction_original"}
    if fact_type == "market_reference":
        return tier == "market_reference"
    if fact_type.startswith("official_"):
        return tier == "official_primary"
    if fact_type == "fx":
        return tier in {"official_primary", "market_reference"}
    return tier not in {"discovery_lead"}


def _parse_aware(value: str | None, field: str) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _validate_state(state: ProviderState) -> None:
    if not isinstance(state, ProviderState):
        raise ValueError("PROVIDER_STATE_REQUIRED")
    if not isinstance(state.provider_id, str) or not state.provider_id.strip():
        raise ValueError("PROVIDER_ID_REQUIRED")
    if state.tier not in KNOWN_TIERS:
        raise ValueError("UNKNOWN_PROVIDER_TIER")
    if state.status not in KNOWN_STATUSES:
        raise ValueError("UNKNOWN_PROVIDER_STATUS")
    if isinstance(state.failure_count, bool) or not isinstance(state.failure_count, int) or state.failure_count < 0:
        raise ValueError("INVALID_FAILURE_COUNT")
    if not isinstance(state.parser_id, str) or not state.parser_id.strip():
        raise ValueError("PARSER_ID_REQUIRED")
    _parse_aware(state.cooldown_until_kst, "cooldown_until_kst")


def _route_eligible(state: ProviderState, *, now: datetime) -> bool:
    if state.status in HARD_FAIL or state.failure_count >= 3:
        return False

    cooldown = _parse_aware(state.cooldown_until_kst, "cooldown_until_kst")
    current = now.astimezone(timezone.utc)
    if cooldown is not None and current < cooldown:
        return False

    # 403/429 without a bounded cooldown must not be retried. After an explicit
    # cooldown expires they may re-enter only as degraded fallbacks.
    if state.status in {"rate_limited", "forbidden"} and cooldown is None:
        return False
    return True


def _priority(state: ProviderState) -> tuple[int, int, str]:
    tier_rank = {
        "official_primary": 0,
        "completed_sale_original": 1,
        "grading_auction_original": 2,
        "official_secondary": 3,
        "market_reference": 4,
        "discovery_lead": 5,
    }.get(state.tier, 99)
    health_penalty = 0 if state.status in HEALTHY else 10
    return (tier_rank + health_penalty, state.failure_count, state.provider_id)


def choose_routes(
    fact_type: str,
    states: Sequence[ProviderState],
    *,
    max_routes: int = 4,
    now_kst: str | None = None,
) -> RouteDecision:
    if not isinstance(fact_type, str) or not fact_type.strip():
        raise ValueError("FACT_TYPE_REQUIRED")
    if isinstance(max_routes, bool) or not isinstance(max_routes, int) or not 1 <= max_routes <= 8:
        raise ValueError("MAX_ROUTES_OUT_OF_RANGE")
    if not isinstance(states, Sequence):
        raise ValueError("PROVIDER_STATES_REQUIRED")

    current = (
        _parse_aware(now_kst, "now_kst")
        if now_kst is not None
        else datetime.now(timezone.utc)
    )
    assert current is not None

    seen_provider_ids: set[str] = set()
    normalized: list[ProviderState] = []
    for state in normalized:
        _validate_state(state)
        provider_id = state.provider_id.strip()
        if provider_id in seen_provider_ids:
            raise ValueError("DUPLICATE_PROVIDER_STATE")
        seen_provider_ids.add(provider_id)
        normalized.append(state)

    target = required_independent_sources(fact_type)
    eligible = sorted(
        (s for s in normalized if _route_eligible(s, now=current)),
        key=_priority,
    )

    proving = [s for s in eligible if tier_satisfies_fact(fact_type, s.tier)]
    supporting = [s for s in eligible if not tier_satisfies_fact(fact_type, s.tier)]

    selected: list[str] = []
    skipped: list[str] = []
    selected_set: set[str] = set()
    skipped_set: set[str] = set()
    route_budget = min(max_routes, target)

    # Healthy/eligible proving routes are sufficient once the independent target
    # is met. Do not contact extra providers just because max_routes is larger.
    for state in proving:
        if state.provider_id in selected_set:
            if state.provider_id not in skipped_set:
                skipped.append(state.provider_id)
                skipped_set.add(state.provider_id)
            continue
        selected.append(state.provider_id)
        selected_set.add(state.provider_id)
        if len(selected) >= route_budget:
            break

    # Supporting routes are diagnostic fallbacks only when qualifying evidence is
    # insufficient; they never inflate the independent-evidence count.
    if len(selected) < route_budget:
        for state in supporting:
            if state.provider_id in selected_set:
                continue
            selected.append(state.provider_id)
            selected_set.add(state.provider_id)
            if len(selected) >= route_budget:
                break

    for state in states:
        if state.provider_id not in selected_set and state.provider_id not in skipped_set:
            skipped.append(state.provider_id)
            skipped_set.add(state.provider_id)

    proving_selected = {
        s.provider_id
        for s in eligible
        if s.provider_id in selected_set
        and tier_satisfies_fact(fact_type, s.tier)
    }
    if len(proving_selected) < target:
        reason = f"insufficient qualifying independent routes: {len(proving_selected)}/{target}"
    elif any(s.status in SOFT_FAIL for s in normalized if s.provider_id in proving_selected):
        reason = "qualifying fallback route included after healthier alternatives were exhausted"
    else:
        reason = "qualifying independent route target satisfied"

    return RouteDecision(tuple(selected), tuple(skipped), reason, target)


def next_strategy(status: str, failure_count: int) -> str:
    if status not in KNOWN_STATUSES:
        raise ValueError("UNKNOWN_PROVIDER_STATUS")
    if isinstance(failure_count, bool) or not isinstance(failure_count, int) or failure_count < 0:
        raise ValueError("INVALID_FAILURE_COUNT")
    if status in {"rate_limited", "forbidden"}:
        return "respect_retry_after_then_alternate_provider"
    if status == "parser_error":
        return "alternate_parser_then_alternate_provider"
    if status in {"timeout", "empty", "stale"}:
        return "alternate_provider_then_recheck_primary"
    if status in HARD_FAIL or failure_count >= 3:
        return "quarantine_and_exclude"
    return "same_provider_once_then_alternate"


def coverage_ok(
    fact_type: str,
    successful_states: Iterable[ProviderState],
) -> bool:
    if not isinstance(fact_type, str) or not fact_type.strip():
        raise ValueError("FACT_TYPE_REQUIRED")
    rows = list(successful_states)
    seen_provider_ids: set[str] = set()
    for state in rows:
        _validate_state(state)
        provider_id = state.provider_id.strip()
        if provider_id in seen_provider_ids:
            raise ValueError("DUPLICATE_PROVIDER_STATE")
        seen_provider_ids.add(provider_id)

    # Cooldown affects whether a provider may be contacted again, not whether a
    # previously captured healthy evidence item remains valid for coverage.
    qualifying = {
        state.provider_id
        for state in rows
        if state.status in HEALTHY
        and state.failure_count < 3
        and tier_satisfies_fact(fact_type, state.tier)
    }
    return len(qualifying) >= required_independent_sources(fact_type)
