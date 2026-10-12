#!/usr/bin/env python3
"""V674 offline market evidence classification. Never promotes claims to verified sales."""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from statistics import median
from ipaddress import ip_address
from urllib.parse import urlsplit

KINDS = {"STORE_BUY_OFFER", "SALE_LISTING", "COMPLETED_SALE_CLAIM"}
STATUS = {"USER_SUPPLIED_UNVERIFIED", "PLATFORM_REPORTED_COMPLETED", "INDEPENDENTLY_SETTLED_VERIFIED"}
IDENTITY = ("game_id", "market", "card_number", "printing", "condition", "grade_service", "grade", "reported_currency")
MAX_ROWS = 10000

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

def evidence_source_key(row, price):
    """A source is only a research identifier, never proof of a sale."""
    url = row.get("source_url")
    if url is None:
        # No provenance: identical claims must not inflate sample size.
        return ("UNSOURCED", str(price))
    if not isinstance(url, str) or len(url) > 1000 or url != url.strip():
        return None
    try:
        u = urlsplit(url)
        host = u.hostname
        if (u.scheme != "https" or not host or "." not in host or
                u.username or u.password or u.fragment or
                u.port not in (None, 443) or
                any(ord(c) < 32 for c in url) or
                host == "localhost" or host.endswith((".localhost", ".local", ".invalid", ".test"))):
            return None
        try:
            ip_address(host)
        except ValueError:
            pass
        else:
            return None
        return ("URL", "https://" + host.lower() + (u.path or "/") +
                ("?" + u.query if u.query else ""))
    except ValueError:
        return None

def audit_prices(records):
    """Offline research only: bounded, deduplicated, conflict-quarantined."""
    if not isinstance(records, (list, tuple)):
        raise ValueError("INVALID_RECORD_COLLECTION")
    if len(records) > MAX_ROWS:
        raise ValueError("TOO_MANY_MARKET_RECORDS")
    grouped = defaultdict(list)
    sources = defaultdict(set)
    seen_counts = defaultdict(int)
    rejected = 0
    for row in records:
        evidence_class = classify(row)
        if evidence_class == "REJECT":
            rejected += 1
            continue
        group = comparable_group(row)
        if group is None or row.get("evidence_status") != "USER_SUPPLIED_UNVERIFIED":
            rejected += 1
            continue
        raw_amount = row.get("reported_amount")
        if isinstance(raw_amount, bool) or not isinstance(raw_amount, (str, int, float, Decimal)):
            rejected += 1
            continue
        try:
            if len(str(raw_amount)) > 32:
                raise InvalidOperation
            price = Decimal(str(raw_amount))
            if (not price.is_finite() or price <= 0 or price > Decimal("1000000000") or
                    price.as_tuple().exponent < -2):
                raise InvalidOperation
        except (InvalidOperation, TypeError, ValueError):
            rejected += 1
            continue
        source = evidence_source_key(row, price)
        if source is None:
            rejected += 1
            continue
        key = (group, evidence_class, source)
        sources[key].add(price)
        seen_counts[(key, price)] += 1

    duplicates = 0
    conflicts = 0
    for key, amounts in sources.items():
        duplicates += sum(seen_counts[(key, amount)] - 1 for amount in amounts)
        if len(amounts) != 1:
            conflicts += 1
            continue  # Price conflicts from the same source are NOT averaged.
        group, evidence_class, _ = key
        grouped[(group, evidence_class)].append(next(iter(amounts)))
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
        "duplicate_count": duplicates,
        "conflicting_source_count": conflicts,
        "independently_verified_sale_count": 0,
        "network_calls": 0,
        "paid_dependencies": 0,
    }
