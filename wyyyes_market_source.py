#!/usr/bin/env python3
"""Bounded public WYYYES market collector.

Only public product pages are used. Login/private APIs are never bypassed.
WYYYES prices are stored as platform quotes and never overwrite the canonical
verified market price. Listing/offer prices stay distinct from explicit sold
or auction-complete evidence.
"""
from __future__ import annotations

from datetime import date
import math
import os
from pathlib import Path
import stat
import unicodedata
from urllib.parse import urlsplit

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
_GRADING_LABELS = {"PSA", "BGS", "CGC", "TAG", "BRG"}


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


def _valid_price(value: int) -> int:
    return value if 100 <= int(value) <= 100_000_000 else 0


def _extract_structured_price_krw(html: str) -> int:
    """Prefer product-price metadata over arbitrary KRW values elsewhere on page."""
    source = html or ""
    patterns = (
        r'<meta[^>]+(?:property|itemprop|name)=["\'](?:product:price:amount|price)["\'][^>]+content=["\']([0-9,]+(?:\.\d+)?)',
        r'<meta[^>]+content=["\']([0-9,]+(?:\.\d+)?)["\'][^>]+(?:property|itemprop|name)=["\'](?:product:price:amount|price)["\']',
        r'["\']price["\']\s*:\s*["\']?([0-9,]+(?:\.\d+)?)',
    )
    for pattern in patterns:
        match = re.search(pattern, source, re.I)
        if not match:
            continue
        try:
            return _valid_price(int(float(match.group(1).replace(",", ""))))
        except (TypeError, ValueError, OverflowError):
            continue
    return 0


def _extract_price_krw(text: str) -> int:
    candidates = []
    for raw in re.findall(r"(?<!\d)(\d{1,3}(?:,\d{3})+|\d{4,9})\s*원", text or ""):
        try:
            value = _valid_price(int(raw.replace(",", "")))
        except ValueError:
            continue
        if value:
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
    match = re.search(r"\b(PSA|BGS|CGC|TAG|BRG)\s*[-:]?\s*(10|[1-9])\b", value, re.I)
    if not match:
        return "", None
    return match.group(1).upper(), int(match.group(2))


def infer_price_type(text: str) -> str:
    """Classify only explicit transaction evidence; ambiguous stock text stays asking."""
    low = (text or "").lower()
    # Auction completion is a distinct evidence class and must win over generic
    # sale words when both appear in the same local listing evidence.
    if any(token in low for token in ("낙찰완료", "낙찰 완료", "낙찰", "경매 종료", "경매종료")):
        return "auction_result"
    if any(token in low for token in ("판매완료", "거래완료", "거래 완료", "판매 완료")):
        return "sold"
    # "sold out" is inventory state, not proof of a completed transaction price.
    if re.search(r"(?<![a-z])sold(?!\s*out\b)", low):
        return "sold"
    return "asking"


def _card_number(text: str) -> str:
    value = text or ""
    # Slash-number forms are the strongest signal and must win over grading labels
    # such as PSA 10 / BRG10.
    slash = re.search(r"\b\d{2,3}/\d{2,3}\b", value, re.I)
    if slash:
        return slash.group(0).upper()
    # Set/card codes require both an alpha prefix and a numeric set/card portion.
    for match in re.finditer(r"\b([A-Z]{1,5}\d{1,2}[A-Z]?)[- ]?(\d{2,3})\b", value, re.I):
        prefix = match.group(1).upper()
        if prefix in _GRADING_LABELS or any(prefix.startswith(label) for label in _GRADING_LABELS):
            continue
        return re.sub(r"\s+", "", match.group(0).upper())[:40]
    for match in re.finditer(r"\b([A-Z]{1,5})-(\d{2,3})\b", value, re.I):
        prefix = match.group(1).upper()
        if prefix in _GRADING_LABELS:
            continue
        return match.group(0).upper()[:40]
    return ""


def _identity_value(primary: str, fallback: str, infer):
    value = infer(primary)
    if value and value not in {"UNKNOWN", ("", None)}:
        return value
    return infer(fallback)


