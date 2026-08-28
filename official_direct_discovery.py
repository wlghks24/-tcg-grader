#!/usr/bin/env python3
"""Direct official-site discovery independent from public search engines.

v116 goals
- Crawl curated official Pokemon / ONE PIECE / NARUTO entry/news pages directly.
- Extract event/product/promo/news links without depending on Bing/Google/DDG indexing.
- Keep results as candidates: an official domain is authoritative for source identity,
  but page contents are still validated by the existing event/cross-check pipeline.
- Return provider="official_direct" so adaptive learning can measure its value.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from adaptive_collection_learner import GAME_CONFIG, canonical_game
from safe_runtime import env_int, safe_urlopen

TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)

OFFICIAL_ENTRY_PAGES = {
    "포켓몬": {
        "KR": (
            "https://www.pokemonkorea.co.kr/",
        ),
        "JP": (
            "https://www.pokemon-card.com/info/",
            "https://www.pokemon-card.com/",
        ),
        "US": (
            "https://www.pokemon.com/us/pokemon-news",
        ),
    },
    "원피스": {
        "KR": (
            "https://onepiece-cardgame.kr/",
        ),
        "JP": (
            "https://www.onepiece-cardgame.com/",
        ),
        "US": (
            "https://en.onepiece-cardgame.com/",
        ),
    },
    "나루토": {
        "KR": (
            "https://www.naruto-cardgame.com/asia-en/",
        ),
        "JP": (
            "https://www.naruto-cardgame.com/",
            "https://naruto-official.com/",
        ),
        "US": (
            "https://www.naruto-cardgame.com/en/",
            "https://naruto-official.com/en/news/",
        ),
    },
}

EVENT_TERMS = (
    "news", "event", "events", "campaign", "promo", "promotion", "tournament",
    "release", "product", "products", "collab", "collaboration", "popup", "pop-up",
    "giveaway", "preorder", "restock", "limited", "exclusive", "movie", "film",
    "행사", "이벤트", "프로모", "콜라보", "팝업", "출시", "발매", "재발매", "한정",
    "증정", "대회", "사전예약", "영화",
    "ニュース", "イベント", "キャンペーン", "プロモ", "コラボ", "発売", "再販",
    "限定", "配布", "大会", "映画", "商品",
)
PATH_HINTS = (
    "/news", "/event", "/events", "/campaign", "/promo", "/product", "/products",
    "/tournament", "/release", "/info", "/topics", "/article", "/articles",
)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._href: str | None = None
        self._parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self._href = html.unescape(str(href))
                self._parts = []

    def handle_data(self, data):
        if self._href is not None:
            self._parts.append(str(data))

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", " ".join(self._parts)).strip()
            self.links.append((self._href, text))
            self._href = None
            self._parts = []


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _allowed_hosts(game: str) -> set[str]:
    cfg = GAME_CONFIG.get(game, {})
    return {str(x).lower() for x in (cfg.get("official_hosts") or ())}


def _clean_title(text: str, url: str) -> str:
    value = re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()
    if value:
        return value[:240]
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    leaf = path.rsplit("/", 1)[-1] if path else "Official news"
    leaf = re.sub(r"[-_]+", " ", urllib.parse.unquote(leaf)).strip()
    return (leaf or "Official news")[:240]


def _looks_relevant(title: str, url: str) -> bool:
    hay = f"{title} {urllib.parse.urlsplit(url).path}".lower()
    if any(term.lower() in hay for term in EVENT_TERMS):
        return True
    path = urllib.parse.urlsplit(url).path.lower()
    return any(hint in path for hint in PATH_HINTS)


def parse_official_links(game: str, region: str, base_url: str, raw_html: str, limit: int = 12) -> list[dict]:
    parser = _AnchorParser()
    parser.feed(raw_html)
    allowed = _allowed_hosts(game)
    rows: list[dict] = []
    seen: set[str] = set()
    for href, anchor_text in parser.links:
        absolute = urllib.parse.urljoin(base_url, href)
        try:
            parsed = urllib.parse.urlsplit(absolute)
        except ValueError:
            continue
        if parsed.scheme != "https" or _host(absolute) not in allowed:
            continue
        clean_url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
        if clean_url in seen:
            continue
        title = _clean_title(anchor_text, clean_url)
        if not _looks_relevant(title, clean_url):
            continue
        seen.add(clean_url)
        rows.append({
            "title": title,
            "url": clean_url,
            "verified": False,
            "official_hint": True,
            "search_provider": "official_direct",
            "query_family": "official-direct",
            "query_region": region,
            "official_entry_page": base_url,
        })
        if len(rows) >= max(3, min(30, int(limit))):
            break
    return rows


def collect_game(keyword: str, limit: int = 8) -> dict:
    game = canonical_game(keyword)
    pages = OFFICIAL_ENTRY_PAGES.get(game, {})
    allowed = _allowed_hosts(game)
    rows: list[dict] = []
    errors: list[str] = []
    page_status: list[dict] = []
    for region in ("KR", "JP", "US"):
        region_rows = 0
        for page in pages.get(region, ()):
            req = urllib.request.Request(page, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-OfficialDirect/116"})
            try:
                with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=allowed) as response:
                    final_url = response.geturl()
                    body = response.read(1_200_000).decode("utf-8", "replace")
                parsed = parse_official_links(game, region, final_url, body, limit=max(limit, 10))
                rows.extend(parsed)
                region_rows += len(parsed)
                page_status.append({"region": region, "url": page, "ok": True, "result_count": len(parsed)})
            except Exception as exc:
                errors.append(f"{game}/{region} {page}: {type(exc).__name__}: {exc}"[:700])
                page_status.append({"region": region, "url": page, "ok": False, "result_count": 0, "error": type(exc).__name__})
        # Keep scanning all three regions even when one region has no results.
    deduped: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        url = str(row.get("url") or "")
        if url in seen:
            continue
        seen.add(url)
        deduped.append(row)
    return {
        "keyword": keyword,
        "game": game,
        "ok": bool(deduped) or any(x.get("ok") for x in page_status),
        "degraded": bool(errors),
        "results": deduped[: max(3, min(30, int(limit)))],
        "result_count": len(deduped[: max(3, min(30, int(limit)))]),
        "errors": errors[:20],
        "pages": page_status,
        "provider": "official_direct",
    }


if __name__ == "__main__":
    import json
    print(json.dumps({k: collect_game(k) for k in ("포켓몬", "원피스", "나루토")}, ensure_ascii=False, indent=2))
