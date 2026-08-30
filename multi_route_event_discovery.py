#!/usr/bin/env python3
"""Independent no-key discovery routes for Pokemon / ONE PIECE / NARUTO.

This module intentionally overlaps *providers*, not trust levels:
- Bing RSS broad discovery
- Bing official-domain scoped discovery
- Bing partner/retail scoped discovery
- direct official-site anchor scanning
- DuckDuckGo HTML fallback when Bing is unavailable or too sparse

All output is candidate/reference data. A search hit never becomes official merely
because it mentions an official brand; official_domain_match is based on the final
result host only. The caller still performs canonical promotion/verification.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import email.utils
import html
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

from safe_runtime import env_int, safe_urlopen, validate_public_https_url

TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
SOURCE_TIMEOUT = max(5, min(12, TIMEOUT))
MAX_PER_QUERY = env_int("TCG_ROUTE_MAX_PER_QUERY", 8, 3, 15)
BING_HOSTS = {"www.bing.com", "bing.com"}
DDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}

GAMES = {
    "포켓몬 카드": {
        "ko": ("포켓몬 카드", "포켓몬카드", "포켓몬"),
        "ja": ("ポケモンカード", "ポケカ", "ポケモン"),
        "en": ("Pokemon TCG", "Pokemon cards", "Pokémon"),
    },
    "원피스 카드": {
        "ko": ("원피스 카드", "원피스카드", "원피스"),
        "ja": ("ワンピースカード", "ワンピカード", "ONE PIECE"),
        "en": ("One Piece Card Game", "ONE PIECE cards"),
    },
    "나루토 카드": {
        "ko": ("나루토 카드", "나루토 카드게임", "나루토"),
        "ja": ("NARUTO CARD GAME", "ナルト カード", "NARUTO"),
        "en": ("NARUTO CARD GAME", "Naruto cards"),
    },
}
REGIONS = {"KR": "ko", "JP": "ja", "US": "en"}

QUERY_FAMILIES = {
    "ko": {
        "release": "출시 발매 신제품 신탄 부스터 스타터 예약 재발매 재판",
        "event": "행사 이벤트 대회 팝업 페스타 체험회 매장대회 월드챔피언십",
        "tournament": "대회 리그 컵 챔피언십 월드챔피언십 매장대회 배틀",
        "popup": "팝업 팝업스토어 페스타 박람회 전시회 체험회 카드샵",
        "promo": "프로모 증정 배포 한정 수령 특전 캠페인 프로모션팩",
        "collab": "콜라보 협업 제휴 브랜드데이 야구 카페 편의점 마트",
        "movie": "영화 극장판 개봉 특별상영 시사회 관람특전 영화특전",
        "reprint": "재발매 재판 재출시 추가생산 재입고 복각",
        "stock": "재입고 입고 판매 자판기 재고 품절 구매처",
    },
    "ja": {
        "release": "発売 新商品 新弾 ブースター スターター 予約 再販",
        "event": "イベント 大会 ポップアップ フェス 体験会 店舗大会",
        "tournament": "大会 リーグ カップ チャンピオンシップ 店舗大会 バトル",
        "popup": "ポップアップ ポップアップストア フェス 展示会 体験会 カードショップ",
        "promo": "プロモ 配布 特典 限定 キャンペーン プレゼント",
        "collab": "コラボ タイアップ カフェ コンビニ ブランド 野球",
        "movie": "映画 劇場版 公開 上映 試写会 入場者特典 映画特典",
        "reprint": "再販 再版 復刻 追加生産 再入荷",
        "stock": "再入荷 入荷 在庫 売り切れ 販売 店舗",
    },
    "en": {
        "release": "release new set booster starter preorder reprint",
        "event": "event tournament pop-up festival demo store championship",
        "tournament": "tournament league cup championship regional worlds store battle",
        "popup": "pop-up popup store festival expo convention exhibition demo card shop",
        "promo": "promo promotional card giveaway distribution exclusive campaign",
        "collab": "collaboration collab cafe retailer partnership brand baseball",
        "movie": "movie film cinema screening premiere theatrical bonus admission promo",
        "reprint": "reprint re-release restock additional print rerun",
        "stock": "restock in stock sold out retailer store vending",
    },
}

COVERAGE_TOPICS = ("event", "tournament", "popup", "promo", "collab", "movie", "release", "reprint")

OFFICIAL_ROUTES = {
    ("포켓몬 카드", "KR"): (
        "https://pokemoncard.co.kr/card/category/info1",
        "https://www.pokemonkorea.co.kr/",
    ),
    ("포켓몬 카드", "JP"): (
        "https://www.pokemon-card.com/info/",
        "https://www.pokemon-card.com/products/",
        "https://players.pokemon-card.com/",
        "https://www.30th.pokemon-card.com/event",
        "https://www.pokemon.co.jp/",
    ),
    ("포켓몬 카드", "US"): (
        "https://www.pokemon.com/us/pokemon-news",
        "https://www.pokemon.com/us/pokemon-tcg/",
    ),
    ("원피스 카드", "KR"): (
        "https://onepiece-cardgame.kr/events.do",
        "https://onepiece-cardgame.kr/topics.do",
        "https://onepiece-cardgame.kr/products.do",
    ),
    ("원피스 카드", "JP"): (
        "https://www.onepiece-cardgame.com/",
        "https://www.onepiece-cardgame.com/events/",
        "https://www.onepiece-cardgame.com/products/",
        "https://one-piece.com/news/",
    ),
    ("원피스 카드", "US"): (
        "https://en.onepiece-cardgame.com/",
        "https://en.onepiece-cardgame.com/events/",
        "https://en.onepiece-cardgame.com/products/",
        "https://en.onepiece-cardgame.com/events/official-shop.html",
    ),
    ("나루토 카드", "KR"): (
        "https://www.naruto-cardgame.com/asia-en/",
        "https://www.naruto-cardgame.com/asia-en/news/article-list.php",
        "https://naruto-official.com/",
    ),
    ("나루토 카드", "JP"): (
        "https://naruto-official.com/",
        "https://www.naruto-cardgame.com/",
    ),
    ("나루토 카드", "US"): (
        "https://www.naruto-cardgame.com/en/",
        "https://www.naruto-cardgame.com/en/news/article-list.php",
        "https://naruto-official.com/en/",
    ),
}

# These are discovery-only domains. They do not get official_domain_match=True.
PARTNER_DOMAINS = {
    ("포켓몬 카드", "KR"): ("musinsa.com", "lotte.co.kr", "emart.ssg.com", "pokemon-go.com"),
    ("포켓몬 카드", "JP"): ("pokemoncenter-online.com", "pokemon.co.jp"),
    ("포켓몬 카드", "US"): ("pokemoncenter.com", "events.pokemon.com"),
    ("원피스 카드", "KR"): ("playgo.bandainamcokorea.co.kr", "ktwizstore.co.kr"),
    ("원피스 카드", "JP"): ("p-bandai.jp", "one-piece.com"),
    ("원피스 카드", "US"): ("bandai.com",),
    ("나루토 카드", "KR"): ("bandainamcokorea.co.kr",),
    ("나루토 카드", "JP"): ("bandai.co.jp",),
    ("나루토 카드", "US"): ("bandai.com",),
}

OFFICIAL_HOSTS = {
    urllib.parse.urlsplit(url).hostname.lower()
    for urls in OFFICIAL_ROUTES.values() for url in urls
    if urllib.parse.urlsplit(url).hostname
}
PARTNER_HOSTS = {host for hosts in PARTNER_DOMAINS.values() for host in hosts}
SOCIAL_DISCOVERY_HOSTS = ("x.com", "instagram.com", "youtube.com")

KEYWORD_RE = re.compile(
    r"행사|이벤트|대회|팝업|페스타|프로모|증정|배포|출시|발매|신탄|부스터|스타터|예약|재발매|재입고|입고|재고|콜라보|협업|영화|극장판|"
    r"イベント|大会|ポップアップ|プロモ|配布|発売|新弾|ブースター|スターター|予約|再販|再入荷|在庫|コラボ|映画|劇場版|"
    r"event|tournament|pop[- ]?up|promo|giveaway|release|booster|starter|preorder|reprint|restock|in stock|collab|movie|film|collector|collection|unboxing|deck|decklist|review|price|"
    r"개봉|언박싱|덱|덱리스트|수집|컬렉터|카드샵|후기|시세|開封|デッキ|コレクター|コレクション|レビュー|相場",
    re.I,
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _short(value: object, limit: int = 320) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()[:limit]


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""


def _category(text: str) -> str:
    topic = _topic(text)
    if topic == "movie": return "movie"
    if topic == "collab": return "collaboration"
    return "promo"


def _topic(text: str) -> str:
    value = text or ""
    patterns = (
        ("movie", r"영화|극장판|개봉|관람특전|movie|film|cinema|screening|映画|劇場版|上映|入場者特典"),
        ("collab", r"콜라보|협업|제휴|브랜드데이|collab|collaboration|partnership|コラボ|タイアップ"),
        ("reprint", r"재발매|재판|복각|reprint|re-release|rerun|再販|再版|復刻"),
        ("release", r"출시|발매|신탄|부스터|스타터|release|launch|new set|booster|starter|発売|新弾"),
        ("popup", r"팝업|팝업스토어|박람회|전시회|pop[- ]?up|expo|convention|exhibition|ポップアップ|展示会"),
        ("tournament", r"대회|리그|챔피언십|월드챔피언십|tournament|league|championship|regional|worlds|大会|リーグ|チャンピオンシップ"),
        ("promo", r"프로모|증정|배포|특전|한정|promo|giveaway|distribution|exclusive|プロモ|配布|特典|限定"),
    )
    for topic, pattern in patterns:
        if re.search(pattern, value, re.I):
            return topic
    return "event"


def _official_for(game: str, region: str, host: str) -> bool:
    normalized = host.lower().removeprefix("www.")
    allowed = {_host(url).removeprefix("www.") for url in OFFICIAL_ROUTES.get((game, region), ())}
    return any(normalized == root or normalized.endswith("." + root) for root in allowed)


def _error_summary(label: str, exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = str(exc.headers.get("Retry-After") or "").strip() if exc.headers else ""
        if exc.code == 429:
            cooldown = f"Retry-After={retry_after}" if retry_after else "Retry-After=미제공"
            return f"{label}: HTTP 429 · {cooldown} · cooldown-required"
        if exc.code == 403:
            return f"{label}: HTTP 403 · access-denied · no-bypass"
        return f"{label}: HTTP {exc.code}"
    return f"{label}: {type(exc).__name__}"


def _parse_pubdate(value: str | None) -> str | None:
    if not value: return None
    try:
        stamp = email.utils.parsedate_to_datetime(value)
        if stamp.tzinfo is None: stamp = stamp.replace(tzinfo=dt.timezone.utc)
        return stamp.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


def _query(game: str, region: str, *, scoped_hosts: tuple[str, ...] = (), topic: str | None = None) -> str:
    lang = REGIONS[region]
    names = GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{x}"' for x in names)
    families = QUERY_FAMILIES[lang]
    selected = {topic: families[topic]} if topic in families else families
    terms = " OR ".join(f"({value.replace(' ', ' OR ')})" for value in selected.values())
    site_expr = ""
    if scoped_hosts:
        site_expr = " (" + " OR ".join(f"site:{host}" for host in scoped_hosts[:8]) + ")"
    return f"({name_expr}) ({terms}){site_expr}"


def _bing_one(game: str, region: str, route: str, hosts: tuple[str, ...] = (), topic: str | None = None) -> tuple[list[dict], str | None]:
    q = _query(game, region, scoped_hosts=hosts, topic=topic)
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"format": "rss", "q": q})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-RouteDiversity/1.0", "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.5"})
    try:
        with safe_urlopen(req, timeout=SOURCE_TIMEOUT, allowed_hosts=BING_HOSTS) as response:
            raw = response.read(1_200_000)
        if b"<!ENTITY" in raw.upper():
            raise ValueError("XML entity expansion blocked")
        root = ET.fromstring(raw)
        rows = []
        for item in root.findall(".//item")[:MAX_PER_QUERY]:
            title = _short(item.findtext("title"), 220)
            link = _short(item.findtext("link"), 700)
            desc = _short(item.findtext("description"), 500)
            if not title or not link.startswith("https://") or not KEYWORD_RE.search(f"{title} {desc}"):
                continue
            try: validate_public_https_url(link)
            except (TypeError, ValueError): continue
            host = _host(link)
            official = _official_for(game, region, host)
            partner = host in set(PARTNER_DOMAINS.get((game, region), ()))
            confidence = 0.91 if official else (0.73 if partner else 0.59)
            rows.append({
                "game": game, "region": region, "category": _category(f"{title} {desc}"),
                "topic": _topic(f"{title} {desc}"), "search_topic": topic or "broad",
                "title": title, "source": link, "source_kind": f"bing_{route}",
                "source_tier": "A-search" if official else "B-search",
                "source_label": "Bing RSS · 공식도메인" if official else ("Bing RSS · 파트너/유통처" if partner else "Bing RSS · 공개웹"),
                "official_domain_match": official, "partner_domain_match": partner,
                "published_at": _parse_pubdate(item.findtext("pubDate")), "dates": [],
                "excerpt": desc or title, "status": "공식출처 검색후보" if official else "교차확인 후보",
                "verified": official, "confidence": confidence,
                "route_family": f"{route}:{topic}" if topic else route,
                "collected_at": _now(),
            })
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, ET.ParseError, UnicodeDecodeError) as exc:
        return [], _error_summary(f"Bing {route} {game}/{region}", exc)


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(); self.current_href = None; self.current_text = []; self.links = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href"); self.current_text = []
    def handle_data(self, data):
        if self.current_href is not None: self.current_text.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href is not None:
            self.links.append((self.current_href, _short(" ".join(self.current_text), 220)))
            self.current_href = None; self.current_text = []


def _official_scan_one(game: str, region: str, url: str) -> tuple[list[dict], str | None]:
    try:
        validate_public_https_url(url, OFFICIAL_HOSTS)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-OfficialLinkScan/1.0"})
        with safe_urlopen(req, timeout=SOURCE_TIMEOUT, allowed_hosts=OFFICIAL_HOSTS) as response:
            final = response.geturl(); raw = response.read(1_000_000).decode("utf-8", "replace")
        parser = _AnchorParser(); parser.feed(raw); rows = []; seen = set()
        for href, text in parser.links:
            if not text or not KEYWORD_RE.search(text): continue
            target = urllib.parse.urljoin(final, href).split("#", 1)[0]
            host = _host(target)
            if not _official_for(game, region, host) or not target.startswith("https://"): continue
            try: validate_public_https_url(target, OFFICIAL_HOSTS)
            except (TypeError, ValueError): continue
            key = (target, text)
            if key in seen: continue
            seen.add(key)
            rows.append({
                "game": game, "region": region, "category": _category(text),
                "topic": _topic(text), "search_topic": _topic(text), "title": text,
                "source": target, "source_kind": "official_anchor_scan", "source_tier": "A-search",
                "source_label": "공식사이트 직접 링크 탐색", "official_domain_match": True,
                "published_at": None, "dates": [], "excerpt": text,
                "status": "공식사이트 링크 후보", "verified": True, "confidence": 0.94,
                "route_family": "official_anchor", "discovered_from": final, "collected_at": _now(),
            })
            if len(rows) >= MAX_PER_QUERY: break
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return [], _error_summary(f"공식링크 {game}/{region}", exc)


def _decode_ddg(url: str) -> str | None:
    value = html.unescape(str(url or ""))
    if value.startswith("//"): value = "https:" + value
    if value.startswith("/"): value = "https://html.duckduckgo.com" + value
    try: parsed = urllib.parse.urlsplit(value)
    except ValueError: return None
    if (parsed.hostname or "").lower() in DDG_HOSTS:
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        if target: value = urllib.parse.unquote(target)
    return value if value.startswith("https://") else None


def _ddg_one(game: str, region: str, topic: str | None = None) -> tuple[list[dict], str | None]:
    q = _query(game, region, topic=topic)
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": q})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-DDGFallback/1.0"})
    try:
        with safe_urlopen(req, timeout=SOURCE_TIMEOUT, allowed_hosts=DDG_HOSTS) as response:
            raw = response.read(900_000).decode("utf-8", "replace")
        rows = []
        for href, raw_title in re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S)[:MAX_PER_QUERY * 2]:
            link = _decode_ddg(href); title = _short(re.sub(r"<[^>]+>", " ", raw_title), 220)
            if not link or not title or not KEYWORD_RE.search(title): continue
            try: validate_public_https_url(link)
            except (TypeError, ValueError): continue
            host = _host(link)
            official = _official_for(game, region, host)
            partner = host in set(PARTNER_DOMAINS.get((game, region), ()))
            rows.append({
                "game": game, "region": region, "category": _category(title),
                "topic": _topic(title), "search_topic": topic or "broad", "title": title,
                "source": link, "source_kind": "ddg_general_fallback", "source_tier": "A-search" if official else "B-search",
                "source_label": "DuckDuckGo · 공식도메인" if official else "DuckDuckGo 공개검색 폴백",
                "official_domain_match": official, "partner_domain_match": partner,
                "published_at": None, "dates": [], "excerpt": title,
                "status": "공식출처 검색후보" if official else "검색 교차확인 후보",
                "verified": official, "confidence": 0.89 if official else 0.56,
                "route_family": f"ddg_fallback:{topic}" if topic else "ddg_fallback", "collected_at": _now(),
            })
            if len(rows) >= MAX_PER_QUERY: break
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return [], _error_summary(f"DDG fallback {game}/{region}", exc)


def collect_all() -> tuple[list[dict], list[str], dict]:
    """Collect candidates through independent routes with bounded concurrency."""
    jobs = []
    for game in GAMES:
        for region in REGIONS:
            official_hosts = tuple(dict.fromkeys(_host(u) for u in OFFICIAL_ROUTES.get((game, region), ()) if _host(u)))
            partner_hosts = tuple(PARTNER_DOMAINS.get((game, region), ()))
            for topic in COVERAGE_TOPICS:
                jobs.append(("bing_topic", _bing_one, (game, region, "topic", (), topic)))
            jobs.append(("bing_social", _bing_one, (game, region, "social", SOCIAL_DISCOVERY_HOSTS)))
            if official_hosts: jobs.append(("bing_official", _bing_one, (game, region, "official", official_hosts)))
            if partner_hosts: jobs.append(("bing_partner", _bing_one, (game, region, "partner", partner_hosts)))
            for url in OFFICIAL_ROUTES.get((game, region), ()):
                jobs.append(("official_anchor", _official_scan_one, (game, region, url)))

    rows = []; errors = []; by_route = {}; successes = 0
    is_android = 'com.termux' in os.environ.get('PREFIX', '') or 'ANDROID_ROOT' in os.environ
    workers = 2 if is_android else 5
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(fn, *args): route for route, fn, args in jobs}
        for future in concurrent.futures.as_completed(future_map):
            route = future_map[future]
            try:
                part, error = future.result()
            except Exception as exc:
                part, error = [], f"{route}: {type(exc).__name__}"
            stat = by_route.setdefault(route, {"queries": 0, "successes": 0, "results": 0, "errors": 0})
            stat["queries"] += 1
            if error:
                stat["errors"] += 1; errors.append(error)
            else:
                stat["successes"] += 1; successes += 1
            stat["results"] += len(part); rows.extend(part)

    # A broad provider can look healthy while still missing a low-volume subject.
    # Retry only empty game/region/topic cells through an independent provider,
    # with a bounded rotating budget to avoid 403/429 pressure.
    first_topic_coverage = {
        f"{game}/{region}/{topic}": sum(
            1 for row in rows
            if row.get("game") == game and row.get("region") == region and row.get("search_topic") == topic
        )
        for game in GAMES for region in REGIONS for topic in COVERAGE_TOPICS
    }
    missing_topics = [key for key, count in first_topic_coverage.items() if count == 0]
    if missing_topics:
        gap_limit = env_int("TCG_ROUTE_GAP_RETRY_LIMIT", 18, 0, len(missing_topics))
        rotation = int(dt.datetime.now(dt.timezone.utc).strftime("%j%H")) % max(1, len(missing_topics))
        rotated = missing_topics[rotation:] + missing_topics[:rotation]
        fallback_jobs = [tuple(key.split("/", 2)) for key in rotated[:gap_limit]]
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            future_map = {pool.submit(_ddg_one, g, r, topic): (g, r, topic) for g, r, topic in fallback_jobs}
            for future in concurrent.futures.as_completed(future_map):
                stat = by_route.setdefault("ddg_fallback", {"queries": 0, "successes": 0, "results": 0, "errors": 0})
                stat["queries"] += 1
                try: part, error = future.result()
                except Exception as exc: part, error = [], f"DDG fallback: {type(exc).__name__}"
                if error: stat["errors"] += 1; errors.append(error)
                else: stat["successes"] += 1; successes += 1
                stat["results"] += len(part); rows.extend(part)

    coverage = {}
    for game in GAMES:
        for region in REGIONS:
            key = f"{game}/{region}"
            coverage[key] = sum(1 for row in rows if row.get("game") == game and row.get("region") == region)
    topic_coverage = {
        f"{game}/{region}/{topic}": sum(
            1 for row in rows
            if row.get("game") == game and row.get("region") == region and row.get("search_topic") == topic
        )
        for game in GAMES for region in REGIONS for topic in COVERAGE_TOPICS
    }

    status = {
        "configured": True,
        "status": "Bing RSS 작품×국가×주제 독립검색 + 공식/파트너/팬SNS + 공식사이트 직접스캔 + 누락주제 DDG 순환폴백",
        "route_count": len(by_route),
        "query_count": sum(v.get("queries", 0) for v in by_route.values()),
        "success_query_count": successes,
        "result_count": len(rows),
        "error_count": len(errors),
        "by_route": by_route,
        "coverage": coverage,
        "topic_coverage": topic_coverage,
        "expected_topic_cells": len(GAMES) * len(REGIONS) * len(COVERAGE_TOPICS),
        "covered_topic_cells": sum(1 for value in topic_coverage.values() if value > 0),
        "missing_topic_cells": [key for key, value in topic_coverage.items() if value == 0],
    }
    return rows, errors[:60], status


if __name__ == "__main__":
    import json
    rows, errors, status = collect_all()
    print(json.dumps({"items": len(rows), "errors": len(errors), "status": status}, ensure_ascii=False))