def parse_public_listing(html: str, url: str, fallback_title: str = "", snippet: str = "") -> dict | None:
    title = _extract_title(html, fallback_title)
    page_text = html_to_text(html)
    identity_text = " ".join(part for part in (title, snippet) if part)

    price = _extract_structured_price_krw(html) or _extract_price_krw(" ".join((identity_text, page_text[:30_000])))
    game = infer_game(identity_text) or infer_game(page_text[:8_000])
    if not title or not price or not game:
        return None

    card_region = infer_card_region(identity_text)
    if card_region == "UNKNOWN":
        card_region = infer_card_region(page_text[:8_000])

    company, grade = infer_grade(identity_text)
    if not company:
        company, grade = infer_grade(page_text[:4_000])

    card_number = _card_number(identity_text) or _card_number(page_text[:8_000])
    # Transaction state must be product-local.  A generic footer, recommendation
    # carousel, or unrelated sold badge elsewhere on the page cannot promote a
    # current listing to completed-sale evidence.
    quote_type = infer_price_type(identity_text)
    return {
        "platform": "WYYYES",
        "market_region": "KR",
        "card_region": card_region,
        "game": game,
        "title": title,
        "card_number": card_number,
        "grading_company": company,
        "grade": grade,
        "currency": "KRW",
        "price": price,
        "price_type": quote_type,
        "is_completed_sale": quote_type in {"sold", "auction_result"},
        "source_url": url,
        "collected_at": _now_iso(),
        "evidence_policy": "public-page-only; completed-sale state requires title/snippet-local explicit transaction evidence",
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
        "policy": "public pages only; KR market location is separate from KR/JP/US card edition; completed-sale evidence must be product-local and explicit",
    }


# Reviewed V1007 identity gate; default reference-only catalog cannot approve pricing.
CATALOG_SCHEMA = "tcg-reviewed-market-identity/v1007"
MAX_CATALOG_BYTES = 120_000
MAX_ENTRIES = 500
MAX_QUOTE_AGE_SECONDS = 72 * 3600
OFFICIAL_HOSTS = {
    "pokemon": frozenset(("www.pokemon-card.com", "pokemon-card.com", "www.pokemon.com", "pokemon.com")),
    "onepiece": frozenset(("en.onepiece-cardgame.com", "onepiece-cardgame.com")),
    # No independently confirmed Naruto card-level catalogue host yet.
    "naruto": frozenset(),
}
MARKET_HOSTS = frozenset(("wyyyes.com", "www.wyyyes.com"))


def _game(value: object) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "")).casefold()
    game = re.sub(r"[^a-z0-9]", "", raw)
    return game if game in OFFICIAL_HOSTS else ""


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or "")).strip()).upper()


def _exact_token(title: str, value: str) -> bool:
    token = _text(value)
    if not token or len(token) > 120:
        return False
    return re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", _text(title)) is not None


def _official_url(url: object, game: str) -> bool:
    try:
        split = urlsplit(str(url or ""))
        return (split.scheme == "https" and not split.username and not split.password
                and split.port in (None, 443) and split.hostname in OFFICIAL_HOSTS.get(game, ()))
    except ValueError:
        return False


def _market_url(url: object) -> bool:
    try:
        split = urlsplit(str(url or ""))
        return (split.scheme == "https" and not split.username and not split.password
                and split.port in (None, 443) and split.hostname in MARKET_HOSTS
                and split.path.startswith("/category/"))
    except ValueError:
        return False


