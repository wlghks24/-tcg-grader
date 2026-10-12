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
    """Claims cannot self-assert independent settlement verification."""
    if row.get("source_type") not in KINDS:
        return "REJECT"
    if row.get("source_type") == "COMPLETED_SALE_CLAIM":
        return "UNVERIFIED_COMPLETED_CLAIM"
    return "ASK_OR_BUY_OFFER"

def comparable_group(row):
    if any(row.get(k) is None for k in IDENTITY if k != "grade"):
        return None
    if row.get("grade_service") != "RAW" and not row.get("grade"):
        return None
    if row.get("grade_service") == "RAW" and row.get("grade"):
        return None
    return tuple(row.get(k) for k in IDENTITY)

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
            if not price.is_finite() or price <= 0:
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
