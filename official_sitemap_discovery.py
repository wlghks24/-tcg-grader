#!/usr/bin/env python3
"""Official sitemap discovery independent from search engines.

v117 goals
- Probe a small, bounded set of sitemap endpoints on curated official hosts.
- Follow one sitemap-index level and keep only event/news/product-like URLs.
- Fetch titles for the newest relevant URLs so candidate text is useful.
- Never leave the official host allowlist and never infer content trust from frequency.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from adaptive_collection_learner import GAME_CONFIG, canonical_game
from official_direct_discovery import OFFICIAL_ENTRY_PAGES, PATH_HINTS, EVENT_TERMS
from safe_runtime import env_int, safe_urlopen

TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
SITEMAP_NAMES = ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-news.xml", "/sitemap_news.xml")


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _allowed_hosts(game: str) -> set[str]:
    cfg = GAME_CONFIG.get(game, {})
    return {str(x).lower() for x in (cfg.get("official_hosts") or ())}


def _roots(game: str) -> list[tuple[str, str]]:
    roots = []
    seen = set()
    for region in ("KR", "JP", "US"):
        for page in (OFFICIAL_ENTRY_PAGES.get(game, {}) or {}).get(region, ()):
            parsed = urllib.parse.urlsplit(page)
            if not parsed.hostname:
                continue
            root = f"https://{parsed.hostname}"
            key = (region, root)
            if key not in seen:
                seen.add(key)
                roots.append(key)
    return roots


def _fetch_xml(url: str, allowed: set[str]) -> tuple[ET.Element | None, str | None]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-Sitemap/117"})
    try:
        with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=allowed) as response:
            raw = response.read(2_000_000)
        return ET.fromstring(raw), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"[:400]


def _xml_locs(root: ET.Element) -> list[tuple[str, str | None]]:
    rows = []
    tag = root.tag.lower()
    if tag.endswith("sitemapindex"):
        for node in list(root):
            loc = next((str(x.text or "").strip() for x in list(node) if x.tag.lower().endswith("loc")), "")
            lastmod = next((str(x.text or "").strip() for x in list(node) if x.tag.lower().endswith("lastmod")), None)
            if loc:
                rows.append((loc, lastmod))
        return rows
    if tag.endswith("urlset"):
        for node in list(root):
            loc = next((str(x.text or "").strip() for x in list(node) if x.tag.lower().endswith("loc")), "")
            lastmod = next((str(x.text or "").strip() for x in list(node) if x.tag.lower().endswith("lastmod")), None)
            if loc:
                rows.append((loc, lastmod))
    return rows


def _looks_relevant(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    hay = urllib.parse.unquote(f"{parsed.path} {parsed.query}").lower()
    if any(hint in parsed.path.lower() for hint in PATH_HINTS):
        return True
    return any(term.lower() in hay for term in EVENT_TERMS)


def _page_title(url: str, allowed: set[str]) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-SitemapTitle/117"})
    try:
        with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=allowed) as response:
            raw = response.read(500_000).decode("utf-8", "replace")
        for pattern in (
            re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', re.I),
            re.compile(r'<title[^>]*>(.*?)</title>', re.I | re.S),
        ):
            match = pattern.search(raw)
            if match:
                title = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
                if title:
                    return title[:240]
    except Exception:
        pass
    path = urllib.parse.unquote(urllib.parse.urlsplit(url).path.rstrip("/")).rsplit("/", 1)[-1]
    path = re.sub(r"[-_]+", " ", path).strip()
    return (path or "Official sitemap update")[:240]


def collect_game(keyword: str, limit: int = 6) -> dict:
    game = canonical_game(keyword)
    allowed = _allowed_hosts(game)
    discovered: list[dict] = []
    status: list[dict] = []
    errors: list[str] = []
    for region, root_url in _roots(game):
        root_host = _host(root_url)
        if root_host not in allowed:
            continue
        host_candidates = []
        for name in SITEMAP_NAMES:
            sitemap_url = root_url.rstrip("/") + name
            xml, error = _fetch_xml(sitemap_url, allowed)
            if xml is None:
                if error:
                    errors.append(f"{game}/{region} {sitemap_url}: {error}"[:600])
                status.append({"region": region, "url": sitemap_url, "ok": False, "result_count": 0})
                continue
            locs = _xml_locs(xml)
            # Follow only a few child sitemap files to keep tablet traffic bounded.
            if xml.tag.lower().endswith("sitemapindex"):
                expanded = []
                for child_url, _lastmod in locs[:4]:
                    if _host(child_url) not in allowed:
                        continue
                    child, child_error = _fetch_xml(child_url, allowed)
                    if child is None:
                        if child_error:
                            errors.append(f"{game}/{region} {child_url}: {child_error}"[:600])
                        continue
                    expanded.extend(_xml_locs(child))
                locs = expanded
            relevant = []
            for url, lastmod in locs:
                if not url.startswith("https://") or _host(url) not in allowed or not _looks_relevant(url):
                    continue
                relevant.append((url, lastmod))
            relevant.sort(key=lambda x: str(x[1] or ""), reverse=True)
            host_candidates.extend(relevant[: max(limit * 2, 8)])
            status.append({"region": region, "url": sitemap_url, "ok": True, "result_count": len(relevant)})
            if relevant:
                break
        seen = set()
        for url, lastmod in host_candidates:
            if url in seen:
                continue
            seen.add(url)
            discovered.append({
                "title": _page_title(url, allowed),
                "url": url,
                "published_at": lastmod,
                "verified": False,
                "official_hint": True,
                "search_provider": "official_sitemap",
                "query_family": "official-sitemap",
                "query_region": region,
                "sitemap_host": root_host,
            })
            if sum(1 for x in discovered if x.get("query_region") == region) >= max(2, min(8, int(limit))):
                break
    deduped = []
    seen = set()
    for row in discovered:
        url = str(row.get("url") or "")
        if url in seen:
            continue
        seen.add(url)
        deduped.append(row)
    return {
        "keyword": keyword,
        "game": game,
        "ok": bool(deduped) or any(x.get("ok") for x in status),
        "degraded": bool(errors),
        "results": deduped[: max(2, min(20, int(limit)))],
        "result_count": len(deduped[: max(2, min(20, int(limit)))]),
        "sitemaps": status,
        "errors": errors[:30],
        "provider": "official_sitemap",
    }


if __name__ == "__main__":
    import json
    print(json.dumps({k: collect_game(k) for k in ("포켓몬", "원피스", "나루토")}, ensure_ascii=False, indent=2))
