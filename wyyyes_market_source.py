#!/usr/bin/env python3
"""Bounded public WYYYES market collector.

Only public product pages are used.  Login/private APIs are never bypassed.
WYYYES prices are stored as platform quotes and never overwrite the canonical
verified market price.  Listing/offer prices stay distinct from explicit sold
or auction-complete evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import json
import re
from urllib.parse import quote_plus, urlparse
from urllib.request import Request
from xml.etree import ElementTree as ET

from safe_runtime import env_int, html_to_text, safe_urlopen

UA = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/126.0 Safari/537.36 TCG-Grader/2.0"
WYYYES_HOSTS = {"wyyyes.com", "www.wyyyes.com"}
SEARCH_HOSTS = {"bing.com", "www.bing.com"}
MAX_RESULTS = env_int("TCG_WYYYES_MAX_RESULTS", 18, 3, 36)
LAST_GOOD_SECONDS = env_int("TCG_WYYYES_LAST_GOOD_SECONDS", 24 * 60 * 60, 60 * 60, 72 * 60 * 60)
SEARCHES = (
    "site:wyyyes.com/category/pokemon-card 포켓몬 카드",
    "site:wyyyes.com/category/trading-cards 원피스 카드",
    "site:wyyyes.com/category/trading-cards 나루토 카드",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _rss(query: str, limit: int = 8) -> list[dict]:
    url = "https://www.bing.com/search?format=rss&q=" + quote_plus(query)
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7,ja;q=0.6"})
    with safe_urlopen(req, timeout=12, allowed_hosts=SEARCH_HOSTS) as response:
        raw = response.read(1_500_000)
    root = ET.fromstring(raw)
    rows = []
    for item in root.findall(".//item")[:limit]:
        link = (item.findtext("link") or "").strip()
        host = (urlparse(link).hostname or "").lower()
        if host not in WYYYES_HOSTS:
            continue
        path = urlparse(link).path.lower()
        if "/category/" not in path:
            continue
        rows.append({
            "url": link[:900],
            "title": _strip_tags(item.findtext("title") or "")[:260],
            "snippet": _strip_tags(item.findtext("description") or "")[:700],
        })
    return rows


def _fetch_public(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host not in WYYYES_HOSTS:
        raise ValueError("unapproved WYYYES host")
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7,ja;q=0.6"})
    with safe_urlopen(req, timeout=12, allowed_hosts=WYYYES_HOSTS) as response:
        ctype = (response.headers.get("Content-Type") or "").lower()
        if "html" not in ctype:
            raise ValueError("WYYYES response is not HTML")
        return response.read(1_500_000).decode("utf-8", "replace")


def _extract_title(html: str, fallback: str = "") -> str:
    for pattern in (
        r"<h1[^>]*>(.*?)</h1>",
        r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)",
        r"<title[^>]*>(.*?)</title>",
    ):
        match = re.search(pattern, html or "", re.I | re.S)
        if match:
            title = _strip_tags(match.group(1))
            title = re.sub(r"\s*\|\s*WYYYES.*$", "", title, flags=re.I).strip()
            if title:
                return title[:240]
    return _strip_tags(fallback)[:240]


def _extract_price_krw(text: str) -> int:
    candidates = []
    for raw in re.findall(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,9})\s*원", text or ""):
        try:
            value = int(raw.replace(",", ""))
        except ValueError:
            continue
        if 100 <= value <= 100_000_000:
            candidates.append(value)
    return candidates[0] if candidates else 0


def infer_card_region(text: str) -> str:
    low = (text or "").lower()
    if any(token in low for token in ("일본판", "일판", "일어판", "japanese", "japan", "日版", "日本版")):
        return "JP"
    if any(token in low for token in ("한국판", "한글판", "국판", "korean", "korea")):
        return "KR"
    if any(token in low for token in ("미국판", "영문판", "english", "usa", "u.s.")):
        return "US"
    return "UNKNOWN"


def infer_game(text: str) -> str:
    low = (text or "").lower()
    if any(token in low for token in ("포켓몬", "pokemon", "ポケモン")):
        return "Pokémon"
    if any(token in low for token in ("원피스", "one piece", "ワンピース")):
        return "ONE PIECE"
    if any(token in low for token in ("나루토", "naruto")):
        return "NARUTO"
    return ""


def infer_grade(text: str) -> tuple[str, int | None]:
    value = text or ""
    # Prefer title/description evidence over platform badges because a badge can be
    # stale or mislabeled for a differently graded item.
    match = re.search(r"\b(PSA|BGS|CGC|TAG|BRG)\s*[-:]?\s*(10|[1-9])\b", value, re.I)
    if not match:
        return "", None
    return match.group(1).upper(), int(match.group(2))


def infer_price_type(text: str) -> str:
    low = (text or "").lower()
    if any(token in low for token in ("판매완료", "거래완료", "거래 완료", "낙찰완료", "낙찰 완료", "sold out", "sold")):
        return "sold"
    if any(token in low for token in ("낙찰", "경매 종료", "경매종료")):
        return "auction_result"
    return "asking"


def _card_number(text: str) -> str:
    value = text or ""
    patterns = (
        r"\b[A-Z]{1,5}\d{0,2}[A-Z]?[- ]?\d{2,3}(?:/\d{2,3})?\b",
        r"\b\d{2,3}/\d{2,3}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, value, re.I)
        if match:
            return re.sub(r"\s+", "", match.group(0).upper())[:40]
    return ""


def parse_public_listing(html: str, url: str, fallback_title: str = "", snippet: str = "") -> dict | None:
    title = _extract_title(html, fallback_title)
    page_text = html_to_text(html)
    combined = " ".join(part for part in (title, snippet, page_text[:30_000]) if part)
    price = _extract_price_krw(combined)
    game = infer_game(combined)
    if not title or not price or not game:
        return None
    company, grade = infer_grade(" ".join((title, snippet, page_text[:8_000])))
    quote_type = infer_price_type(page_text)
    return {
        "platform": "WYYYES",
        "market_region": "KR",
        "card_region": infer_card_region(combined),
        "game": game,
        "title": title,
        "card_number": _card_number(combined),
        "grading_company": company,
        "grade": grade,
        "currency": "KRW",
        "price": price,
        "price_type": quote_type,
        "is_completed_sale": quote_type in {"sold", "auction_result"},
        "source_url": url,
        "collected_at": _now_iso(),
        "evidence_policy": "public-page-only; asking prices never promoted to sold",
    }


def _fresh_previous(previous: list[dict] | None) -> list[dict]:
    rows = []
    now = datetime.now(timezone.utc)
    for row in previous or []:
        if not isinstance(row, dict) or row.get("platform") != "WYYYES":
            continue
        stamp = str(row.get("collected_at") or "").strip()
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age = (now - parsed.astimezone(timezone.utc)).total_seconds()
        except (ValueError, TypeError):
            continue
        if 0 <= age <= LAST_GOOD_SECONDS:
            kept = dict(row)
            kept["stale_preserved"] = True
            rows.append(kept)
    return rows


def collect_quotes(previous: list[dict] | None = None) -> dict:
    discovered = []
    errors = []
    seen = set()
    for query in SEARCHES:
        try:
            rows = _rss(query, limit=max(3, min(8, MAX_RESULTS)))
        except Exception as exc:
            errors.append(f"search:{type(exc).__name__}")
            continue
        for row in rows:
            url = row.get("url") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            if len(seen) > MAX_RESULTS:
                break
            try:
                html = _fetch_public(url)
                quote = parse_public_listing(html, url, row.get("title", ""), row.get("snippet", ""))
                if quote:
                    discovered.append(quote)
            except Exception as exc:
                errors.append(f"page:{type(exc).__name__}")
        if len(seen) >= MAX_RESULTS:
            break
    discovered.sort(key=lambda row: (row.get("card_region", ""), row.get("game", ""), -int(row.get("price") or 0), row.get("title", "")))
    if discovered:
        quotes = discovered[:MAX_RESULTS]
        status = "ok"
        preserved = False
    else:
        quotes = _fresh_previous(previous)
        status = "degraded_preserved" if quotes else "degraded_empty"
        preserved = bool(quotes)
    region_counts = {region: sum(1 for row in quotes if row.get("card_region") == region) for region in ("KR", "JP", "US", "UNKNOWN")}
    sold_count = sum(1 for row in quotes if row.get("is_completed_sale") is True)
    return {
        "status": status,
        "quotes": quotes,
        "preserved_last_good": preserved,
        "quote_count": len(quotes),
        "completed_sale_count": sold_count,
        "asking_count": len(quotes) - sold_count,
        "region_counts": region_counts,
        "errors": errors[:20],
        "source": "https://wyyyes.com/",
        "collected_at": _now_iso(),
        "policy": "public pages only; KR market location is separate from KR/JP/US card edition; asking/offer price is not a completed sale",
    }


if __name__ == "__main__":
    print(json.dumps(collect_quotes(), ensure_ascii=False, indent=2))
