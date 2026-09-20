#!/usr/bin/env python3
"""Maintenance-aware compatibility layer for the official grading-company watcher.

The base watcher remains fail-closed.  This layer adds one narrowly-scoped recovery
path for Beckett: when a canonical beckett.com source is officially redirected to
maintenance.beckett.com, pricing/news rows remain degraded and retain last-good
facts, while a separately verified maintenance-status row proves that BGS itself
is still observable.  No maintenance page is allowed to invent or overwrite price
facts.
"""
from __future__ import annotations

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
FETCH_ALLOWED_HOSTS = set(base.ALLOWED_HOSTS) | {MAINTENANCE_HOST}
BGS_CANONICAL_STATUS_URL = "https://www.beckett.com/grading"
STATUS_SOURCE_ID = "bgs-maintenance-status"


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


def _collector_fetch(url: str) -> str:
    raw, final_url = _request(url)
    initial_host = (urlsplit(url).hostname or "").lower().rstrip(".")
    final_host = (urlsplit(final_url).hostname or "").lower().rstrip(".")
    if initial_host in BECKETT_HOSTS and final_host == MAINTENANCE_HOST:
        raise BeckettMaintenanceRedirect(
            f"canonical Beckett source temporarily redirected to {MAINTENANCE_HOST}"
        )
    return raw


def _maintenance_status() -> dict:
    # Trust is anchored at the canonical Beckett URL.  The temporary host is
    # accepted only when Beckett itself redirects there during this request.
    raw, final_url = _request(BGS_CANONICAL_STATUS_URL)
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


def _is_maintenance_error(row: dict) -> bool:
    message = str(row.get("last_error") or row.get("error") or "").casefold()
    return "beckettmaintenanceredirect" in message or MAINTENANCE_HOST in message


def _recompute_summary(data: dict) -> None:
    companies = data.get("companies") if isinstance(data.get("companies"), dict) else {}
    health = []
    for company in companies.values():
        if isinstance(company, dict) and isinstance(company.get("source_health"), list):
            health.extend(row for row in company["source_health"] if isinstance(row, dict))
    summary = data.setdefault("summary", {})
    summary["companies"] = len(base.WATCH_SOURCES)
    summary["sources"] = len(health)
    summary["healthy_sources"] = sum(row.get("status") == "ok" for row in health)
    summary["degraded_sources"] = sum(row.get("status") != "ok" for row in health)


def collect(previous: dict | None = None, fetcher=None) -> dict:
    previous = previous if isinstance(previous, dict) else base._load_previous(OUT)
    data = base.collect(previous, fetcher=fetcher or _collector_fetch)
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    bgs_rows = [sources.get("bgs-pricing"), sources.get("bgs-news")]
    maintenance_seen = any(isinstance(row, dict) and _is_maintenance_error(row) for row in bgs_rows)
    if not maintenance_seen:
        return data

    # Preserve the canonical pricing/news failures as degraded evidence.  This
    # prevents the maintenance landing page from being misread as a pricing page.
    for row in bgs_rows:
        if isinstance(row, dict) and _is_maintenance_error(row):
            row["failure_class"] = "planned_maintenance"

    try:
        status_row = _maintenance_status()
    except Exception as exc:
        data.setdefault("resilience", {})["bgs_maintenance_status"] = {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "price_facts_promoted": False,
        }
        return data

    sources[STATUS_SOURCE_ID] = status_row
    bgs_company = (data.get("companies") or {}).get("BGS")
    if isinstance(bgs_company, dict):
        rows = bgs_company.setdefault("source_health", [])
        if isinstance(rows, list):
            rows.append({
                "source_id": STATUS_SOURCE_ID,
                "status": "ok",
                "url": BGS_CANONICAL_STATUS_URL,
                "effective_url": status_row["effective_url"],
                "maintenance_mode": True,
            })
    data.setdefault("resilience", {})["bgs_maintenance_status"] = {
        "ok": True,
        "source_id": STATUS_SOURCE_ID,
        "effective_url": status_row["effective_url"],
        "available_service_labels": status_row["available_service_labels"],
        "price_facts_promoted": False,
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