def _fresh_at(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 48:
        return False
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return False
        delta = (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds()
        return 0 <= delta <= MAX_QUOTE_AGE_SECONDS
    except (ValueError, TypeError, OverflowError):
        return False


def _approved_rows(catalog: object) -> list[dict]:
    if (not isinstance(catalog, dict) or catalog.get("schema") != CATALOG_SCHEMA
            or catalog.get("reviewed_for_auto_price_link") is not True):
        return []
    records = catalog.get("entries")
    if not isinstance(records, list) or len(records) > MAX_ENTRIES:
        return []
    accepted = []
    for record in records:
        if not isinstance(record, dict) or record.get("identity_verified") is not True:
            continue
        if record.get("source_grade") != "official_card_catalog":
            continue
        game = _game(record.get("game"))
        region = str(record.get("region") or "").upper()
        fields = ("card_name", "card_number", "set_code", "printing")
        if not game or region not in {"KR", "JP", "US"}:
            continue
        if any(not isinstance(record.get(key), str) or not record[key].strip()
               or len(record[key]) > 120 for key in fields):
            continue
        if not _official_url(record.get("source_url"), game):
            continue
        try:
            reviewed = date.fromisoformat(record["reviewed_on"])
        except (KeyError, TypeError, ValueError):
            continue
        if reviewed > datetime.now(timezone.utc).date():
            continue
        accepted.append(record)
    return accepted


def load_reviewed_catalog(path: Path) -> dict | None:
    """Bounded read only; fail closed for symlink, oversized or malformed input."""
    try:
        if path.is_symlink():
            return None
        mode = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(str(path), mode)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CATALOG_BYTES:
                return None
            with os.fdopen(fd, "rb", closefd=False) as handle:
                data = handle.read(MAX_CATALOG_BYTES + 1)
        finally:
            os.close(fd)
        if len(data) > MAX_CATALOG_BYTES:
            return None
        parsed = json.loads(data.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except (OSError, UnicodeError, ValueError, TypeError):
        return None


def _name_matches(title: str, name: str) -> bool:
    """A base name must not absorb a different explicitly printed card variant."""
    if not _exact_token(title, name):
        return False
    for suffix in ("V", "VMAX", "VSTAR", "EX", "GX", "V-UNION", "BREAK"):
        if _exact_token(title, suffix) and not _exact_token(name, suffix):
            return False
    return True


def _printing_matches(title: str, printing: str) -> bool:
    name = _text(printing)
    if name in ("HOLO", "HOLOFOIL") and any(
        _exact_token(title, other) for other in ("REVERSE HOLO", "REVERSE HOLOFOIL")
    ):
        return False
    return _exact_token(title, name.replace("_", " "))


def _eligible_quote(quote: dict) -> bool:
    try:
        price = float(quote.get("price"))
    except (TypeError, ValueError, OverflowError):
        return False
    return (
        quote.get("platform") == "WYYYES"
        and _market_url(quote.get("source_url"))
        and _fresh_at(quote.get("collected_at"))
        and math.isfinite(price) and 100 <= price <= 100_000_000
        and quote.get("currency") == "KRW"
        and _game(quote.get("game")) != ""
        and quote.get("card_region") in ("KR", "JP", "US")
        and isinstance(quote.get("title"), str) and bool(quote["title"].strip())
        and isinstance(quote.get("card_number"), str) and bool(quote["card_number"].strip())
        and _exact_token(quote["title"], quote["card_number"])
    )


def bind_quote(quote: dict, catalog: object) -> dict:
    """Only one distinct *reviewed* printing can produce an automatic card name."""
    if not isinstance(quote, dict):
        return {"identity_binding_status": "HOLD_INVALID_QUOTE"}
    sanitized = dict(quote)
    for field in (
        "card_name", "identity_verified", "identity_binding_status",
        "identity_source_url", "identity_set_code", "identity_printing",
    ):
        sanitized.pop(field, None)
    sanitized["identity_binding_status"] = "HOLD_UNVERIFIED"
    if not _eligible_quote(sanitized):
        return sanitized
    title = sanitized["title"]
    matches = []
    for candidate in _approved_rows(catalog):
        if (_game(candidate.get("game")) != _game(sanitized.get("game"))
                or candidate.get("region") != sanitized.get("card_region")
                or _text(candidate.get("card_number")) != _text(sanitized.get("card_number"))):
            continue
        if not all((
            _name_matches(title, candidate["card_name"]),
            _exact_token(title, candidate["card_number"]),
            _exact_token(title, candidate["set_code"]),
            _printing_matches(title, candidate["printing"]),
        )):
            continue
        matches.append(candidate)
    if len(matches) != 1:
        return sanitized
    matched = matches[0]
    sanitized.update({
        "card_name": matched["card_name"],
        "identity_verified": True,
        "identity_binding_status": "VERIFIED_EXACT",
        "identity_source_url": matched["source_url"],
        "identity_set_code": matched["set_code"],
        "identity_printing": matched["printing"],
    })
    return sanitized


def bind_quotes(quotes: object, catalog: object) -> list[dict]:
    if not isinstance(quotes, list):
        return []
    return [bind_quote(q, catalog) for q in quotes[:36] if isinstance(q, dict)]


if __name__ == "__main__":
    print(json.dumps(collect_quotes(), ensure_ascii=False, indent=2))
