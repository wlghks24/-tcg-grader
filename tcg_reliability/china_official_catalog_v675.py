"""V675 shadow-only Chinese official catalog parsing with per-link isolation.

This is not enabled in update_market_watch. It reuses V571's strict candidate
criteria and bounded network retry policy without altering the SHA-pinned V571
source. Only offline evaluation/independent PR checks are authorized.
"""
from __future__ import annotations

import datetime as dt
from html import escape
from urllib.request import Request

from safe_runtime import safe_urlopen
from tcg_reliability import china_official_catalog_v571 as legacy

SOURCES = legacy.SOURCES
HOSTS = legacy.HOSTS
MAX_BYTES = legacy.MAX_BYTES
MAX_ROWS_PER_SOURCE = legacy.MAX_ROWS_PER_SOURCE
MAX_ROWS_TOTAL = legacy.MAX_ROWS_TOTAL


def safe_link(index_url: str, href: str, edition: str) -> str | None:
    """Reject one malformed URL without aborting the other anchor candidates."""
    try:
        return legacy.safe_link(index_url, href, edition)
    except (ValueError, UnicodeError):
        return None


def parse_official_html(
    body: str, region: str, locale: str, url: str, checked_at: str,
) -> list[dict]:
    """Reapply V571's unmodified product gates to individually validated anchors."""
    if (region, locale, url) not in SOURCES:
        return []
    if not isinstance(body, str) or len(body) > MAX_BYTES:
        return []
    parser = legacy._Anchors()
    parser.feed(body)
    rows: list[dict] = []
    seen: set[str] = set()
    for entry in parser.links:
        target = safe_link(url, entry.get("href"), region)
        if not target or target in seen:
            continue
        # Reconstruct a minimal, escaped fragment so the original V571 parser
        # controls every title, BOX, publication and evidence-safety decision.
        context = "".join("<span>" + escape(s, quote=False) + "</span>"
                          for s in entry["context"])
        label = " ".join(escape(s, quote=False) for s in entry["text"])
        fragment = (
            context + '<a href="' + escape(target, quote=True) + '">'
            + label + "</a>"
        )
        try:
            qualified = legacy.parse_official_html(
                fragment, region, locale, url, checked_at
            )
        except (ValueError, UnicodeError):
            continue
        if qualified:
            rows.append(qualified[0])
            seen.add(target)
            if len(rows) >= MAX_ROWS_PER_SOURCE:
                break
    return rows


def _network(url: str) -> str:
    request = Request(
        url, headers={
            "User-Agent": "TCG-Grader-OfficialCatalog/1.0",
            "Accept": "text/html",
            "Accept-Language": "zh-CN,zh;q=0.8",
        }
    )
    with safe_urlopen(
        request, timeout=6, allowed_hosts=HOSTS, max_redirects=1
    ) as response:
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("official index too large")
        return data.decode("utf-8", "replace")


def fetch_official_products(*, fetcher=None, now: dt.datetime | None = None) -> dict:
    """Shadow collector: preserve V571 limits, HTTP backoff and per-locale HOLD."""
    checked_at = (now or dt.datetime.now(dt.timezone.utc)).astimezone(
        dt.timezone.utc
    ).isoformat(timespec="seconds")
    load = fetcher or _network
    rows: list[dict] = []
    errors: list[dict] = []
    coverage: list[dict] = []
    for region, locale, url in SOURCES:
        try:
            candidates = parse_official_html(
                legacy._fetch_with_retry(load, url),
                region, locale, url, checked_at,
            )
            if not candidates:
                raise ValueError("no qualified official BOX candidates")
            rows.extend(candidates)
            coverage.append({
                "region": region, "locale": locale,
                "count": len(candidates), "checked_at": checked_at,
            })
        except (OSError, ValueError, TimeoutError, UnicodeError) as exc:
            errors.append({
                "region": region, "locale": locale,
                "error": type(exc).__name__,
            })
    return {
        "items": rows[:MAX_ROWS_TOTAL],
        "coverage": coverage, "errors": errors, "checked_at": checked_at,
        "automatic": True, "prices_verified": False, "holdings_created": False,
    }
