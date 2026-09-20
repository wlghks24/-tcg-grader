#!/usr/bin/env python3
"""Maintenance-aware compatibility layer for the official grading-company watcher.

The base watcher remains fail-closed. This layer adds narrowly-scoped recovery for
provider-side delivery changes without weakening source trust:

* Beckett canonical pages may redirect to maintenance.beckett.com. Pricing/news
  stay degraded and last-good facts are retained; a separate status-only source
  proves provider availability and can never promote price facts.
* TAG's primary pricing page can render service cards in a way the generic parser
  cannot see. When that exact official source yields no verified services, a second
  official TAG collection page is parsed as a bounded pricing fallback.
* Requests are memoized for one collection transaction so Beckett maintenance
  status validation reuses the already-fetched canonical grading response instead
  of performing a third request.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
import json
import urllib.request

import grading_company_watch as base
from safe_runtime import atomic_write_json, safe_urlopen

OUT = base.OUT
MAINTENANCE_HOST = "maintenance.beckett.com"
BECKETT_HOSTS = {"beckett.com", "www.beckett.com"}
TAG_HOSTS = {"taggrading.com", "www.taggrading.com"}
FETCH_ALLOWED_HOSTS = set(base.ALLOWED_HOSTS) | {MAINTENANCE_HOST}
BGS_CANONICAL_STATUS_URL = "https://www.beckett.com/grading"
STATUS_SOURCE_ID = "bgs-maintenance-status"
TAG_PRIMARY_SOURCE_ID = "tag-pricing"
TAG_FALLBACK_SOURCE_ID = "tag-pricing-official-fallback"
TAG_FALLBACK_URL = "https://taggrading.com/collections/grading-services-official"
TAG_REQUIRED_FALLBACK_SERVICES = {"Basic", "Standard", "Priority"}


class BeckettMaintenanceRedirect(ValueError):
    """Canonical Beckett content is temporarily replaced by the maintenance site."""


def _request(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": base.UA,
        "Accept-Language": "ko-KR,ja-JP;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    with safe_urlopen(req, timeout=20, allowed_hosts=FETCH_ALLOWED_HOSTS, max_redirects=3) as response:
        final_url = str(response.geturl() or url)
        raw = response.read(base.MAX_PAGE_BYTES).decode("utf-8", "ignore")
    return raw, final_url


def _make_cached_requester(requester):
    """Memoize exact URLs for one collection transaction only.

    The cache is intentionally not persisted between runs: every scheduled watch still
    performs fresh network checks, while repeated validation of the same canonical URL
    within one run avoids duplicate provider traffic.
    """
    cache: dict[str, tuple[str, str]] = {}
    stats = {"network_calls": 0, "cache_hits": 0}

    def cached(url: str) -> tuple[str, str]:
        if url in cache:
            stats["cache_hits"] += 1
            return cache[url]
        result = requester(url)
        cache[url] = result
        stats["network_calls"] += 1
        return result

    return cached, stats


def _collector_fetch(url: str, *, requester=None) -> str:
    requester = requester or _request
    raw, final_url = requester(url)
    initial_host = (urlsplit(url).hostname or "").lower().rstrip(".")
    final_host = (urlsplit(final_url).hostname or "").lower().rstrip(".")
    if initial_host in BECKETT_HOSTS and final_host == MAINTENANCE_HOST:
        raise BeckettMaintenanceRedirect(
            f"canonical Beckett source temporarily redirected to {MAINTENANCE_HOST}"
        )
    return raw


def _maintenance_status(*, requester=None) -> dict:
    # Trust is anchored at the canonical Beckett URL. The temporary host is
    # accepted only when Beckett itself redirects there during this request.
    requester = requester or _request
    raw, final_url = requester(BGS_CANONICAL_STATUS_URL)
    final_host = (urlsplit(final_url).hostname or "").lower().rstrip(".")
    if final_host != MAINTENANCE_HOST:
        raise ValueError("Beckett canonical page is not in the expected maintenance mode")
    text = base._text(raw)
    low = text.casefold()
    marker_groups = (
        ("beckett",),
        ("temporary submission form", "temporary submission"),
        ("base",),
        ("standard",),
        ("express",),
    )
    if len(text) < 200 or any(not any(marker in low for marker in group) for group in marker_groups):
        raise ValueError("Beckett maintenance page identity/service markers are incomplete")
    services = [name for name in ("Base", "Standard", "Express", "Priority") if name.casefold() in low]
    return {
        "company": "BGS",
        "source_id": STATUS_SOURCE_ID,
        "kind": "status",
        "market": "US",
        "currency": "USD",
        "url": BGS_CANONICAL_STATUS_URL,
        "effective_url": final_url,
        "status": "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signal_fingerprint": sha256(text.encode("utf-8")).hexdigest(),
        "services": [],
        "announcements": [],
        "maintenance_mode": True,
        "available_service_labels": services,
        "verified_official_source": True,
        "parser_version": base.PARSER_VERSION,
        "fact_scope": "service_availability_status_only_no_price_promotion",
    }


def _tag_pricing_fallback(*, requester=None) -> dict:
    """Parse TAG's official grading-services collection when /pages/pricing collapses.

    This is a factual pricing source, unlike the Beckett maintenance status source.
    Promotion requires an official TAG final host plus at least three expected service
    tiers, preventing a generic landing page or partial error page from becoming price
    truth.
    """
    requester = requester or _request
    raw, final_url = requester(TAG_FALLBACK_URL)
    final_host = (urlsplit(final_url).hostname or "").lower().rstrip(".")
    if final_host not in TAG_HOSTS:
        raise ValueError("TAG fallback escaped the official TAG host")
    text = base._text(raw)
    services = base.parse_services("TAG", "US", "USD", text, TAG_FALLBACK_URL)
    names = {str(row.get("name") or "") for row in services if isinstance(row, dict)}
    if len(services) < 3 or not TAG_REQUIRED_FALLBACK_SERVICES.issubset(names):
        raise ValueError("TAG official fallback yielded insufficient verified service tiers")
    if any(
        row.get("verified_official_source") is not True
        or row.get("parser_version") != base.PARSER_VERSION
        or not isinstance(row.get("fee"), (int, float))
        or float(row["fee"]) <= 0
        for row in services
    ):
        raise ValueError("TAG official fallback service validation failed")
    return {
        "company": "TAG",
        "source_id": TAG_FALLBACK_SOURCE_ID,
        "kind": "pricing",
        "market": "US",
        "currency": "USD",
        "url": TAG_FALLBACK_URL,
        "effective_url": final_url,
        "status": "ok",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signal_fingerprint": sha256(text.encode("utf-8")).hexdigest(),
        "services": services,
        "announcements": [],
        "verified_official_source": True,
        "parser_version": base.PARSER_VERSION,
        "fact_scope": "official_pricing_and_availability",
    }


def _is_maintenance_error(row: dict) -> bool:
    message = str(row.get("last_error") or row.get("error") or "").casefold()
    return "beckettmaintenanceredirect" in message or MAINTENANCE_HOST in message


def _recompute_summary(data: dict) -> None:
    companies = data.get("companies") if isinstance(data.get("companies"), dict) else {}
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    health = []
    for company in companies.values():
        if isinstance(company, dict) and isinstance(company.get("source_health"), list):
            health.extend(row for row in company["source_health"] if isinstance(row, dict))
    summary = data.setdefault("summary", {})
    summary["companies"] = len(base.WATCH_SOURCES)
    summary["sources"] = len(health)
    summary["healthy_sources"] = sum(row.get("status") == "ok" for row in health)
    summary["degraded_sources"] = sum(row.get("status") != "ok" for row in health)

    healthy_pricing_sources = []
    healthy_pricing_companies = set()
    for source_id, row in sources.items():
        if not isinstance(row, dict) or str(row.get("status") or "").lower() not in {"ok", "healthy"}:
            continue
        if str(row.get("kind") or "") not in {"pricing", "pricing_news"}:
            continue
        services = row.get("services")
        if not isinstance(services, list) or not services:
            continue
        company = str(row.get("company") or "").upper()
        if company in base.WATCH_SOURCES:
            healthy_pricing_sources.append(str(source_id))
            healthy_pricing_companies.add(company)
    summary["healthy_pricing_sources"] = len(healthy_pricing_sources)
    summary["grading_companies_with_healthy_pricing"] = len(healthy_pricing_companies)
    summary["pricing_degraded_companies"] = sorted(set(base.WATCH_SOURCES) - healthy_pricing_companies)


def _upsert_health(company: dict, row: dict) -> None:
    rows = company.setdefault("source_health", [])
    if not isinstance(rows, list):
        company["source_health"] = rows = []
    source_id = row.get("source_id")
    rows[:] = [item for item in rows if not isinstance(item, dict) or item.get("source_id") != source_id]
    rows.append(row)


def _install_tag_fallback(data: dict, status_row: dict) -> None:
    sources = data.setdefault("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("invalid grading source map")
    sources[TAG_FALLBACK_SOURCE_ID] = status_row
    companies = data.setdefault("companies", {})
    if not isinstance(companies, dict):
        raise ValueError("invalid grading company map")
    company = companies.setdefault("TAG", {"markets": {}, "source_health": []})
    if not isinstance(company, dict):
        raise ValueError("invalid TAG company payload")
    markets = company.setdefault("markets", {})
    if not isinstance(markets, dict):
        company["markets"] = markets = {}
    markets["US"] = {
        "currency": "USD",
        "source": TAG_FALLBACK_URL,
        "services": deepcopy(status_row["services"]),
        "verified_official_source": True,
    }
    _upsert_health(company, {
        "source_id": TAG_FALLBACK_SOURCE_ID,
        "status": "ok",
        "url": TAG_FALLBACK_URL,
        "effective_url": status_row["effective_url"],
        "fact_scope": status_row["fact_scope"],
    })


def collect(previous: dict | None = None, fetcher=None, requester=None) -> dict:
    previous = previous if isinstance(previous, dict) else base._load_previous(OUT)
    requester = requester or _request
    cached_request, request_stats = _make_cached_requester(requester)

    def collector_fetch(url: str) -> str:
        return _collector_fetch(url, requester=cached_request)

    data = base.collect(previous, fetcher=fetcher or collector_fetch)
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    resilience = data.setdefault("resilience", {})

    bgs_rows = [sources.get("bgs-pricing"), sources.get("bgs-news")]
    maintenance_seen = any(isinstance(row, dict) and _is_maintenance_error(row) for row in bgs_rows)
    if maintenance_seen:
        # Preserve the canonical pricing/news failures as degraded evidence. This
        # prevents the maintenance landing page from being misread as a pricing page.
        for row in bgs_rows:
            if isinstance(row, dict) and _is_maintenance_error(row):
                row["failure_class"] = "planned_maintenance"
        try:
            status_row = _maintenance_status(requester=cached_request)
        except Exception as exc:
            resilience["bgs_maintenance_status"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "price_facts_promoted": False,
            }
        else:
            sources[STATUS_SOURCE_ID] = status_row
            bgs_company = (data.get("companies") or {}).get("BGS")
            if isinstance(bgs_company, dict):
                _upsert_health(bgs_company, {
                    "source_id": STATUS_SOURCE_ID,
                    "status": "ok",
                    "url": BGS_CANONICAL_STATUS_URL,
                    "effective_url": status_row["effective_url"],
                    "maintenance_mode": True,
                })
            resilience["bgs_maintenance_status"] = {
                "ok": True,
                "source_id": STATUS_SOURCE_ID,
                "effective_url": status_row["effective_url"],
                "available_service_labels": status_row["available_service_labels"],
                "price_facts_promoted": False,
            }

    tag_primary = sources.get(TAG_PRIMARY_SOURCE_ID)
    tag_needs_fallback = (
        isinstance(tag_primary, dict)
        and str(tag_primary.get("status") or "").lower() not in {"ok", "healthy"}
        and not (tag_primary.get("services") or [])
    )
    if tag_needs_fallback:
        try:
            tag_status = _tag_pricing_fallback(requester=cached_request)
        except Exception as exc:
            resilience["tag_pricing_fallback"] = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "price_facts_promoted": False,
            }
        else:
            _install_tag_fallback(data, tag_status)
            resilience["tag_pricing_fallback"] = {
                "ok": True,
                "source_id": TAG_FALLBACK_SOURCE_ID,
                "effective_url": tag_status["effective_url"],
                "service_count": len(tag_status["services"]),
                "price_facts_promoted": True,
                "promotion_scope": "official_tag_pricing_only",
            }

    resilience["request_efficiency"] = {
        "transaction_cache": True,
        "network_calls": request_stats["network_calls"],
        "cache_hits": request_stats["cache_hits"],
        "persistent_cache": False,
    }
    _recompute_summary(data)
    return data


def update(path=OUT) -> dict:
    data = collect(base._load_previous(path))
    atomic_write_json(path, data, suffix=".grading-company-resilient.tmp")
    return data


def main() -> int:
    data = update()
    print(json.dumps({
        "checked_at": data.get("checked_at"),
        "summary": data.get("summary", {}),
        "resilience": data.get("resilience", {}),
        "recent_changes": (data.get("recent_changes") or [])[-10:],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
