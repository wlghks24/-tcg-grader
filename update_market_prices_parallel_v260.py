#!/usr/bin/env python3
"""Bounded cross-host prefetch wrapper for the canonical market-price collector.

The existing `update_market_prices` parser/validation logic remains the source of
truth. This module only moves network waiting earlier and overlaps *different*
provider hosts. Requests to the same host stay serial, no source is queried more
than once, and a prefetch failure is replayed into the canonical collector so its
existing last-good/error policy remains unchanged.

WYYYES is integrated as a separate public-platform quote lane.  Those quotes keep
market location (KR), card edition (KR/JP/US), currency, and asking-vs-sold status
separate and never overwrite the canonical verified price.
"""
from __future__ import annotations

import concurrent.futures
import threading
import time
from collections import defaultdict
from urllib.parse import urlsplit

import update_market_prices as base
import wyyyes_market_source as wyyyes

# These are the fixed first-party/public-reference URLs already queried directly by
# base.main(). Dynamic discovery/cross-check lanes keep their own bounded policies.
FIXED_URLS = (
    "https://narutomarket.com/en/market/chakra-card-cp-001-gen-con-2026",
    "https://pokard.io/",
    "https://kream.co.kr/products/959332",
    "https://kream.co.kr/products/290634",
    "https://kream.co.kr/products/627575",
    "https://www.packmagik.com/cards/op-op14-op14-009-p1",
    "https://pokard.io/jpcard/SV8a-217/",
)
MAX_HOST_WORKERS = 4


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().rstrip(".")


def _prefetch_group(urls: tuple[str, ...], fetcher):
    rows = []
    for url in urls:
        started = time.monotonic()
        try:
            rows.append((url, True, fetcher(url), None, time.monotonic() - started))
        except Exception as exc:  # replay the same failure through canonical handlers
            rows.append((url, False, None, exc, time.monotonic() - started))
    return rows


def prefetch(fetcher=None, urls=FIXED_URLS, max_workers: int = MAX_HOST_WORKERS):
    """Fetch different hosts concurrently while keeping each host strictly serial."""
    fetcher = fetcher or base.fetch
    urls = tuple(urls)
    grouped: dict[str, list[str]] = defaultdict(list)
    for url in urls:
        host = _host(url)
        if not host:
            raise ValueError(f"market prefetch URL without host: {url}")
        grouped[host].append(url)

    workers = max(1, min(int(max_workers), MAX_HOST_WORKERS, len(grouped) or 1))
    result = {}
    stats = {
        "hosts": len(grouped),
        "urls": len(urls),
        "max_workers": workers,
        "network_calls": 0,
        "cache_hits": 0,
        "same_host_parallelism": 1,
    }
    if workers == 1 or len(grouped) <= 1:
        batches = [_prefetch_group(tuple(group), fetcher) for group in grouped.values()]
    else:
        batches = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="market-prefetch"
        ) as pool:
            futures = [pool.submit(_prefetch_group, tuple(group), fetcher) for group in grouped.values()]
            for future in concurrent.futures.as_completed(futures):
                batches.append(future.result())
    for batch in batches:
        for url, ok, payload, exc, duration in batch:
            result[url] = {
                "ok": ok,
                "payload": payload,
                "error": exc,
                "duration_seconds": round(max(0.0, float(duration)), 3),
            }
            stats["network_calls"] += 1
    return result, stats


def _merge_wyyyes_quotes(db: dict) -> dict:
    platform_quotes = db.setdefault("platform_quotes", {})
    previous = platform_quotes.get("WYYYES")
    if not isinstance(previous, list):
        previous = []
    try:
        result = wyyyes.collect_quotes(previous=previous)
    except Exception as exc:
        result = {
            "status": "collector_error",
            "quotes": previous,
            "preserved_last_good": bool(previous),
            "quote_count": len(previous),
            "completed_sale_count": sum(1 for row in previous if isinstance(row, dict) and row.get("is_completed_sale") is True),
            "asking_count": sum(1 for row in previous if isinstance(row, dict) and row.get("is_completed_sale") is not True),
            "region_counts": {},
            "errors": [f"collector:{type(exc).__name__}"],
            "source": "https://wyyyes.com/",
            "policy": "collector failed; preserve existing public quotes without promoting asking prices to sold",
        }
    platform_quotes["WYYYES"] = result.get("quotes") if isinstance(result.get("quotes"), list) else []
    status = db.setdefault("platform_quote_status", {})
    status["WYYYES"] = {key: value for key, value in result.items() if key != "quotes"}
    db["platform_quote_schema_version"] = 1
    db["platform_quote_policy"] = {
        "market_region_separate_from_card_region": True,
        "supported_card_regions": ["KR", "JP", "US", "UNKNOWN"],
        "asking_price_is_not_completed_sale": True,
        "public_pages_only": True,
        "canonical_market_price_overwrite": False,
    }
    return result


def run() -> dict:
    original_fetch = base.fetch
    cache, stats = prefetch(original_fetch)
    lock = threading.Lock()

    def cached_fetch(url: str) -> str:
        row = cache.get(url)
        if row is None:
            # Dynamic or newly-added canonical URLs are not silently skipped.
            return original_fetch(url)
        with lock:
            stats["cache_hits"] += 1
        if row["ok"]:
            return row["payload"]
        error = row["error"]
        if isinstance(error, BaseException):
            raise error
        raise OSError("market prefetch failed without exception evidence")

    base.fetch = cached_fetch
    try:
        db = base.main()
    finally:
        base.fetch = original_fetch

    if isinstance(db, dict):
        wyyyes_result = _merge_wyyyes_quotes(db)
        db["market_collection_performance"] = {
            "mode": "bounded_cross_host_prefetch_v267",
            "fixed_urls": stats["urls"],
            "network_calls": stats["network_calls"],
            "cache_hits": stats["cache_hits"],
            "provider_hosts": stats["hosts"],
            "cross_host_workers": stats["max_workers"],
            "same_host_parallelism": 1,
            "duplicate_network_requests_added": 0,
            "wyyyes_quote_count": int(wyyyes_result.get("quote_count") or 0),
            "wyyyes_completed_sale_count": int(wyyyes_result.get("completed_sale_count") or 0),
            "wyyyes_status": str(wyyyes_result.get("status") or "unknown"),
        }
        base.atomic_save(db)
    return db


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
