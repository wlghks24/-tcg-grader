#!/usr/bin/env python3
"""Fail-closed completed-sale / market-reference bridge for IG card-info.

The bridge keeps completed transactions separate from market references, preserves
provider/lineage/finality semantics, rejects private/local locators before they
reach verification, and retains raw accepted/rejected evidence for audit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any, Callable, Iterable

from instagram_tcg_content.collector_runtime import validate_source_url
from instagram_tcg_content.source_verification_engine import (
    Observation,
    VerificationResult,
    verify_fact,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = Path(__file__).resolve().with_name("source_registry.json")
DEFAULT_LEDGER = ROOT / "TCG_CROSSCHECK" / "IG_CARDINFO" / "market_evidence_ledger.json"
KST = timezone(timedelta(hours=9))
VERIFICATION_MODE = "INSTAGRAM_LOCAL_EVIDENCE_ONLY"
VERIFICATION_ENGINE = "instagram_tcg_content.source_verification_engine.py::verify_fact"
MAX_MARKET_REFERENCE_RELATIVE_SPREAD = Decimal("0.35")

FINALITY_TO_ENGINE = {
    "auction_house_realized": "realized",
    "platform_reported_sold": "completed",
    "final": "final",
    "settled": "settled",
    "closed": "closed",
    "completed": "completed",
    "complete": "complete",
    "realized": "realized",
}
NON_PROMOTABLE_FINALITY = {"settlement_unknown"}
STATUS_TO_ENGINE = {
    "sold": "sold",
    "completed": "completed",
    "ended_sold": "sold",
    "realized": "realized",
    "closed": "closed",
    "settled": "settled",
}
COMPLETED_REQUIRED = (
    "canonical_identity",
    "game",
    "region",
    "language",
    "item_or_lot_locator",
    "sold_or_completed_status",
    "event_or_trade_time",
    "currency",
    "realized_amount",
    "condition_or_grade_basis",
    "transaction_finality",
    "price_basis",
    "source_code",
    "source_locator",
    "unit_type",
    "quantity_basis",
    "underlying_lineage_key",
)
MARKET_REQUIRED = (
    "canonical_identity",
    "game",
    "region",
    "language",
    "value",
    "currency",
    "condition_basis",
    "source_code",
    "source_locator",
    "underlying_lineage_key",
    "unit_type",
    "quantity_basis",
)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _dec(value: Any, field: str) -> Decimal:
    try:
        parsed = Decimal(_clean(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field.upper()}_INVALID") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field.upper()}_INVALID")
    return parsed


def _fmt(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return "0" if rendered == "-0" else rendered


def _qty(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("QUANTITY_BASIS_INVALID")
    try:
        parsed = Decimal(_clean(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("QUANTITY_BASIS_INVALID") from exc
    if not parsed.is_finite() or parsed != parsed.to_integral_value() or parsed <= 0:
        raise ValueError("QUANTITY_BASIS_INVALID")
    return int(parsed)


def _aware(value: Any, field: str) -> str:
    raw = _clean(value)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field.upper()}_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field.upper()}_TIMEZONE_REQUIRED")
    return parsed.isoformat(timespec="seconds")


def _condition(value: Any) -> tuple[str, str | None]:
    raw = " ".join(_clean(value).upper().replace("_", " ").split())
    if not raw:
        raise ValueError("CONDITION_BASIS_REQUIRED")
    match = re.fullmatch(r"(PSA|BGS|CGC|TAG|BRG)\s*([0-9]+(?:\.[0-9]+)?)", raw)
    if match:
        return "graded", f"{match.group(1)} {match.group(2)}"
    return raw.lower().replace(" ", "_"), None


def _digest(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8", "replace")).hexdigest()[:16]


def _required(row: dict[str, Any], fields: Iterable[str]) -> None:
    missing = [key for key in fields if row.get(key) in (None, "")]
    if missing:
        raise ValueError("MARKET_EVIDENCE_MISSING:" + ",".join(missing))


def _public_locator(value: Any) -> str:
    locator = _clean(value)
    try:
        validate_source_url(locator)
    except Exception as exc:
        # Preserve the collector-runtime safety code (for example
        # PRIVATE_SOURCE_URL_FORBIDDEN / INVALID_SOURCE_URL) as the bridge error.
        raise ValueError(str(exc) or "INVALID_SOURCE_URL") from exc
    return locator


def _load_registry() -> dict[str, Any]:
    value = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("providers"), dict):
        raise ValueError("SOURCE_REGISTRY_INVALID")
    return value


def _index(registry: dict[str, Any]) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for provider_id, entry in (registry.get("providers") or {}).items():
        if not isinstance(entry, dict):
            continue
        for source_code in entry.get("source_codes") or []:
            key = _clean(source_code).upper()
            if key in index and index[key][0] != provider_id:
                raise ValueError(f"SOURCE_CODE_COLLISION:{key}")
            index[key] = (_clean(provider_id), _clean(entry.get("tier")))
    return index


def _provider(
    row: dict[str, Any],
    index: dict[str, tuple[str, str]],
    allowed_tiers: set[str],
) -> tuple[str, str]:
    source_code = _clean(row.get("source_code")).upper()
    hit = index.get(source_code)
    if not hit:
        raise ValueError(f"SOURCE_REGISTRY_UNRESOLVED_PROVIDER:{source_code or 'MISSING'}")
    if hit[1] not in allowed_tiers:
        raise ValueError(f"SOURCE_TIER_NOT_ALLOWED:{source_code}:{hit[1]}")
    return hit


def _sale(
    row: dict[str, Any],
    index: dict[str, tuple[str, str]],
    now: datetime,
) -> dict[str, Any]:
    _required(row, COMPLETED_REQUIRED)
    provider_id, tier = _provider(
        row, index, {"completed_sale_original", "grading_auction_original"}
    )
    finality = _clean(row["transaction_finality"]).lower()
    if finality in NON_PROMOTABLE_FINALITY:
        raise ValueError("SALE_SETTLEMENT_UNKNOWN_NOT_PROMOTABLE")
    engine_finality = FINALITY_TO_ENGINE.get(finality)
    if not engine_finality:
        raise ValueError(f"SALE_FINALITY_UNSUPPORTED:{finality}")
    status = STATUS_TO_ENGINE.get(_clean(row["sold_or_completed_status"]).lower())
    if not status:
        raise ValueError("SALE_FINAL_STATUS_INVALID")

    event_time = _aware(row["event_or_trade_time"], "event_or_trade_time")
    checked_at = _aware(row.get("checked_at") or now.isoformat(), "checked_at")
    amount = _dec(row["realized_amount"], "realized_amount")
    quantity = _qty(row["quantity_basis"])
    unit = _clean(row["unit_type"]).lower()
    if quantity != 1 or unit != "single_card":
        raise ValueError("UNIT_QUANTITY_BASIS_MIX")

    currency = _clean(row["currency"]).upper()
    condition, grade = _condition(row["condition_or_grade_basis"])
    identity = _clean(row["canonical_identity"])
    game = _clean(row["game"]).lower()
    region = _clean(row["region"]).upper()
    language = _clean(row["language"]).upper()
    price_basis = _clean(row["price_basis"]).lower()
    lineage = _clean(row["underlying_lineage_key"])
    item_locator = _public_locator(row["item_or_lot_locator"])
    source_locator = _public_locator(row["source_locator"])
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("CURRENCY_INVALID")
    if not all((identity, game, region, language, price_basis, lineage)):
        raise ValueError("SALE_IDENTITY_OR_PROVENANCE_MISSING")

    canonical_key = "completed_sale|" + "|".join(
        (
            game,
            region,
            language,
            _digest(identity),
            currency,
            condition,
            grade or "",
            price_basis,
            unit,
            str(quantity),
            finality,
        )
    )
    observation = Observation(
        game=game,
        fact_type="completed_sale",
        canonical_key=canonical_key,
        value=_fmt(amount),
        source_code=_clean(row["source_code"]).upper(),
        source_name=_clean(row["source_code"]).upper(),
        source_locator=item_locator,
        source_tier=tier,
        collector_id="market_evidence_bridge:completed_sale",
        provider_id=provider_id,
        fetched_at_kst=checked_at,
        event_or_trade_time=event_time,
        status=status,
        original_currency=currency,
        condition=condition,
        grade=grade,
        finality=engine_finality,
        price_basis=price_basis,
        quantity=quantity,
        unit=unit,
        lineage_key=lineage,
    )
    return {
        "kind": "completed_sale",
        "key": canonical_key,
        "provider_id": provider_id,
        "tier": tier,
        "lineage": lineage,
        "finality": finality,
        "amount": _fmt(amount),
        "currency": currency,
        "condition": condition,
        "grade": grade,
        "basis": price_basis,
        "quantity": quantity,
        "unit": unit,
        "event": event_time,
        "checked": checked_at,
        "item_locator": item_locator,
        "source_locator": source_locator,
        "raw": dict(row),
        "obs": observation,
    }


def _market_reference(
    row: dict[str, Any],
    index: dict[str, tuple[str, str]],
    now: datetime,
) -> dict[str, Any]:
    _required(row, MARKET_REQUIRED)
    provider_id, tier = _provider(row, index, {"market_reference"})
    if _clean(row.get("value_type") or "market_reference").lower() not in {
        "market_reference",
        "market_price",
        "index",
    }:
        raise ValueError("MARKET_REFERENCE_VALUE_TYPE_INVALID")

    value = _dec(row["value"], "market_reference_value")
    currency = _clean(row["currency"]).upper()
    condition, grade = _condition(row["condition_basis"])
    quantity = _qty(row["quantity_basis"])
    unit = _clean(row["unit_type"]).lower()
    checked_at = _aware(row.get("checked_at") or now.isoformat(), "checked_at")
    identity = _clean(row["canonical_identity"])
    game = _clean(row["game"]).lower()
    region = _clean(row["region"]).upper()
    language = _clean(row["language"]).upper()
    lineage = _clean(row["underlying_lineage_key"])
    source_locator = _public_locator(row["source_locator"])

    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("CURRENCY_INVALID")
    if quantity != 1 or unit != "single_card":
        raise ValueError("UNIT_QUANTITY_BASIS_MIX")
    if not all((identity, game, region, language, lineage)):
        raise ValueError("MARKET_REFERENCE_IDENTITY_OR_PROVENANCE_MISSING")

    canonical_key = "market_reference|" + "|".join(
        (
            game,
            region,
            language,
            _digest(identity),
            currency,
            condition,
            grade or "",
            unit,
            str(quantity),
        )
    )
    return {
        "kind": "market_reference",
        "key": canonical_key,
        "provider_id": provider_id,
        "tier": tier,
        "lineage": lineage,
        "value": value,
        "currency": currency,
        "condition": condition,
        "grade": grade,
        "quantity": quantity,
        "unit": unit,
        "checked": checked_at,
        "identity": identity,
        "game": game,
        "region": region,
        "language": language,
        "source_code": _clean(row["source_code"]).upper(),
        "source_locator": source_locator,
        "raw": dict(row),
    }


def _signature(row: dict[str, Any]) -> tuple[Any, ...]:
    if row["kind"] == "completed_sale":
        return (
            row["key"],
            row["amount"],
            row["event"],
            row["finality"],
            row["basis"],
            row["condition"],
            row.get("grade"),
        )
    return (
        row["key"],
        _fmt(row["value"]),
        row["currency"],
        row["condition"],
        row.get("grade"),
    )


def _rejection(
    *,
    index: int | None,
    row: dict[str, Any] | None,
    error: str,
    kind: str | None = None,
) -> dict[str, Any]:
    raw = dict(row) if isinstance(row, dict) else None
    return {
        "index": index,
        "kind": kind,
        "source_code": _clean(raw.get("source_code")).upper() if raw else "",
        "lineage_key": _clean(raw.get("underlying_lineage_key")) if raw else "",
        "source_locator": _clean(
            (raw.get("item_or_lot_locator") or raw.get("source_locator")) if raw else ""
        ),
        "error": error,
        "raw_evidence": raw,
    }


def _dedupe(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # A completed-sale lineage and a market-reference lineage can legitimately
    # share the same external identifier. Never let one evidence family erase
    # or conflict with the other merely because their lineage strings match.
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row["kind"], row["lineage"])].append(row)

    keep: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for (kind, lineage), group in grouped.items():
        signatures = {_signature(row) for row in group}
        if len(signatures) > 1:
            for row in group:
                rejected.append(
                    _rejection(
                        index=None,
                        row=row["raw"],
                        error="EVIDENCE_LINEAGE_CONFLICT",
                        kind=kind,
                    )
                )
            continue
        keep.append(group[0])
        for duplicate in group[1:]:
            rejected.append(
                _rejection(
                    index=None,
                    row=duplicate["raw"],
                    error="DUPLICATE_EVIDENCE_LINEAGE",
                    kind=kind,
                )
            )
    return keep, rejected


def _sale_output(
    group: list[dict[str, Any]],
    verifier: Callable[..., VerificationResult],
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = verifier([row["obs"] for row in group], now=now)
    detail = asdict(result)
    if result.status != "verified":
        return [], detail

    output: list[dict[str, Any]] = []
    for item in group:
        raw = item["raw"]
        output.append(
            {
                "canonical_key": item["key"],
                "fact_type": "completed_sale",
                "information_family": "completed_sale",
                "lineage_key": item["lineage"],
                "identity": {
                    "game": item["obs"].game,
                    "region": _clean(raw["region"]).upper(),
                    "language": _clean(raw["language"]).upper(),
                    "canonical_identity": _clean(raw["canonical_identity"]),
                    "transaction_finality": item["finality"],
                    "price_basis": item["basis"],
                    "condition_basis": _clean(raw["condition_or_grade_basis"]),
                    "unit_type": item["unit"],
                    "quantity_basis": item["quantity"],
                },
                "value": item["amount"],
                "value_type": "completed_sale",
                "currency": item["currency"],
                "region": _clean(raw["region"]).upper(),
                "language": _clean(raw["language"]).upper(),
                "condition": item["condition"],
                "grade": item.get("grade"),
                "observed_at": item["checked"],
                "source_role": _clean(raw["source_code"]).upper(),
                "source_locator": item["item_locator"],
                "verification": "verified",
                "verification_status": "verified",
                "verification_mode": VERIFICATION_MODE,
                "verification_engine": VERIFICATION_ENGINE,
            }
        )
    return output, detail


def _reference_output(
    group: list[dict[str, Any]],
    spread_cap: Decimal,
    verifier: Callable[..., VerificationResult],
    now: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    providers = {row["provider_id"] for row in group}
    if len(providers) < 2:
        return [], {
            "canonical_key": group[0]["key"],
            "status": "partial",
            "uncertainty_reason": "needs 2 independent market-reference providers",
        }

    values = sorted(row["value"] for row in group)
    med = Decimal(str(median(values)))
    low, high = values[0], values[-1]
    spread = (high - low) / med
    if spread > spread_cap:
        return [], {
            "canonical_key": group[0]["key"],
            "status": "conflict",
            "uncertainty_reason": "MARKET_REFERENCE_DISPERSION_TOO_WIDE",
            "relative_spread": _fmt(spread),
            "max_relative_spread": _fmt(spread_cap),
            "low": _fmt(low),
            "high": _fmt(high),
            "median": _fmt(med),
            "provider_count": len(providers),
        }

    aggregate = _fmt(med)
    token = (
        f"{group[0]['currency']}|median={aggregate}|"
        f"range={_fmt(low)}-{_fmt(high)}|n={len(providers)}"
    )
    observations = [
        Observation(
            game=row["game"],
            fact_type="market_reference",
            canonical_key=row["key"],
            value=token,
            source_code=row["source_code"],
            source_name=row["source_code"],
            source_locator=row["source_locator"],
            source_tier="market_reference",
            collector_id="market_evidence_bridge:market_reference",
            provider_id=row["provider_id"],
            fetched_at_kst=row["checked"],
            status="observed",
            original_currency=row["currency"],
            condition=row["condition"],
            grade=row.get("grade"),
            price_basis="market_reference",
            quantity=row["quantity"],
            unit=row["unit"],
            lineage_key=row["lineage"],
        )
        for row in group
    ]
    result = verifier(observations, now=now)
    detail = asdict(result) | {
        "derived_median": aggregate,
        "derived_low": _fmt(low),
        "derived_high": _fmt(high),
        "relative_spread": _fmt(spread),
        "provider_count": len(providers),
    }
    if result.status != "verified":
        return [], detail

    output: list[dict[str, Any]] = []
    for row in group:
        output.append(
            {
                "canonical_key": row["key"],
                "fact_type": "market_reference",
                "information_family": "market_reference",
                "lineage_key": row["lineage"],
                "identity": {
                    "game": row["game"],
                    "region": row["region"],
                    "language": row["language"],
                    "canonical_identity": row["identity"],
                    "condition_basis": row["condition"],
                    "unit_type": row["unit"],
                    "quantity_basis": row["quantity"],
                    "market_reference_low": _fmt(low),
                    "market_reference_high": _fmt(high),
                    "market_reference_median": aggregate,
                    "market_reference_provider_count": len(providers),
                    "market_reference_relative_spread": _fmt(spread),
                },
                "value": aggregate,
                "value_type": "market_reference_median",
                "currency": row["currency"],
                "region": row["region"],
                "language": row["language"],
                "condition": row["condition"],
                "grade": row.get("grade"),
                "observed_at": row["checked"],
                "source_role": row["source_code"],
                "source_locator": row["source_locator"],
                "verification": "verified",
                "verification_status": "verified",
                "verification_mode": VERIFICATION_MODE,
                "verification_engine": VERIFICATION_ENGINE,
            }
        )
    return output, detail


def verify_market_records(
    rows: list[dict[str, Any]],
    *,
    registry: dict[str, Any] | None = None,
    now: datetime | None = None,
    max_market_relative_spread: Decimal = MAX_MARKET_REFERENCE_RELATIVE_SPREAD,
    verifier: Callable[..., VerificationResult] = verify_fact,
) -> dict[str, Any]:
    if not isinstance(rows, list):
        raise ValueError("MARKET_RECORD_LIST_REQUIRED")
    current = now or datetime.now(KST)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if (
        not isinstance(max_market_relative_spread, Decimal)
        or max_market_relative_spread <= 0
    ):
        raise ValueError("MAX_MARKET_RELATIVE_SPREAD_INVALID")

    index = _index(registry or _load_registry())
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            rejected.append(
                _rejection(
                    index=row_index,
                    row=None,
                    error="MARKET_EVIDENCE_ROW_INVALID",
                )
            )
            continue
        kind = _clean(row.get("value_type") or row.get("fact_type")).lower()
        try:
            if kind in {"completed_sale", "sale"} or "realized_amount" in row:
                normalized.append(_sale(row, index, current))
            elif kind in {"market_reference", "market_price", "index"} or (
                "value" in row and "condition_basis" in row
            ):
                normalized.append(_market_reference(row, index, current))
            else:
                raise ValueError("MARKET_EVIDENCE_KIND_UNSUPPORTED")
        except ValueError as exc:
            rejected.append(
                _rejection(
                    index=row_index,
                    row=row,
                    error=str(exc),
                    kind=kind or None,
                )
            )

    normalized, dedupe_rejections = _dedupe(normalized)
    rejected.extend(dedupe_rejections)

    sales: dict[str, list[dict[str, Any]]] = defaultdict(list)
    references: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in normalized:
        (sales if row["kind"] == "completed_sale" else references)[row["key"]].append(row)

    verified: list[dict[str, Any]] = []
    sale_results: list[dict[str, Any]] = []
    reference_results: list[dict[str, Any]] = []
    for group in sales.values():
        output, result = _sale_output(group, verifier, current)
        verified.extend(output)
        sale_results.append(result)
    for group in references.values():
        output, result = _reference_output(
            group, max_market_relative_spread, verifier, current
        )
        verified.extend(output)
        reference_results.append(result)

    ledger = [
        {
            "kind": row["kind"],
            "lineage_key": row["lineage"],
            "provider_id": row["provider_id"],
            "source_tier": row["tier"],
            "source_code": _clean(row["raw"].get("source_code")).upper(),
            "source_locator": _clean(
                row["raw"].get("item_or_lot_locator")
                or row["raw"].get("source_locator")
            ),
            "raw_evidence": row["raw"],
        }
        for row in normalized
    ]

    return {
        "schema_version": "1.1-market-evidence-bridge",
        "verification_mode": VERIFICATION_MODE,
        "verification_engine": VERIFICATION_ENGINE,
        "observed_at": current.astimezone(KST).isoformat(timespec="seconds"),
        "verified_records": verified,
        "verified_completed_sale_count": sum(
            row["fact_type"] == "completed_sale" for row in verified
        ),
        "verified_market_reference_count": sum(
            row["fact_type"] == "market_reference" for row in verified
        ),
        "sale_verification_results": sale_results,
        "market_reference_verification_results": reference_results,
        "rejected": rejected,
        "evidence_ledger": ledger,
        "safety": {
            "completed_sale_market_reference_separated": True,
            "settlement_unknown_auto_promotion": False,
            "finality_class_preserved": True,
            "lineage_deduplication": True,
            "lineage_conflict_quarantine": True,
            "lineage_namespace_includes_evidence_kind": True,
            "accepted_and_rejected_raw_evidence_preserved": True,
            "public_http_locator_validation": True,
            "market_reference_relative_spread_cap": _fmt(
                max_market_relative_spread
            ),
        },
    }


def _atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)


def persist_evidence_ledger(
    report: dict[str, Any], path: Path = DEFAULT_LEDGER
) -> dict[str, Any]:
    payload = {
        "schema_version": report.get("schema_version"),
        "observed_at": report.get("observed_at"),
        "verification_mode": report.get("verification_mode"),
        "verification_engine": report.get("verification_engine"),
        "safety": report.get("safety"),
        "rows": report.get("evidence_ledger") or [],
        "rejected": report.get("rejected") or [],
    }
    _atomic(path, payload)
    reread = json.loads(path.read_text(encoding="utf-8"))
    if reread != payload:
        raise RuntimeError("MARKET_EVIDENCE_LEDGER_READBACK_MISMATCH")
    return reread


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--no-persist-ledger", action="store_true")
    args = parser.parse_args()
    if not args.input:
        raise SystemExit("--input is required")

    value = json.loads(Path(args.input).read_text(encoding="utf-8"))
    rows = value.get("records", value) if isinstance(value, dict) else value
    report = verify_market_records(rows)
    if not args.no_persist_ledger:
        persist_evidence_ledger(report, Path(args.ledger))
    print(
        json.dumps(
            {
                "verified_completed_sale_count": report[
                    "verified_completed_sale_count"
                ],
                "verified_market_reference_count": report[
                    "verified_market_reference_count"
                ],
                "rejected_count": len(report["rejected"]),
                "ledger": None
                if args.no_persist_ledger
                else str(Path(args.ledger)),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
