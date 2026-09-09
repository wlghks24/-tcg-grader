#!/usr/bin/env python3
"""Instagram TCG source routing + cross-verification core.

This module belongs to the Instagram TCG domain only. It deliberately avoids
imports from the Main runtime/collector/grading stack. It keeps provenance and
sale lineage explicit, verifies facts fail-closed, and changes retry strategy
after repeated failures.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Iterable, Sequence

KST = timezone(timedelta(hours=9))
MAX_FETCH_AGE_HOURS = 36.0
MAX_COMPLETED_SALE_AGE_DAYS = 30
MAX_FUTURE_SKEW = timedelta(minutes=5)
POSTABLE = {"verified"}
CORE_FACTS = {
    "completed_sale",
    "official_release",
    "official_reprint",
    "official_promo",
    "official_event",
    "official_movie_bonus",
    "fx",
}
SOURCE_TIERS = {
    "official_primary": 1,
    "official_secondary": 2,
    "completed_sale_original": 3,
    "grading_auction_original": 4,
    "market_reference": 5,
    "discovery_lead": 6,
}
TRANSACTION_EVIDENCE_TIERS = {"completed_sale_original", "grading_auction_original"}
INVALID_COMPLETED_STATUSES = {
    "cancelled",
    "refunded",
    "relisted",
    "asking",
    "listing",
    "best_offer_unknown",
    "unknown_condition",
}
FINAL_COMPLETED_STATES = {"sold", "completed", "closed", "settled", "realized"}
FINALITY_VALUES = {"final", "settled", "closed", "completed", "complete", "realized"}
GRADED_CONDITIONS = {"graded", "slabbed", "encapsulated"}


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
    condition: str | None = None
    grade: str | None = None
    finality: str | None = None
    price_basis: str | None = None
    quantity: int | None = None
    unit: str | None = None
    lineage_key: str | None = None

    def with_lineage(self) -> "Observation":
        if self.lineage_key:
            return self
        raw = "|".join(
            (
                self.collector_id,
                self.provider_id,
                self.canonical_key,
                self.source_locator,
                self.value,
            )
        )
        return replace(
            self,
            lineage_key=sha256(raw.encode("utf-8", "replace")).hexdigest()[:24],
        )


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


def error_signature(
    stage: str, collector_id: str, provider_id: str, evidence: str
) -> str:
    raw = f"{stage}|{collector_id}|{provider_id}|{evidence[:300]}"
    return sha256(raw.encode("utf-8", "replace")).hexdigest()[:20]


def independent_key(obs: Observation) -> tuple[str, str]:
    """Mirrors from one provider are not independent evidence."""
    return (obs.provider_id, obs.source_tier)


def dedupe_lineage(rows: Iterable[Observation]) -> list[Observation]:
    """Deduplicate shared lineage without hiding identity conflicts.

    Completed-sale transaction evidence must carry explicit lineage. Missing
    lineage remains visible for the hard gate; non-sale facts may derive a
    deterministic lineage fingerprint.
    """
    seen: set[tuple[str, str, str, str]] = set()
    out: list[Observation] = []
    for raw in rows:
        is_transaction = (
            raw.fact_type == "completed_sale"
            and raw.source_tier in TRANSACTION_EVIDENCE_TIERS
        )
        row = raw if is_transaction else raw.with_lineage()
        if row.lineage_key:
            lineage = row.lineage_key
        else:
            fallback = "|".join(
                (
                    row.collector_id,
                    row.provider_id,
                    row.canonical_key,
                    row.source_locator,
                    row.value,
                )
            )
            lineage = "__missing_lineage__:" + sha256(
                fallback.encode("utf-8", "replace")
            ).hexdigest()[:24]
        dedupe_key = (lineage, row.game, row.fact_type, row.canonical_key)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
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


def _positive_finite_decimal(value: str) -> bool:
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return False
    return parsed.is_finite() and parsed > 0


def _normalized_sale_amount(value: str) -> str | None:
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite():
        return None
    return format(parsed.normalize(), "f")


def _normalize_condition(value: str | None) -> str:
    condition = (value or "").strip().lower()
    if condition in GRADED_CONDITIONS:
        return "graded"
    if condition in {"raw", "ungraded"}:
        return "raw"
    return condition


def _normalize_finality(value: str | None) -> str:
    finality = (value or "").strip().lower()
    return "final" if finality in FINALITY_VALUES else finality


def _sale_comparability_key(row: Observation) -> tuple[object, ...]:
    condition = _normalize_condition(row.condition)
    grade = " ".join((row.grade or "").strip().upper().split()) if condition == "graded" else ""
    return (
        (row.original_currency or "").strip().upper(),
        condition,
        grade,
        (row.price_basis or "").strip().lower(),
        row.quantity,
        (row.unit or "").strip().lower(),
    )


def _transaction_lineage_conflict(rows: Sequence[Observation]) -> tuple[bool, tuple[str, ...]]:
    """Detect contradictory facts published for one explicit transaction lineage."""
    grouped: dict[str, set[tuple[object, ...]]] = {}
    values: dict[str, set[str]] = {}
    for row in rows:
        if (
            row.fact_type != "completed_sale"
            or row.source_tier not in TRANSACTION_EVIDENCE_TIERS
            or not row.lineage_key
        ):
            continue
        trade_time = _parse_time(row.event_or_trade_time)
        normalized_time = trade_time.astimezone(timezone.utc).isoformat() if trade_time else None
        status = row.status.strip().lower()
        final_state = "final" if status in FINAL_COMPLETED_STATES else status
        signature = (
            row.game,
            row.fact_type,
            row.canonical_key,
            _normalized_sale_amount(row.value),
            normalized_time,
            final_state,
            _normalize_finality(row.finality),
            _sale_comparability_key(row),
        )
        grouped.setdefault(row.lineage_key, set()).add(signature)
        values.setdefault(row.lineage_key, set()).add(str(row.value))

    conflicting_values: set[str] = set()
    found = False
    for lineage, signatures in grouped.items():
        if len(signatures) > 1:
            found = True
            conflicting_values.update(values.get(lineage, set()))
    return (found, tuple(sorted(conflicting_values)))


def _completed_sale_evidence_reason(row: Observation) -> str | None:
    if row.fact_type != "completed_sale":
        return None
    if row.source_tier not in TRANSACTION_EVIDENCE_TIERS:
        return None
    if row.status.lower() in INVALID_COMPLETED_STATUSES:
        return "invalid completed-sale status"
    if row.status.lower() not in FINAL_COMPLETED_STATES:
        return "completed-sale final state missing"
    if _parse_time(row.event_or_trade_time) is None:
        return "completed-sale transaction time missing"
    if not row.lineage_key:
        return "completed-sale explicit lineage missing"
    currency = (row.original_currency or "").strip()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return "completed-sale currency invalid"
    if not _positive_finite_decimal(row.value):
        return "completed-sale realized amount invalid"
    if not row.condition:
        return "completed-sale condition missing"
    condition = _normalize_condition(row.condition)
    if condition == "graded" and not row.grade:
        return "completed-sale grade missing"
    if not row.finality:
        return "completed-sale finality missing"
    if row.finality.strip().lower() not in FINALITY_VALUES:
        return "completed-sale finality invalid"
    if not row.price_basis:
        return "completed-sale price basis missing"
    if (
        row.quantity is None
        or isinstance(row.quantity, bool)
        or not isinstance(row.quantity, int)
        or row.quantity <= 0
    ):
        return "completed-sale quantity missing or invalid"
    if not row.unit:
        return "completed-sale unit missing"
    if not row.source_locator:
        return "completed-sale item/lot locator missing"
    return None


def _invalid_observation_reason(
    row: Observation,
    *,
    now: datetime,
) -> str | None:
    if row.source_tier not in SOURCE_TIERS:
        return "unknown source tier"
    if (
        not row.source_code
        or not row.source_locator
        or not row.provider_id
        or not row.collector_id
    ):
        return "missing provenance field"
    if not row.canonical_key or not row.fact_type or not row.game:
        return "missing identity field"

    fetched = _parse_time(row.fetched_at_kst)
    if fetched is None:
        return "invalid fetched_at_kst"
    fetched_utc = fetched.astimezone(timezone.utc)
    current_utc = now.astimezone(timezone.utc)
    if fetched_utc - current_utc > MAX_FUTURE_SKEW:
        return "fetched_at_kst is in the future"
    fetch_age_hours = (current_utc - fetched_utc).total_seconds() / 3600.0
    if fetch_age_hours > MAX_FETCH_AGE_HOURS:
        return "stale source capture"

    event_time = _parse_time(row.event_or_trade_time) if row.event_or_trade_time else None
    if row.event_or_trade_time and event_time is None:
        return "invalid event_or_trade_time"
    if row.fact_type == "completed_sale" and event_time is not None:
        event_utc = event_time.astimezone(timezone.utc)
        if event_utc - current_utc > MAX_FUTURE_SKEW:
            return "completed-sale time is in the future"
        sale_age_days = (current_utc - event_utc).total_seconds() / 86400.0
        if sale_age_days > MAX_COMPLETED_SALE_AGE_DAYS:
            return "completed-sale evidence older than 30 days"
    return None


def _latest(rows: Sequence[Observation]) -> Observation:
    def key(row: Observation):
        return (
            _parse_time(row.event_or_trade_time)
            or _parse_time(row.fetched_at_kst)
            or datetime.min.replace(tzinfo=timezone.utc)
        )

    return max(rows, key=key)


def verify_fact(
    rows: Sequence[Observation],
    *,
    now: datetime | None = None,
) -> VerificationResult:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if not rows:
        return VerificationResult(
            "", "", "inaccessible", None, (), 0, 0, False, 0.0, "no observations"
        )

    lineage_conflict, lineage_conflict_values = _transaction_lineage_conflict(rows)
    if lineage_conflict:
        first_raw = rows[0]
        return VerificationResult(
            first_raw.canonical_key,
            first_raw.fact_type,
            "conflict",
            None,
            tuple(sorted({r.source_code for r in rows if r.source_code})),
            len(rows),
            0,
            any(r.source_tier == "official_primary" for r in rows),
            0.10,
            "same completed-sale lineage disagrees on transaction facts",
            lineage_conflict_values,
        )

    rows = dedupe_lineage(rows)
    first = rows[0]
    key = first.canonical_key
    fact = first.fact_type
    game = first.game

    invalid = [
        reason
        for r in rows
        if (reason := _invalid_observation_reason(r, now=current))
    ]
    if invalid:
        return VerificationResult(
            key,
            fact,
            "unverified",
            None,
            tuple(sorted({r.source_code for r in rows if r.source_code})),
            len(rows),
            0,
            False,
            0.10,
            invalid[0],
        )

    if any(
        r.canonical_key != key or r.fact_type != fact or r.game != game for r in rows
    ):
        return VerificationResult(
            key,
            fact,
            "conflict",
            None,
            tuple(sorted({r.source_code for r in rows})),
            len(rows),
            0,
            False,
            0.10,
            "mixed canonical identity/game/fact",
        )

    source_codes = tuple(sorted({r.source_code for r in rows}))
    independent = {independent_key(r) for r in rows}
    official_primary = any(r.source_tier == "official_primary" for r in rows)

    if fact == "completed_sale":
        valid = [
            r
            for r in rows
            if r.source_tier in TRANSACTION_EVIDENCE_TIERS
            and _completed_sale_evidence_reason(r) is None
        ]
        comparable_groups: dict[tuple[object, ...], list[Observation]] = {}
        for row in valid:
            comparable_groups.setdefault(_sale_comparability_key(row), []).append(row)
        eligible_groups = [
            group
            for group in comparable_groups.values()
            if len({r.provider_id for r in group}) >= 2
        ]
        if len(eligible_groups) > 1:
            return VerificationResult(
                key,
                fact,
                "conflict",
                None,
                tuple(sorted({r.source_code for r in valid})),
                len(valid),
                0,
                official_primary,
                0.20,
                "multiple completed-sale evidence bases for one canonical key",
            )
        if len(eligible_groups) == 1:
            selected = eligible_groups[0]
            original_providers = {r.provider_id for r in selected}
            latest = _latest(selected)
            return VerificationResult(
                key,
                fact,
                "verified",
                latest.value,
                tuple(sorted({r.source_code for r in selected})),
                len(selected),
                len(original_providers),
                official_primary,
                0.97,
                None,
            )
        original_providers = {r.provider_id for r in valid}
        evidence_errors = [
            reason
            for r in rows
            if r.source_tier in TRANSACTION_EVIDENCE_TIERS
            if (reason := _completed_sale_evidence_reason(r))
        ]
        if evidence_errors:
            reason = evidence_errors[0]
        elif len(comparable_groups) > 1:
            reason = "completed-sale evidence basis mismatch"
        else:
            reason = "needs 2 independent realized-sale evidence providers"
        return VerificationResult(
            key,
            fact,
            "partial",
            None if not valid else _latest(valid).value,
            tuple(sorted({r.source_code for r in valid})),
            len(valid),
            len(original_providers),
            official_primary,
            0.58,
            reason,
        )

    values = sorted({r.value for r in rows})
    if len(values) > 1:
        return VerificationResult(
            key,
            fact,
            "conflict",
            None,
            source_codes,
            len(rows),
            len(independent),
            official_primary,
            0.25,
            "independent sources disagree",
            tuple(values),
        )

    value = values[0] if values else None

    if fact.startswith("official_"):
        if official_primary:
            return VerificationResult(
                key,
                fact,
                "verified",
                value,
                source_codes,
                len(rows),
                len(independent),
                True,
                0.99,
                None,
            )
        return VerificationResult(
            key,
            fact,
            "partial",
            value,
            source_codes,
            len(rows),
            len(independent),
            False,
            0.60,
            "official primary source missing",
        )

    if fact == "market_reference":
        refs = {r.provider_id for r in rows if r.source_tier == "market_reference"}
        if len(refs) >= 2:
            return VerificationResult(
                key,
                fact,
                "verified",
                value,
                source_codes,
                len(rows),
                len(refs),
                official_primary,
                0.90,
                None,
            )
        return VerificationResult(
            key,
            fact,
            "probable",
            value,
            source_codes,
            len(rows),
            len(refs),
            official_primary,
            0.65,
            "single market-reference provider",
        )

    if fact == "fx":
        if any(r.provider_id.startswith("fx:") for r in rows):
            return VerificationResult(
                key,
                fact,
                "verified",
                value,
                source_codes,
                len(rows),
                len(independent),
                official_primary,
                0.95,
                None,
            )
        return VerificationResult(
            key,
            fact,
            "partial",
            value,
            source_codes,
            len(rows),
            len(independent),
            official_primary,
            0.55,
            "explicit FX provider missing",
        )

    if len(independent) >= 2:
        return VerificationResult(
            key,
            fact,
            "verified",
            value,
            source_codes,
            len(rows),
            len(independent),
            official_primary,
            0.90,
            None,
        )
    return VerificationResult(
        key,
        fact,
        "probable",
        value,
        source_codes,
        len(rows),
        len(independent),
        official_primary,
        0.60,
        "needs independent cross-check",
    )


def strategy_for_retry(retry_count: int) -> str:
    if retry_count <= 0:
        return "same_source_backoff"
    if retry_count == 1:
        return "alternate_source"
    if retry_count == 2:
        return "alternate_parser_and_source"
    return "quarantine_and_exclude"


def build_error(
    stage: str,
    collector_id: str,
    provider_id: str,
    evidence: str,
    retry_count: int = 0,
) -> ErrorRecord:
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


def x10_fact_gate(
    results: Sequence[VerificationResult],
    *,
    required_core_keys: Sequence[tuple[str, str]] | None = None,
) -> tuple[bool, list[str]]:
    """Fail closed unless core production facts are present and verified."""
    reasons: list[str] = []
    if not results:
        return False, ["NO_VERIFICATION_RESULTS"]

    core_results = [result for result in results if result.fact_type in CORE_FACTS]
    if not core_results:
        reasons.append("NO_CORE_FACTS")

    seen = {(result.canonical_key, result.fact_type) for result in core_results}
    if required_core_keys is not None:
        required = {
            (str(key).strip(), str(fact).strip())
            for key, fact in required_core_keys
            if str(key).strip() and str(fact).strip()
        }
        missing = sorted(required - seen)
        reasons.extend(f"MISSING_REQUIRED_CORE_FACT:{key}:{fact}" for key, fact in missing)

    for result in core_results:
        if result.status != "verified":
            reasons.append(
                f"{result.canonical_key}:{result.fact_type}:{result.status}:"
                f"{result.uncertainty_reason or 'unverified'}"
            )
    return (not reasons, reasons)


VERIFICATION_RECEIPT_SCHEMA = 2
VERIFICATION_MODE = "INSTAGRAM_LOCAL_EVIDENCE_ONLY"
VERIFICATION_RECEIPT_CONTRACT = "OBSERVATION_GROUPS_V1"


def _verification_result_payload(result: VerificationResult) -> dict[str, object]:
    return {
        "canonical_key": result.canonical_key,
        "fact_type": result.fact_type,
        "status": result.status,
        "canonical_value": result.canonical_value,
        "source_codes": list(result.source_codes),
        "source_count": result.source_count,
        "independent_source_count": result.independent_source_count,
        "official_primary_present": result.official_primary_present,
        "confidence_score": result.confidence_score,
        "uncertainty_reason": result.uncertainty_reason,
        "conflict_values": list(result.conflict_values),
    }


def _observation_payload(row: Observation) -> dict[str, object]:
    return {
        "game": row.game,
        "fact_type": row.fact_type,
        "canonical_key": row.canonical_key,
        "value": row.value,
        "source_code": row.source_code,
        "source_name": row.source_name,
        "source_locator": row.source_locator,
        "source_tier": row.source_tier,
        "collector_id": row.collector_id,
        "provider_id": row.provider_id,
        "fetched_at_kst": row.fetched_at_kst,
        "event_or_trade_time": row.event_or_trade_time,
        "status": row.status,
        "original_currency": row.original_currency,
        "condition": row.condition,
        "grade": row.grade,
        "finality": row.finality,
        "price_basis": row.price_basis,
        "quantity": row.quantity,
        "unit": row.unit,
        "lineage_key": row.lineage_key,
    }


def _receipt_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_production_verification_receipt(
    observation_groups: Sequence[Sequence[Observation]],
    *,
    snapshot_id: str,
    snapshot_fingerprint: str,
    required_core_keys: Sequence[tuple[str, str]],
    now: datetime | None = None,
) -> dict[str, object]:
    """Run local verification and bind PASS to the exact observation set.

    Callers provide raw Observation groups, not pre-computed VerificationResult
    objects.  This prevents production code from bypassing verify_fact() by
    constructing a synthetic "verified" result directly.
    """
    snapshot = str(snapshot_id or "").strip()
    required = sorted(
        {
            (str(key).strip(), str(fact).strip())
            for key, fact in required_core_keys
            if str(key).strip() and str(fact).strip()
        }
    )
    if not snapshot:
        raise ValueError("SNAPSHOT_ID_REQUIRED")
    if (
        not isinstance(snapshot_fingerprint, str)
        or len(snapshot_fingerprint) != 64
        or any(ch not in "0123456789abcdef" for ch in snapshot_fingerprint)
    ):
        raise ValueError("SNAPSHOT_FINGERPRINT_REQUIRED")
    if not required:
        raise ValueError("REQUIRED_CORE_KEYS_REQUIRED")
    if not isinstance(observation_groups, (list, tuple)) or not observation_groups:
        raise ValueError("OBSERVATION_GROUPS_REQUIRED")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    results: list[VerificationResult] = []
    observations: list[Observation] = []
    seen_group_keys: set[tuple[str, str]] = set()
    for index, group in enumerate(observation_groups):
        if not isinstance(group, (list, tuple)) or not group:
            raise ValueError(f"OBSERVATION_GROUP_REQUIRED:{index}")
        if any(not isinstance(row, Observation) for row in group):
            raise ValueError(f"OBSERVATION_TYPE_REQUIRED:{index}")

        result = verify_fact(group, now=current)
        key = (result.canonical_key, result.fact_type)
        if key in seen_group_keys:
            raise ValueError(
                "DUPLICATE_VERIFICATION_GROUP:"
                + result.canonical_key
                + ":"
                + result.fact_type
            )
        seen_group_keys.add(key)
        results.append(result)
        observations.extend(group)

    passed, reasons = x10_fact_gate(results, required_core_keys=required)
    if not passed:
        raise ValueError("VERIFICATION_GATE_FAILED:" + "|".join(reasons))

    core_results = [
        result for result in results
        if result.fact_type in CORE_FACTS
    ]
    verified_keys = sorted(
        {
            (result.canonical_key, result.fact_type)
            for result in core_results
            if result.status == "verified"
        }
    )
    evidence_payload = sorted(
        (_verification_result_payload(result) for result in results),
        key=lambda row: (
            str(row["canonical_key"]),
            str(row["fact_type"]),
            str(row["status"]),
            str(row["canonical_value"]),
        ),
    )
    observation_payload = sorted(
        (_observation_payload(row) for row in observations),
        key=lambda row: (
            str(row["canonical_key"]),
            str(row["fact_type"]),
            str(row["provider_id"]),
            str(row["source_locator"]),
            str(row["lineage_key"]),
            str(row["value"]),
        ),
    )
    evidence_fingerprint = _receipt_hash({"results": evidence_payload})
    observation_fingerprint = _receipt_hash({"observations": observation_payload})

    payload: dict[str, object] = {
        "schema_version": VERIFICATION_RECEIPT_SCHEMA,
        "verification_mode": VERIFICATION_MODE,
        "verification_contract": VERIFICATION_RECEIPT_CONTRACT,
        "snapshot_id": snapshot,
        "snapshot_fingerprint": snapshot_fingerprint,
        "status": "pass",
        "required_core_keys": [list(item) for item in required],
        "verified_core_keys": [list(item) for item in verified_keys],
        "core_fact_count": len(core_results),
        "verified_core_fact_count": len(verified_keys),
        "observation_count": len(observations),
        "observation_fingerprint": observation_fingerprint,
        "evidence_fingerprint": evidence_fingerprint,
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return payload


def validate_production_verification_receipt(
    receipt: object,
    *,
    expected_snapshot_id: str,
    expected_snapshot_fingerprint: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["verification_receipt must be an object"]

    expected_fields = {
        "schema_version",
        "verification_mode",
        "verification_contract",
        "snapshot_id",
        "snapshot_fingerprint",
        "status",
        "required_core_keys",
        "verified_core_keys",
        "core_fact_count",
        "verified_core_fact_count",
        "observation_count",
        "observation_fingerprint",
        "evidence_fingerprint",
        "receipt_hash",
    }
    if set(receipt) != expected_fields:
        errors.append("verification_receipt field set mismatch")
        return errors
    if receipt.get("schema_version") != VERIFICATION_RECEIPT_SCHEMA:
        errors.append("verification_receipt schema mismatch")
    if receipt.get("verification_mode") != VERIFICATION_MODE:
        errors.append("verification_receipt mode mismatch")
    if receipt.get("verification_contract") != VERIFICATION_RECEIPT_CONTRACT:
        errors.append("verification_receipt contract mismatch")
    if receipt.get("snapshot_id") != expected_snapshot_id:
        errors.append("verification_receipt snapshot mismatch")
    snapshot_fingerprint = receipt.get("snapshot_fingerprint")
    if (
        not isinstance(snapshot_fingerprint, str)
        or len(snapshot_fingerprint) != 64
        or any(ch not in "0123456789abcdef" for ch in snapshot_fingerprint)
    ):
        errors.append("verification_receipt snapshot_fingerprint invalid")
    elif (
        expected_snapshot_fingerprint is not None
        and snapshot_fingerprint != expected_snapshot_fingerprint
    ):
        errors.append("verification_receipt snapshot fingerprint mismatch")
    if receipt.get("status") != "pass":
        errors.append("verification_receipt status must be pass")

    required_raw = receipt.get("required_core_keys")
    verified_raw = receipt.get("verified_core_keys")

    def normalize_pairs(value: object) -> set[tuple[str, str]] | None:
        if not isinstance(value, list):
            return None
        out: set[tuple[str, str]] = set()
        for row in value:
            if (
                not isinstance(row, list)
                or len(row) != 2
                or not all(isinstance(item, str) and item.strip() for item in row)
            ):
                return None
            out.add((row[0].strip(), row[1].strip()))
        return out

    required = normalize_pairs(required_raw)
    verified = normalize_pairs(verified_raw)
    if not required:
        errors.append("verification_receipt required_core_keys invalid")
    if verified is None:
        errors.append("verification_receipt verified_core_keys invalid")
    elif required is not None and not required.issubset(verified):
        errors.append("verification_receipt missing required verified core facts")

    core_count = receipt.get("core_fact_count")
    verified_count = receipt.get("verified_core_fact_count")
    observation_count = receipt.get("observation_count")
    if isinstance(core_count, bool) or not isinstance(core_count, int) or core_count <= 0:
        errors.append("verification_receipt core_fact_count invalid")
    if (
        isinstance(verified_count, bool)
        or not isinstance(verified_count, int)
        or verified_count <= 0
    ):
        errors.append("verification_receipt verified_core_fact_count invalid")
    elif verified is not None and verified_count != len(verified):
        errors.append("verification_receipt verified_core_fact_count mismatch")
    if (
        isinstance(core_count, int)
        and not isinstance(core_count, bool)
        and isinstance(verified_count, int)
        and not isinstance(verified_count, bool)
        and verified_count > core_count
    ):
        errors.append("verification_receipt verified count exceeds core count")
    if (
        isinstance(observation_count, bool)
        or not isinstance(observation_count, int)
        or observation_count <= 0
    ):
        errors.append("verification_receipt observation_count invalid")

    for field in ("observation_fingerprint", "evidence_fingerprint"):
        fingerprint = receipt.get(field)
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 64
            or any(ch not in "0123456789abcdef" for ch in fingerprint)
        ):
            errors.append(f"verification_receipt {field} invalid")

    receipt_hash = receipt.get("receipt_hash")
    if (
        not isinstance(receipt_hash, str)
        or len(receipt_hash) != 64
        or any(ch not in "0123456789abcdef" for ch in receipt_hash)
    ):
        errors.append("verification_receipt receipt_hash invalid")
    else:
        base = dict(receipt)
        base.pop("receipt_hash", None)
        try:
            expected_hash = _receipt_hash(base)
        except (TypeError, ValueError):
            errors.append("verification_receipt canonical encoding failed")
        else:
            if receipt_hash != expected_hash:
                errors.append("verification_receipt hash mismatch")
    return errors
