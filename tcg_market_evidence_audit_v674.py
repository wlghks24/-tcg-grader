#!/usr/bin/env python3
"""V674 offline market evidence classification. Never promotes claims to verified sales."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from statistics import median

KINDS = {"STORE_BUY_OFFER", "SALE_LISTING", "COMPLETED_SALE_CLAIM"}
STATUS = {"USER_SUPPLIED_UNVERIFIED", "PLATFORM_REPORTED_COMPLETED", "INDEPENDENTLY_SETTLED_VERIFIED"}
IDENTITY = ("game_id", "market", "card_number", "printing", "condition", "grade_service", "grade", "reported_currency")

def classify(row):
    """Keep store buy offers, active asks, and completed claims in separate bins."""
    if not isinstance(row, dict) or not isinstance(row.get("source_type"), str):
        return "REJECT"
    return {
        "STORE_BUY_OFFER": "UNVERIFIED_STORE_BUY_OFFER",
        "SALE_LISTING": "UNVERIFIED_SALE_LISTING",
        "COMPLETED_SALE_CLAIM": "UNVERIFIED_COMPLETED_CLAIM",
    }.get(row["source_type"], "REJECT")

def comparable_group(row):
    """Reject malformed identities safely and canonicalize the numeric grade."""
    if not isinstance(row, dict):
        return None
    for key in IDENTITY:
        if key == "grade":
            continue
        value = row.get(key)
        if (not isinstance(value, str) or not value or len(value) > 128 or
                value != value.strip() or any(ord(c) < 32 for c in value)):
            return None
    service, value = row["grade_service"], row.get("grade")
    if service not in {"RAW", "PSA", "BGS", "CGC", "TAG", "BRG"}:
        return None
    if service == "RAW":
        if value is not None and value != "":
            return None
        if row["condition"] not in {"NM", "LP", "MP", "HP", "DMG", "UNSPECIFIED"}:
            return None
        grade_text = None
    else:
        if row["condition"] != "UNSPECIFIED":
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
            return None
        try:
            grade = Decimal(str(value))
            norm = grade.normalize()
            if (not grade.is_finite() or not 1 <= grade <= 10 or
                    norm.as_tuple().exponent < -1):
                return None
            grade_text = format(norm, "f")
        except (InvalidOperation, TypeError, ValueError):
            return None
    if row["market"] not in {"KR", "JP", "US"}:
        return None
    if row["reported_currency"] != {"KR": "KRW", "JP": "JPY", "US": "USD"}[row["market"]]:
        return None
    return tuple(grade_text if key == "grade" else row[key] for key in IDENTITY)

def audit_prices(records):
    """Produce separate non-public summaries; no live price or verified sales."""
    grouped = defaultdict(list)
    rejected = 0
    for row in records:
        if not isinstance(row, dict) or classify(row) == "REJECT":
            rejected += 1
            continue
        group = comparable_group(row)
        if group is None or row.get("evidence_status") != "USER_SUPPLIED_UNVERIFIED":
            rejected += 1
            continue
        try:
            price = Decimal(str(row["reported_amount"]))
            if not price.is_finite() or price <= 0 or price > Decimal("1000000000") or price.as_tuple().exponent < -2:
                raise InvalidOperation
        except (InvalidOperation, KeyError, TypeError, ValueError):
            rejected += 1
            continue
        grouped[(group, classify(row))].append(price)
    return {
        "schema_version": 1,
        "status": "UNVERIFIED_PRIVATE_RESEARCH_ONLY",
        "groups": [
            {"identity": dict(zip(IDENTITY, identity)),
             "evidence_class": evidence_class,
             "sample_count": len(prices),
             "observed_median": str(median(prices)),
             "eligible_for_public_price_index": False}
            for (identity, evidence_class), prices in sorted(grouped.items())
        ],
        "rejected_count": rejected,
        "independently_verified_sale_count": 0,
        "network_calls": 0,
        "paid_dependencies": 0,
    }
