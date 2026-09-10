#!/usr/bin/env python3
"""Normalize collector labels into the verification engine's canonical fact types.

This prevents festival/card-news/product-news aliases from being silently omitted
before source verification while retaining their original content subtype.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from instagram_tcg_content.canonical_taxonomy import (
    normalize_content_type,
    verification_fact_type,
)

DIRECT_FACT_TYPES = frozenset({"completed_sale", "market_reference", "fx", "card_price"})


def normalize_collector_record(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("COLLECTOR_RECORD_REQUIRED")
    out = deepcopy(row)
    raw = str(out.get("information_family") or out.get("fact_type") or "").strip().lower()
    content = str(out.get("content_type") or "").strip().lower()
    if raw in DIRECT_FACT_TYPES:
        out["fact_type"] = raw
        return out
    candidate = content or raw
    content_type = normalize_content_type(candidate)
    out["content_type"] = content_type
    out["fact_type"] = verification_fact_type(content_type)
    out["information_family"] = out["fact_type"]
    return out


def normalize_collector_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError("COLLECTOR_RECORD_LIST_REQUIRED")
    return [normalize_collector_record(row) for row in rows]


def self_test() -> None:
    festival = normalize_collector_record({"information_family": "festival"})
    assert festival["content_type"] == "festival"
    assert festival["fact_type"] == "official_event"
    news = normalize_collector_record({"fact_type": "official_card_news"})
    assert news["content_type"] == "card_news"
    assert news["fact_type"] == "official_release"
    sale = normalize_collector_record({"fact_type": "completed_sale"})
    assert sale["fact_type"] == "completed_sale" and "content_type" not in sale
    try:
        normalize_collector_record({"fact_type": "unknown"})
    except ValueError:
        pass
    else:
        raise AssertionError("unknown collector family must fail closed")
    print("Instagram card collection normalizer: PASS")


if __name__ == "__main__":
    self_test()
