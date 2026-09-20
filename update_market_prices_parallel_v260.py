#!/usr/bin/env python3
"""Bounded cross-host prefetch wrapper for the canonical market-price collector.

The existing `update_market_prices` parser/validation logic remains the source of
truth. This module only moves network waiting earlier and overlaps *different*
provider hosts. Requests to the same host stay serial, no source is queried more
than once, and a prefetch failure is replayed into the canonical collector so its
existing last-good/error policy remains unchanged.

WYYYES is integrated as a separate public-platform quote lane. Those quotes keep
market location (KR), card edition (KR/JP/US), currency, and asking-vs-sold status
separate and never overwrite the canonical verified price.

The market-reference registry is intentionally navigation-only. It gives the UI a
curated set of domestic/international cross-check destinations without adding
scrapers, bypassing logins, or turning asking prices into completed sales.
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

# Evidence labels describe what the destination generally exposes. They do not
# assert that every individual result is a verified sale. The UI keeps the same
# distinction and asks the user to confirm card number, edition, grade and date.
MARKET_REFERENCE_SOURCES = (
    {
        "id": "collectory",
        "name": "Collectory",
        "region": "KR",
        "region_label": "국내 · 다국가 비교",
        "evidence_group": "mixed",
        "evidence_label": "집계 · 실거래/매물 혼합",
        "games": ["Pokémon"],
        "url": "https://collectory.cc/",
        "search_url_template": "https://collectory.cc/?q={query}",
        "recommended": True,
        "auto_collected": False,
        "note": "한국·일본·미국 등 판본 비교와 가격 이력 교차확인에 유용",
    },
    {
        "id": "joongna",
        "name": "중고나라 시세조회",
        "region": "KR",
        "region_label": "국내",
        "evidence_group": "mixed",
        "evidence_label": "등록가 · 판매가 분리",
        "games": ["ALL"],
        "url": "https://web.joongna.com/",
        "search_url_template": "https://web.joongna.com/search-price/{query}",
        "recommended": True,
        "auto_collected": False,
        "note": "BID 등록가와 EXECUTION 판매가를 구분해 확인",
    },
    {
        "id": "kream",
        "name": "KREAM",
        "region": "KR",
        "region_label": "국내",
        "evidence_group": "mixed",
        "evidence_label": "공개 거래 · 시장 참고",
        "games": ["ALL"],
        "url": "https://kream.co.kr/",
        "search_url_template": "https://kream.co.kr/search?keyword={query}",
        "recommended": True,
        "auto_collected": True,
        "note": "국내 TCG 공개 거래/상품 페이지를 카드·판본별로 교차확인",
    },
    {
        "id": "bunjang",
        "name": "번개장터",
        "region": "KR",
        "region_label": "국내",
        "evidence_group": "asking",
        "evidence_label": "판매중 · 호가 참고",
        "games": ["ALL"],
        "url": "https://m.bunjang.co.kr/",
        "search_url_template": "https://m.bunjang.co.kr/search/products?q={query}",
        "recommended": False,
        "auto_collected": False,
        "note": "현재 판매 희망가와 매물 수 확인용 · 체결가로 자동 간주하지 않음",
    },
    {
        "id": "daangn",
        "name": "당근",
        "region": "KR",
        "region_label": "국내 · 지역거래",
        "evidence_group": "asking",
        "evidence_label": "지역 매물 · 호가 참고",
        "games": ["ALL"],
        "url": "https://www.daangn.com/kr/buy-sell/",
        "search_url_template": "",
        "recommended": False,
        "auto_collected": False,
        "note": "지역별 매물/판매완료 표시는 참고하되 실제 체결금액은 별도 확인",
    },
    {
        "id": "wyyyes",
        "name": "WYYYES",
        "region": "KR",
        "region_label": "국내 · 해외판 포함",
        "evidence_group": "mixed",
        "evidence_label": "판매중 · 판매완료 구분",
        "games": ["Pokémon", "ONE PIECE", "NARUTO"],
        "url": "https://wyyyes.com/",
        "search_url_template": "",
        "recommended": True,
        "auto_collected": True,
        "note": "앱에서 공개 페이지를 제한 수집하며 호가와 판매완료를 분리",
    },
    {
        "id": "yahoo_auction_jp",
        "name": "Yahoo!オークション 낙찰",
        "region": "JP",
        "region_label": "일본",
        "evidence_group": "sold",
        "evidence_label": "낙찰 완료",
        "games": ["ALL"],
        "url": "https://auctions.yahoo.co.jp/closedsearch/closedsearch",
        "search_url_template": "https://auctions.yahoo.co.jp/closedsearch/closedsearch?p={query}",
        "recommended": True,
        "auto_collected": False,
        "note": "종료된 경매의 낙찰가 확인에 유용 · 동일 판본/상태/등급 확인 필수",
    },
    {
        "id": "mercari_jp",
        "name": "Mercari Japan",
        "region": "JP",
        "region_label": "일본",
        "evidence_group": "asking",
        "evidence_label": "판매중 · 매물 참고",
        "games": ["ALL"],
        "url": "https://jp.mercari.com/",
        "search_url_template": "https://jp.mercari.com/search?keyword={query}",
        "recommended": False,
        "auto_collected": False,
        "note": "일본 현지 매물가 확인용 · 판매중 가격을 체결가로 간주하지 않음",
    },
    {
        "id": "snkrdunk",
        "name": "SNKRDUNK",
        "region": "JP",
        "region_label": "일본 · 글로벌",
        "evidence_group": "guide",
        "evidence_label": "거래시장 · 시장가이드",
        "games": ["Pokémon", "ONE PIECE"],
        "url": "https://snkrdunk.com/en/brands/pokemon/trading-cards?categoryId=25",
        "search_url_template": "",
        "recommended": True,
        "auto_collected": False,
        "note": "일본 TCG 거래량·시장가 리포트와 현재 시장 참고",
    },
    {
        "id": "ebay_sold",
        "name": "eBay Sold",
        "region": "US_GLOBAL",
        "region_label": "미국 · 글로벌",
        "evidence_group": "sold",
        "evidence_label": "판매완료 검색",
        "games": ["ALL"],
        "url": "https://www.ebay.com/",
        "search_url_template": "https://www.ebay.com/sch/i.html?_nkw={query}&LH_Sold=1&LH_Complete=1",
        "recommended": True,
        "auto_collected": False,
        "note": "판매완료 비교용 · Best Offer, 배송비, 카드 상태와 판본 차이를 함께 확인",
    },
    {
        "id": "tcgplayer",
        "name": "TCGplayer",
        "region": "US_GLOBAL",
        "region_label": "미국",
        "evidence_group": "guide",
        "evidence_label": "최근 판매 기반 Market Price",
        "games": ["Pokémon", "ONE PIECE"],
        "url": "https://www.tcgplayer.com/",
        "search_url_template": "https://www.tcgplayer.com/search/all/product?q={query}&view=grid",
        "recommended": True,
        "auto_collected": False,
        "note": "최근 판매 기반 Market Price와 Most Recent Sale을 교차확인",
    },
    {
        "id": "pricecharting",
        "name": "PriceCharting",
        "region": "US_GLOBAL",
        "region_label": "미국 · 글로벌",
        "evidence_group": "guide",
        "evidence_label": "판매이력 · 등급별 가이드",
        "games": ["Pokémon"],
        "url": "https://www.pricecharting.com/",
        "search_url_template": "https://www.pricecharting.com/search-products?type=prices&q={query}",
        "recommended": True,
        "auto_collected": False,
        "note": "Ungraded·Grade 9·PSA 10 등 등급별 가격과 sold listings 확인",
    },
    {
        "id": "130point",
        "name": "130point Sales",
        "region": "US_GLOBAL",
        "region_label": "미국 · 글로벌",
        "evidence_group": "sold",
        "evidence_label": "판매완료 집계 참고",
        "games": ["ALL"],
        "url": "https://130point.com/sales/",
        "search_url_template": "",
        "recommended": True,
        "auto_collected": False,
        "note": "여러 경매/마켓 판매완료 비교에 유용한 보조 확인처",
    },
    {
        "id": "psa_apr",
        "name": "PSA Auction Prices Realized",
        "region": "US_GLOBAL",
        "region_label": "미국 · 글로벌",
        "evidence_group": "sold",
        "evidence_label": "PSA 등급품 낙찰결과",
        "games": ["ALL"],
        "url": "https://www.psacard.com/auctionprices",
        "search_url_template": "",
        "recommended": True,
        "auto_collected": False,
        "note": "PSA 등급품의 검증된 경매 결과를 등급·기간별로 확인",
    },
    {
        "id": "cardmarket",
        "name": "Cardmarket",
        "region": "EU",
        "region_label": "유럽",
        "evidence_group": "asking",
        "evidence_label": "유럽 매물 · 시장 참고",
        "games": ["Pokémon"],
        "url": "https://www.cardmarket.com/en/Pokemon",
        "search_url_template": "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString={query}",
        "recommended": False,
        "auto_collected": False,
        "note": "유럽 P2P 마켓의 매물/가격 수준 비교용 · 지역 차이를 감안",
    },
)


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


def _attach_reference_sources(db: dict) -> int:
    db["market_reference_schema_version"] = 1
    db["market_reference_sources"] = [dict(row) for row in MARKET_REFERENCE_SOURCES]
    db["market_reference_policy"] = {
        "navigation_only": True,
        "new_scrapers_added": False,
        "login_or_private_api_bypass": False,
        "asking_price_is_not_completed_sale": True,
        "evidence_reading_order": [
            "sold_or_auction_completed",
            "sale_based_market_guide",
            "mixed_aggregator",
            "asking_or_active_listing",
        ],
        "match_fields": ["card_name", "card_number", "edition", "grade", "condition", "sale_date"],
    }
    return len(MARKET_REFERENCE_SOURCES)


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
        reference_count = _attach_reference_sources(db)
        db["market_collection_performance"] = {
            "mode": "bounded_cross_host_prefetch_v268",
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
            "market_reference_source_count": reference_count,
            "market_reference_network_calls_added": 0,
        }
        base.atomic_save(db)
    return db


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
