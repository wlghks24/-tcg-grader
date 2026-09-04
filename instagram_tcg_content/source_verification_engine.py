#!/usr/bin/env python3
"""Instagram TCG X10 source routing + cross-verification core.

Domain: Instagram TCG content only. This module does not import Main runtime code.
It plans diversified source acquisition, keeps independent provenance, performs
cross-source verification, and changes strategy after repeated failures.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from typing import Iterable, Sequence

KST = timezone(timedelta(hours=9))
POSTABLE = {"verified"}
CORE_FACTS = {"completed_sale", "official_release", "official_reprint", "official_promo", "official_event", "official_movie_bonus", "fx"}

SOURCE_TIERS = {
    "official_primary": 1,
    "official_secondary": 2,
    "completed_sale_original": 3,
    "grading_auction_original": 4,
    "market_reference": 5,
    "discovery_lead": 6,
}
INVALID_COMPLETED_STATUSES = {"cancelled", "refunded", "relisted", "asking", "listing", "best_offer_unknown", "unknown_condition"}

@dataclass(frozen=True)
class Observation:
    game: str
    fact_type: str
    canonical_key: str
    value: str
    source_code: str
    source_name: str
    source_locator: str
    source_tier: str
    collector_id: str
    provider_id: str
    fetched_at_kst: str
    event_or_trade_time: str | None = None
    status: str = "observed"
    original_currency: str | None = None
    lineage_key: str | None = None

    def with_lineage(self) -> "Observation":
        if self.lineage_key:
            return self
        raw = "|".join((self.collector_id, self.provider_id, self.canonical_key, self.source_locator, self.value))
        return Observation(**{**asdict(self), "lineage_key": sha256(raw.encode()).hexdigest()[:24]})

@dataclass(frozen=True)
class ErrorRecord:
    error_signature: str
    stage: str
    root_cause: str
    evidence: str
    fix_rule: str
    retry_count: int
    regression_result: str
    first_seen_at_kst: str
    last_seen_at_kst: str
    collector_id: str
    provider_id: str

@dataclass(frozen=True)
class VerificationResult:
    canonical_key: str
    fact_type: str
    status: str
    canonical_value: str | None
    source_codes: tuple[str, ...]
    source_count: int
    independent_source_count: int
    official_primary_present: bool
    confidence_score: float
    uncertainty_reason: str | None
    conflict_values: tuple[str, ...] = ()


def now_kst() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def error_signature(stage: str, collector_id: str, provider_id: str, evidence: str) -> str:
    raw = f"{stage}|{collector_id}|{provider_id}|{evidence[:300]}"
    return sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def independent_key(obs: Observation) -> tuple[str, str]:
    """Mirrors/aggregators from the same provider are not independent evidence."""
    return (obs.provider_id, obs.source_tier)


def dedupe_lineage(rows: Iterable[Observation]) -> list[Observation]:
    seen: set[str] = set()
    out: list[Observation] = []
    for raw in rows:
        row = raw.with_lineage()
        assert row.lineage_key
        if row.lineage_key in seen:
            continue
        seen.add(row.lineage_key)
        out.append(row)
    return out


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        return None
    return dt


def _invalid_observation_reason(row: Observation) -> str | None:
    if row.source_tier not in SOURCE_TIERS:
        return "unknown source tier"
    if not row.source_code or not row.source_locator or not row.provider_id or not row.collector_id:
        return "missing provenance field"
    if not row.canonical_key or not row.fact_type or not row.game:
        return "missing identity field"
    if _parse_time(row.fetched_at_kst) is None:
        return "invalid fetched_at_kst"
    if row.event_or_trade_time and _parse_time(row.event_or_trade_time) is None:
        return "invalid event_or_trade_time"
    return None


def _latest(rows: Sequence[Observation]) -> Observation:
    def key(row: Observation):
        return _parse_time(row.event_or_trade_time) or _parse_time(row.fetched_at_kst) or datetime.min.replace(tzinfo=timezone.utc)
    return max(rows, key=key)


def verify_fact(rows: Sequence[Observation]) -> VerificationResult:
    if not rows:
        return VerificationResult("", "", "inaccessible", None, (), 0, 0, False, 0.0, "no observations")
    rows = dedupe_lineage(rows)
    first = rows[0]
    key = first.canonical_key
    fact = first.fact_type
    game = first.game

    invalid = [reason for r in rows if (reason := _invalid_observation_reason(r))]
    if invalid:
        return VerificationResult(key, fact, "unverified", None, tuple(sorted({r.source_code for r in rows if r.source_code})), len(rows), 0, False, 0.10, invalid[0])

    # Never cross-verify different identities/games/fact families in one bucket.
    if any(r.canonical_key != key or r.fact_type != fact or r.game != game for r in rows):
        return VerificationResult(key, fact, "conflict", None, tuple(sorted({r.source_code for r in rows})), len(rows), 0, False, 0.10, "mixed canonical identity/game/fact")

    source_codes = tuple(sorted({r.source_code for r in rows}))
    independent = {independent_key(r) for r in rows}
    official_primary = any(r.source_tier == "official_primary" for r in rows)

    # Each completed sale is a distinct event. Different legitimate sale prices are
    # expected and must not be treated as a data conflict. We verify the evidence set
    # with >=2 independent original-sale providers and display the most recent valid sale.
    if fact == "completed_sale":
        valid = [r for r in rows if r.source_tier == "completed_sale_original" and r.status.lower() not in INVALID_COMPLETED_STATUSES]
        originals = {r.provider_id for r in valid}
        if len(originals) >= 2:
            latest = _latest(valid)
            return VerificationResult(key, fact, "verified", latest.value, tuple(sorted({r.source_code for r in valid})), len(valid), len(originals), official_primary, 0.97, None)
        return VerificationResult(key, fact, "partial", None if not valid else _latest(valid).value, tuple(sorted({r.source_code for r in valid})), len(valid), len(originals), official_primary, 0.58, "needs 2 independent original completed-sale sources")

    values = sorted({r.value for r in rows})
    if len(values) > 1:
        return VerificationResult(key, fact, "conflict", None, source_codes, len(rows), len(independent), official_primary, 0.25, "independent sources disagree", tuple(values))

    value = values[0] if values else None
    if fact.startswith("official_"):
        if official_primary:
            return VerificationResult(key, fact, "verified", value, source_codes, len(rows), len(independent), True, 0.99, None)
        return VerificationResult(key, fact, "partial", value, source_codes, len(rows), len(independent), False, 0.60, "official primary source missing")

    if fact == "market_reference":
        refs = {r.provider_id for r in rows if r.source_tier == "market_reference"}
        if len(refs) >= 2:
            return VerificationResult(key, fact, "verified", value, source_codes, len(rows), len(refs), official_primary, 0.90, None)
        return VerificationResult(key, fact, "probable", value, source_codes, len(rows), len(refs), official_primary, 0.65, "single market-reference provider")

    if fact == "fx":
        # FX is postable only with an explicit FX provider. Freshness must be checked
        # by the run packet immediately before final rendering; stale values are not reused.
        if any(r.provider_id.startswith("fx:") for r in rows):
            return VerificationResult(key, fact, "verified", value, source_codes, len(rows), len(independent), official_primary, 0.95, None)
        return VerificationResult(key, fact, "partial", value, source_codes, len(rows), len(independent), official_primary, 0.55, "explicit FX provider missing")

    if len(independent) >= 2:
        return VerificationResult(key, fact, "verified", value, source_codes, len(rows), len(independent), official_primary, 0.90, None)
    return VerificationResult(key, fact, "probable", value, source_codes, len(rows), len(independent), official_primary, 0.60, "needs independent cross-check")


def strategy_for_retry(retry_count: int) -> str:
    """SELF-HEAL: same signature cannot repeat unchanged after two failures."""
    if retry_count <= 0:
        return "same_source_backoff"
    if retry_count == 1:
        return "alternate_source"
    if retry_count == 2:
        return "alternate_parser_and_source"
    return "quarantine_and_exclude"


def build_error(stage: str, collector_id: str, provider_id: str, evidence: str, retry_count: int = 0) -> ErrorRecord:
    stamp = now_kst()
    strategy = strategy_for_retry(retry_count)
    return ErrorRecord(
        error_signature=error_signature(stage, collector_id, provider_id, evidence),
        stage=stage,
        root_cause="collection_or_verification_failure",
        evidence=evidence[:1200],
        fix_rule=strategy,
        retry_count=retry_count,
        regression_result="failed",
        first_seen_at_kst=stamp,
        last_seen_at_kst=stamp,
        collector_id=collector_id,
        provider_id=provider_id,
    )


def can_post(result: VerificationResult) -> bool:
    return result.status in POSTABLE


def x10_fact_gate(results: Sequence[VerificationResult]) -> tuple[bool, list[str]]:
    """Fail closed for core facts: every included core fact must be verified."""
    reasons: list[str] = []
    for r in results:
        if r.fact_type in CORE_FACTS and r.status != "verified":
            reasons.append(f"{r.canonical_key}:{r.fact_type}:{r.status}:{r.uncertainty_reason or 'unverified'}")
    return (not reasons, reasons)
