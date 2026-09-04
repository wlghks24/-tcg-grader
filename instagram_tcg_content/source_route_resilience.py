#!/usr/bin/env python3
"""Resilient multi-route collection planner for Instagram TCG content.

Keeps source substitution explicit, auditable, and fail-closed. It never bypasses
403/429; blocked providers are cooled down and replaced with independent routes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

HEALTHY = {"ok", "fresh"}
SOFT_FAIL = {"timeout", "parser_error", "stale", "empty", "rate_limited", "forbidden"}
HARD_FAIL = {"invalid_provenance", "identity_mismatch", "security_block", "quarantined"}


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
    if fact_type == "completed_sale":
        return 2
    if fact_type == "market_reference":
        return 2
    if fact_type.startswith("official_"):
        return 1
    if fact_type == "fx":
        return 1
    return 2


def _eligible(state: ProviderState) -> bool:
    if state.status in HARD_FAIL:
        return False
    if state.failure_count >= 3:
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


def choose_routes(fact_type: str, states: Sequence[ProviderState], *, max_routes: int = 4) -> RouteDecision:
    """Choose independent providers with automatic substitution.

    Failed/blocked/stale routes are not treated as success. They may remain as a
    fallback candidate only while failure_count < 3, after healthy independent routes.
    """
    target = required_independent_sources(fact_type)
    eligible = sorted((s for s in states if _eligible(s)), key=_priority)
    selected: list[str] = []
    skipped: list[str] = []
    seen: set[str] = set()

    for state in eligible:
        if state.provider_id in seen:
            skipped.append(state.provider_id)
            continue
        seen.add(state.provider_id)
        if state.status in HARD_FAIL:
            skipped.append(state.provider_id)
            continue
        selected.append(state.provider_id)
        if len(selected) >= max(target, min(max_routes, target + 2)):
            break

    for state in states:
        if state.provider_id not in selected and state.provider_id not in skipped:
            skipped.append(state.provider_id)

    if len(selected) < target:
        reason = f"insufficient independent routes: {len(selected)}/{target}"
    elif any(s.status in SOFT_FAIL for s in states if s.provider_id in selected):
        reason = "fallback route included after healthier alternatives were exhausted"
    else:
        reason = "independent route target satisfied"
    return RouteDecision(tuple(selected), tuple(skipped), reason, target)


def next_strategy(status: str, failure_count: int) -> str:
    """Deterministic substitution policy used by SELF-HEAL."""
    if status in {"rate_limited", "forbidden"}:
        return "respect_retry_after_then_alternate_provider"
    if status == "parser_error":
        return "alternate_parser_then_alternate_provider"
    if status in {"timeout", "empty", "stale"}:
        return "alternate_provider_then_recheck_primary"
    if status in HARD_FAIL or failure_count >= 3:
        return "quarantine_and_exclude"
    return "same_provider_once_then_alternate"


def coverage_ok(fact_type: str, successful_provider_ids: Iterable[str]) -> bool:
    return len(set(successful_provider_ids)) >= required_independent_sources(fact_type)
