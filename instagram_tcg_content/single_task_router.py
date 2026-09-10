#!/usr/bin/env python3
"""Single-task schedule/taxonomy policy for Instagram card information.

Canonical runtime contract:
* One active automation runs hourly on the hour in Asia/Seoul.
* Monday 19:00 KST is the only final-production slot.
* Every other hourly slot is collection/verification/refinement only.

This module has no scheduler mutation capability and is safe to import from
collection, recovery, production-state, and monitor code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
WEEKLY_PRODUCTION_WEEKDAY = 0  # Monday
WEEKLY_PRODUCTION_HOUR = 19
WEEKLY_PRODUCTION_MINUTE = 0
HOURLY_MINUTE = 0

WEEKLY_PRODUCTION = "WEEKLY_PRODUCTION"
COLLECTION_VERIFY_REFINE_ONLY = "COLLECTION_VERIFY_REFINE_ONLY"

GENERAL_CARDINFO_FACT_TYPES = frozenset({
    "official_release",
    "official_reprint",
    "official_promo",
    "official_event",
    "official_movie_bonus",
    "official_festival",
    "official_card_news",
})
MARKET_FACT_TYPES = frozenset({"completed_sale", "market_reference", "fx"})
ALL_SUPPORTED_FACT_TYPES = GENERAL_CARDINFO_FACT_TYPES | MARKET_FACT_TYPES


class RouterPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class RouterDecision:
    branch: str
    observed_at_kst: str
    production_allowed: bool
    render_allowed: bool
    verified_delivery_allowed: bool
    collection_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "observed_at_kst": self.observed_at_kst,
            "production_allowed": self.production_allowed,
            "render_allowed": self.render_allowed,
            "verified_delivery_allowed": self.verified_delivery_allowed,
            "collection_required": self.collection_required,
        }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise RouterPolicyError("datetime must be timezone-aware")
    return value.astimezone(KST)


def is_hourly_slot(value: datetime) -> bool:
    current = _aware(value)
    return current.minute == HOURLY_MINUTE and current.second == 0


def is_weekly_production_slot(value: datetime) -> bool:
    current = _aware(value)
    return (
        current.weekday() == WEEKLY_PRODUCTION_WEEKDAY
        and current.hour == WEEKLY_PRODUCTION_HOUR
        and current.minute == WEEKLY_PRODUCTION_MINUTE
    )


def route_for(value: datetime) -> RouterDecision:
    current = _aware(value)
    production = is_weekly_production_slot(current)
    branch = WEEKLY_PRODUCTION if production else COLLECTION_VERIFY_REFINE_ONLY
    return RouterDecision(
        branch=branch,
        observed_at_kst=current.isoformat(timespec="seconds"),
        production_allowed=production,
        render_allowed=production,
        verified_delivery_allowed=production,
    )


def next_weekly_production_slot(value: datetime) -> datetime:
    current = _aware(value)
    candidate = datetime.combine(
        current.date(),
        time(WEEKLY_PRODUCTION_HOUR, WEEKLY_PRODUCTION_MINUTE),
        tzinfo=KST,
    )
    days = (WEEKLY_PRODUCTION_WEEKDAY - current.weekday()) % 7
    candidate += timedelta(days=days)
    if candidate <= current:
        candidate += timedelta(days=7)
    return candidate


def visibility_bucket(*, end_date: date, as_of: date) -> str:
    """Current through end+5 days; archive starts on day 6."""
    if as_of <= end_date + timedelta(days=5):
        return "CURRENT"
    return "ARCHIVE"


def normalize_general_fact_type(value: str) -> str:
    token = str(value or "").strip().lower()
    aliases = {
        "release": "official_release",
        "release_or_product": "official_release",
        "product_announcement": "official_card_news",
        "announcement": "official_card_news",
        "card_news": "official_card_news",
        "rerelease": "official_reprint",
        "reprint": "official_reprint",
        "reprint_or_restock": "official_reprint",
        "restock": "official_reprint",
        "promo": "official_promo",
        "promo_distribution": "official_promo",
        "event": "official_event",
        "festival": "official_festival",
        "축제": "official_festival",
        "movie_bonus": "official_movie_bonus",
    }
    normalized = aliases.get(token, token)
    if normalized not in ALL_SUPPORTED_FACT_TYPES:
        raise RouterPolicyError(f"unsupported fact type: {value}")
    return normalized


def validate_hourly_schedule_text(schedule: str) -> list[str]:
    text = str(schedule or "")
    errors: list[str] = []
    if "FREQ=HOURLY" not in text:
        errors.append("schedule must be hourly")
    if "BYMINUTE=0" not in text:
        errors.append("schedule must run at minute 0")
    if "BYMINUTE=30" in text:
        errors.append("legacy minute-30 schedule is forbidden")
    return errors


def assert_render_allowed(value: datetime) -> None:
    if not is_weekly_production_slot(value):
        raise RouterPolicyError("FINAL_RENDER_OUTSIDE_MONDAY_19_KST")
