#!/usr/bin/env python3
"""Safe multi-source discovery for TCG events, collaborations, promos and movies.

v107 source policy
- Official web pages remain the canonical confirmed source.
- X: uses the official X API recent-search endpoint when X_BEARER_TOKEN is configured.
- Instagram: uses Meta Instagram Business Discovery when credentials are configured.
- Google: Google News RSS is the default broad discovery source. Legacy Custom Search JSON
  is optional for existing customers only and is never required.
- Social/news results are candidates until either an account is linked from an official site,
  the result points to an approved official domain, or a separate official source confirms it.
- Credentials are read only from environment variables and are never written to JSON/logs.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import email.utils
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from safe_runtime import (
    atomic_write_json,
    env_int,
    safe_read_text,
    safe_urlopen,
    safe_urlopen_no_redirect,
    validate_public_https_url,
)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "social_event_candidates.json"
REGISTRY = ROOT / "social_source_registry.json"
TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
MAX_ITEMS = env_int("TCG_SOCIAL_MAX_ITEMS", 80, 10, 250)
MAX_PER_QUERY = env_int("TCG_SOCIAL_MAX_PER_QUERY", 10, 5, 25)
REGISTRY_TTL_HOURS = env_int("TCG_SOCIAL_REGISTRY_TTL_HOURS", 168, 6, 720)

GAMES = {
    "포켓몬 카드": {
        "ko": ("포켓몬", "포켓몬카드", "포켓몬 카드"),
        "ja": ("ポケモン", "ポケカ", "ポケモンカード"),
        "en": ("Pokemon", "Pokémon", "Pokemon TCG"),
    },
    "원피스 카드": {
        "ko": ("원피스", "원피스카드", "원피스 카드"),
        "ja": ("ONE PIECE", "ワンピース", "ワンピカード"),
        "en": ("ONE PIECE", "One Piece Card Game"),
    },
    "나루토 카드": {
        "ko": ("나루토", "나루토카드", "나루토 카드"),
        "ja": ("NARUTO", "ナルト", "NARUTO CARD GAME"),
        "en": ("NARUTO", "NARUTO CARD GAME"),
    },
}
REGION_LANG = {
    "KR": {"lang": "ko", "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
    "JP": {"lang": "ja", "hl": "ja", "gl": "JP", "ceid": "JP:ja"},
    "US": {"lang": "en", "hl": "en-US", "gl": "US", "ceid": "US:en"},
}

EVENT_TERMS = {
    "ko": "행사 이벤트 콜라보 프로모 팝업 영화 극장판 개봉 예약 발매 대회",
    "ja": "イベント コラボ キャンペーン プロモ ポップアップ 映画 劇場版 発売 大会",
    "en": "event collaboration collab promo pop-up movie film release tournament preorder",
}
CATEGORY_PATTERNS = (
    ("movie", re.compile(r"영화|극장판|개봉|movie|film|cinema|劇場版|映画|上映|netflix|streaming", re.I)),
    ("collaboration", re.compile(r"콜라보|협업|collab|collaboration|コラボ|タイアップ|popup|pop-up|ポップアップ", re.I)),
    ("promo", re.compile(r"프로모|증정|이벤트|행사|대회|배틀|예약|발매|promo|event|campaign|tournament|battle|release|preorder|キャンペーン|イベント|大会|発売|予約", re.I)),
)
DATE_RE = re.compile(
    r"(?<!\d)(20\d{2})\s*(?:[년./-]|年)\s*(\d{1,2})\s*(?:[월./-]|月)\s*(\d{1,2})\s*(?:일|日)?",
    re.I,
)

OFFICIAL_HOSTS = {
    "www.pokemon-card.com", "www.30th.pokemon-card.com", "pokemon.co.jp", "www.pokemon.co.jp",
    "pokemoncard.co.kr", "www.pokemoncard.co.kr", "pokemonkorea.co.kr", "www.pokemonkorea.co.kr",
    "www.pokemon.com", "pokemon.com",
    "onepiece-cardgame.kr", "www.onepiece-cardgame.kr", "www.onepiece-cardgame.com",
    "en.onepiece-cardgame.com", "cp.onepiece-cardgame.com", "one-piece.com", "www.one-piece.com",
    "naruto-cardgame.com", "www.naruto-cardgame.com", "naruto-official.com", "www.naruto-official.com",
    "daewonmedia.com", "www.daewonmedia.com", "kobis.or.kr", "www.kobis.or.kr",
}

# Only links discovered from these official pages can auto-enter the trusted social registry.
OFFICIAL_DISCOVERY_PAGES = (
    ("포켓몬 카드", "KR", "https://www.pokemonkorea.co.kr/"),
    ("포켓몬 카드", "JP", "https://www.pokemon.co.jp/"),
    ("포켓몬 카드", "US", "https://www.pokemon.com/us"),
    ("원피스 카드", "KR", "https://onepiece-cardgame.kr/"),
    ("원피스 카드", "JP", "https://one-piece.com/"),
    ("원피스 카드", "US", "https://en.onepiece-cardgame.com/"),
    ("나루토 카드", "JP", "https://naruto-official.com/"),
    ("나루토 카드", "US", "https://www.naruto-cardgame.com/en/"),
    ("나루토 카드", "KR", "https://www.naruto-cardgame.com/asia-en/"),
)

SOCIAL_HOSTS = {
    "x.com", "www.x.com", "twitter.com", "www.twitter.com",
    "instagram.com", "www.instagram.com",
    "youtube.com", "www.youtube.com", "youtu.be",
}
GOOGLE_NEWS_HOSTS = {"news.google.com"}
GOOGLE_API_HOSTS = {"www.googleapis.com"}
X_API_HOSTS = {"api.x.com"}
META_API_HOSTS = {"graph.facebook.com"}

SECRET_ENV_NAMES = (
    "X_BEARER_TOKEN",
    "INSTAGRAM_ACCESS_TOKEN",
    "INSTAGRAM_IG_USER_ID",
    "GOOGLE_CSE_API_KEY",
    "GOOGLE_CSE_ID",
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _short(text: object, limit: int = 320) -> str:
    value = re.sub(r"\s+", " ", html.unescape(str(text or ""))).strip()
    return value[:limit]


def _secret_safe(text: object) -> str:
    value = str(text or "")
    for name in SECRET_ENV_NAMES:
        secret = os.environ.get(name)
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)(access_token|bearer|api[_-]?key)=([^&\s]+)", r"\1=[REDACTED]", value)
    return value[:1200]


def _category(text: str) -> str:
    for category, pattern in CATEGORY_PATTERNS:
        if pattern.search(text or ""):
            return category
    return "promo"


def _dates(text: str) -> list[str]:
    found: list[str] = []
    for year, month, day in DATE_RE.findall(text or ""):
        try:
            value = dt.date(int(year), int(month), int(day)).isoformat()
        except ValueError:
            continue
        if value not in found:
            found.append(value)
    return found[:6]


def _host(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def _normalize_title(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z가-힣ぁ-んァ-ヶ一-龠]+", " ", (value or "").lower())
    return re.sub(r"\s+", " ", text).strip()[:180]


def _candidate_key(row: dict) -> tuple[str, str, str, str]:
    return (
        str(row.get("game") or ""), str(row.get("region") or ""),
        str(row.get("category") or ""), _normalize_title(str(row.get("title") or "")),
    )


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(html.unescape(href))


def _registry_default() -> dict:
    return {
        "version": 1,
        "updated_at": None,
        "policy": "공식 웹사이트에서 직접 연결된 SNS 계정만 trusted=true로 자동 등록",
        "accounts": [],
        "discovery_pages": [
            {"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES
        ],
    }


def load_registry() -> dict:
    if not REGISTRY.exists():
        return _registry_default()
    try:
        data = json.loads(safe_read_text(REGISTRY))
        if not isinstance(data, dict) or not isinstance(data.get("accounts"), list):
            return _registry_default()
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        return _registry_default()


def _registry_fresh(data: dict) -> bool:
    raw = data.get("updated_at")
    if not raw:
        return False
    try:
        stamp = dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=dt.timezone.utc)
        age = dt.datetime.now(dt.timezone.utc) - stamp.astimezone(dt.timezone.utc)
        return age.total_seconds() < REGISTRY_TTL_HOURS * 3600
    except ValueError:
        return False


def _parse_social_link(link: str) -> tuple[str, str] | None:
    try:
        parsed = urllib.parse.urlsplit(link)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    path = parsed.path.strip("/")
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        user = path.split("/", 1)[0]
        if user and user.lower() not in {"home", "search", "share", "intent", "i"} and re.fullmatch(r"[A-Za-z0-9_]{1,15}", user):
            return "x", user
    if host in {"instagram.com", "www.instagram.com"}:
        user = path.split("/", 1)[0]
        if user and user.lower() not in {"p", "reel", "explore", "stories"} and re.fullmatch(r"[A-Za-z0-9_.]{1,30}", user):
            return "instagram", user
    if host in {"youtube.com", "www.youtube.com"}:
        if path.startswith("channel/UC"):
            return "youtube_channel", path.split("/", 1)[1]
        if path.startswith("@") and len(path) > 1:
            return "youtube_handle", path.split("/", 1)[0]
    return None


def _fetch_official_page(game: str, region: str, url: str) -> tuple[list[dict], str | None]:
    try:
        validate_public_https_url(url, OFFICIAL_HOSTS)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-SocialRegistry/1.0"})
        with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=OFFICIAL_HOSTS) as response:
            final = response.geturl()
            validate_public_https_url(final, OFFICIAL_HOSTS)
            raw = response.read(1_000_000).decode("utf-8", "replace")
        parser = LinkParser(); parser.feed(raw)
        rows = []
        for href in parser.links:
            absolute = urllib.parse.urljoin(final, href)
            social = _parse_social_link(absolute)
            if not social:
                continue
            platform, username = social
            rows.append({
                "platform": platform, "username": username, "game": game, "region": region,
                "profile_url": absolute.split("?", 1)[0], "trusted": True,
                "verified_via_official_site": final, "verified_at": _now(),
            })
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, UnicodeDecodeError) as exc:
        return [], f"{game}/{region}: {type(exc).__name__}"


def refresh_registry(force: bool = False) -> tuple[dict, list[str]]:
    current = load_registry()
    if not force and _registry_fresh(current):
        return current, []
    errors: list[str] = []
    discovered: list[dict] = []
    workers = 2 if ('com.termux' in os.environ.get('PREFIX','') or 'ANDROID_ROOT' in os.environ) else 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tcg-social-registry") as pool:
        futures = [pool.submit(_fetch_official_page, *row) for row in OFFICIAL_DISCOVERY_PAGES]
        for future in concurrent.futures.as_completed(futures):
            rows, error = future.result()
            discovered.extend(rows)
            if error:
                errors.append(error)
    # Preserve manually configured accounts and merge discoveries by platform+username+game+region.
    manual = [x for x in current.get("accounts", []) if isinstance(x, dict) and x.get("manual") is True]
    merged: dict[tuple[str, str, str, str], dict] = {}
    for row in manual + discovered:
        key = (str(row.get("platform")), str(row.get("username")).lower(), str(row.get("game")), str(row.get("region")))
        if all(key):
            merged[key] = row
    payload = {
        "version": 1, "updated_at": _now(),
        "policy": "공식 웹사이트에서 직접 연결된 SNS 계정만 trusted=true로 자동 등록. manual=true 계정은 사용자가 직접 관리.",
        "accounts": sorted(merged.values(), key=lambda x: (x.get("game", ""), x.get("region", ""), x.get("platform", ""), x.get("username", ""))),
        "discovery_pages": [{"game": g, "region": r, "url": u} for g, r, u in OFFICIAL_DISCOVERY_PAGES],
        "discovery_errors": errors[:30],
    }
    atomic_write_json(REGISTRY, payload, suffix=".registry.tmp")
    return payload, errors


def _trusted_accounts(registry: dict, platform: str, game: str | None = None, region: str | None = None) -> list[dict]:
    rows = []
    for row in registry.get("accounts", []):
        if not isinstance(row, dict) or row.get("platform") != platform or row.get("trusted") is not True:
            continue
        if game and row.get("game") != game:
            continue
        if region and row.get("region") != region:
            continue
        rows.append(row)
    return rows


def _game_query_terms(game: str, region: str) -> str:
    lang = REGION_LANG[region]["lang"]
    names = GAMES[game][lang]
    # X query size stays safely under 512 chars.
    name_expr = " OR ".join(f'"{name}"' if " " in name else name for name in names[:3])
    event_words = {
        "ko": "(행사 OR 이벤트 OR 콜라보 OR 프로모 OR 영화 OR 극장판 OR 발매 OR 대회)",
        "ja": "(イベント OR コラボ OR キャンペーン OR プロモ OR 映画 OR 劇場版 OR 発売 OR 大会)",
        "en": "(event OR collab OR collaboration OR promo OR movie OR film OR release OR tournament)",
    }[lang]
    return f"({name_expr}) {event_words} lang:{lang} -is:retweet"


def _x_request(query: str) -> dict:
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        return {"ok": True, "configured": False, "items": [], "note": "X_BEARER_TOKEN 미설정"}
    params = urllib.parse.urlencode({
        "query": query,
        "max_results": max(10, min(100, MAX_PER_QUERY)),
        "tweet.fields": "created_at,lang,author_id,entities,public_metrics",
        "expansions": "author_id",
        "user.fields": "username,name,verified,verified_type",
    })
    url = f"https://api.x.com/2/tweets/search/recent?{params}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "TCG-Grader-v107/1.0"})
    try:
        with safe_urlopen_no_redirect(req, timeout=TIMEOUT, allowed_hosts=X_API_HOSTS) as response:
            data = json.loads(response.read(1_500_000).decode("utf-8", "replace"))
        return {"ok": True, "configured": True, "payload": data}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "configured": True, "items": [], "error": _secret_safe(f"{type(exc).__name__}: {exc}")}


def collect_x(registry: dict) -> tuple[list[dict], list[str], dict]:
    if not os.environ.get("X_BEARER_TOKEN", "").strip():
        return [], [], {"configured": False, "status": "X_BEARER_TOKEN 미설정 · X API 건너뜀"}
    rows: list[dict] = []
    errors: list[str] = []
    query_count = 0
    for game in GAMES:
        for region in REGION_LANG:
            trusted = _trusted_accounts(registry, "x", game, region)
            base = _game_query_terms(game, region)
            if trusted:
                from_expr = " OR ".join(f"from:{x['username']}" for x in trusted[:6])
                query = f"({from_expr}) {base}"
            else:
                query = base
            result = _x_request(query)
            query_count += 1
            if not result.get("ok"):
                errors.append(f"X {game}/{region}: {result.get('error','수집 실패')}")
                continue
            payload = result.get("payload") or {}
            users = {str(u.get("id")): u for u in (payload.get("includes", {}).get("users") or []) if isinstance(u, dict)}
            trusted_names = {str(x.get("username", "")).lower(): x for x in trusted}
            for post in payload.get("data") or []:
                if not isinstance(post, dict):
                    continue
                user = users.get(str(post.get("author_id")), {})
                username = str(user.get("username") or "")
                text = _short(post.get("text"), 500)
                title = _short(text, 180)
                post_id = str(post.get("id") or "")
                if not post_id or not title:
                    continue
                official = username.lower() in trusted_names
                verified = bool(user.get("verified"))
                confidence = 0.96 if official else (0.72 if verified else 0.52)
                rows.append({
                    "game": game, "region": region, "category": _category(text),
                    "title": title, "source": f"https://x.com/{urllib.parse.quote(username, safe='')}/status/{urllib.parse.quote(post_id, safe='')}",
                    "source_kind": "x", "source_tier": "A-social" if official else "B-social",
                    "source_label": "X 공식계정" if official else "X 공개게시물 후보",
                    "author": username, "official_account_verified": official,
                    "author_platform_verified": verified,
                    "verification_origin": trusted_names.get(username.lower(), {}).get("verified_via_official_site") if official else None,
                    "published_at": post.get("created_at"), "dates": _dates(text), "excerpt": _short(text, 260),
                    "status": "공식 SNS 후보" if official else "SNS 보조후보",
                    "verified": official, "confidence": confidence, "collected_at": _now(),
                })
    return rows, errors, {"configured": True, "query_count": query_count, "error_count": len(errors), "result_count": len(rows), "success_query_count": max(0, query_count-len(errors)), "status": "X API 최근 7일 검색"}


def _instagram_request(viewer_id: str, username: str, token: str) -> dict:
    version = os.environ.get("META_GRAPH_VERSION", "v26.0").strip() or "v26.0"
    if not re.fullmatch(r"v\d{1,2}\.\d", version):
        version = "v26.0"
    fields = f"business_discovery.username({username}){{username,name,media.limit({max(5,min(25,MAX_PER_QUERY))}){{caption,permalink,timestamp,media_type}}}}"
    params = urllib.parse.urlencode({"fields": fields, "access_token": token})
    url = f"https://graph.facebook.com/{version}/{urllib.parse.quote(viewer_id, safe='')}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "TCG-Grader-v107/1.0"})
    try:
        with safe_urlopen_no_redirect(req, timeout=TIMEOUT, allowed_hosts=META_API_HOSTS) as response:
            data = json.loads(response.read(1_500_000).decode("utf-8", "replace"))
        return {"ok": True, "payload": data}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": _secret_safe(f"{type(exc).__name__}: {exc}")}


def collect_instagram(registry: dict) -> tuple[list[dict], list[str], dict]:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    viewer_id = os.environ.get("INSTAGRAM_IG_USER_ID", "").strip()
    if not token or not viewer_id:
        return [], [], {"configured": False, "status": "Instagram API 자격정보 미설정 · 공식계정 후보만 보관"}
    accounts = _trusted_accounts(registry, "instagram")[:12]
    if not accounts:
        return [], [], {"configured": True, "status": "공식사이트에서 연결된 Instagram 계정 미발견", "account_count": 0}
    rows: list[dict] = []
    errors: list[str] = []
    for account in accounts:
        result = _instagram_request(viewer_id, str(account["username"]), token)
        if not result.get("ok"):
            errors.append(f"Instagram {account.get('username')}: {result.get('error','수집 실패')}")
            continue
        discovery = (result.get("payload") or {}).get("business_discovery") or {}
        media = (discovery.get("media") or {}).get("data") or []
        for item in media:
            if not isinstance(item, dict):
                continue
            caption = _short(item.get("caption"), 600)
            if not caption or not any(pattern.search(caption) for _, pattern in CATEGORY_PATTERNS):
                continue
            source = str(item.get("permalink") or account.get("profile_url") or "")
            if _host(source) not in {"instagram.com", "www.instagram.com"}:
                continue
            rows.append({
                "game": account.get("game"), "region": account.get("region"), "category": _category(caption),
                "title": _short(caption, 180), "source": source,
                "source_kind": "instagram", "source_tier": "A-social", "source_label": "Instagram 공식계정",
                "author": account.get("username"), "official_account_verified": True,
                "verification_origin": account.get("verified_via_official_site"),
                "published_at": item.get("timestamp"), "dates": _dates(caption), "excerpt": _short(caption, 260),
                "status": "공식 SNS 후보", "verified": True, "confidence": 0.96, "collected_at": _now(),
            })
    return rows, errors, {"configured": True, "account_count": len(accounts), "error_count": len(errors), "result_count": len(rows), "success_query_count": max(0, len(accounts)-len(errors)), "status": "Meta Instagram Business Discovery"}


def _google_news_url(game: str, region: str) -> str:
    cfg = REGION_LANG[region]
    lang = cfg["lang"]
    names = " OR ".join(f'"{x}"' for x in GAMES[game][lang][:2])
    query = f"({names}) ({EVENT_TERMS[lang]}) when:30d"
    params = urllib.parse.urlencode({"q": query, "hl": cfg["hl"], "gl": cfg["gl"], "ceid": cfg["ceid"]})
    return f"https://news.google.com/rss/search?{params}"


def _parse_pubdate(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


def _google_news_one(game: str, region: str) -> tuple[list[dict], str | None]:
    url = _google_news_url(game, region)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-GoogleNews/1.0"})
    try:
        with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=GOOGLE_NEWS_HOSTS) as response:
            raw = response.read(1_500_000)
        root = ET.fromstring(raw)
        rows = []
        for item in root.findall("./channel/item")[:MAX_PER_QUERY]:
            title = _short(item.findtext("title"), 220)
            link = _short(item.findtext("link"), 600)
            description = _short(item.findtext("description"), 500)
            source_node = item.find("source")
            publisher_url = source_node.attrib.get("url", "") if source_node is not None else ""
            publisher = _short(source_node.text if source_node is not None else "", 120)
            combined = f"{title} {description}"
            if not title or not link:
                continue
            official = _host(publisher_url) in OFFICIAL_HOSTS
            rows.append({
                "game": game, "region": region, "category": _category(combined),
                "title": title, "source": link, "publisher_url": publisher_url or None,
                "source_kind": "google_news", "source_tier": "A-search" if official else "B-news",
                "source_label": "Google News · 공식도메인" if official else "Google News 보조탐색",
                "publisher": publisher, "official_domain_match": official,
                "published_at": _parse_pubdate(item.findtext("pubDate")), "dates": _dates(combined),
                "excerpt": description or title, "status": "공식출처 검색후보" if official else "뉴스 교차확인 후보",
                "verified": official, "confidence": 0.90 if official else 0.64, "collected_at": _now(),
            })
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, ET.ParseError) as exc:
        return [], f"Google News {game}/{region}: {type(exc).__name__}"


def collect_google_news() -> tuple[list[dict], list[str], dict]:
    rows: list[dict] = []
    errors: list[str] = []
    workers = 2 if ('com.termux' in os.environ.get('PREFIX','') or 'ANDROID_ROOT' in os.environ) else 4
    jobs = [(game, region) for game in GAMES for region in REGION_LANG]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tcg-google-news") as pool:
        future_map = {pool.submit(_google_news_one, *job): job for job in jobs}
        for future in concurrent.futures.as_completed(future_map):
            part, error = future.result()
            rows.extend(part)
            if error:
                errors.append(error)
    return rows, errors, {"configured": True, "query_count": len(jobs), "error_count": len(errors), "result_count": len(rows), "success_query_count": max(0, len(jobs)-len(errors)), "status": "Google News 최근 30일 검색"}


def _google_cse_one(game: str, region: str, key: str, cx: str) -> tuple[list[dict], str | None]:
    cfg = REGION_LANG[region]; lang = cfg["lang"]
    names = " OR ".join(f'"{x}"' for x in GAMES[game][lang][:2])
    query = f"({names}) {EVENT_TERMS[lang]}"
    params = urllib.parse.urlencode({"key": key, "cx": cx, "q": query, "num": min(10, MAX_PER_QUERY), "dateRestrict": "m1"})
    url = f"https://www.googleapis.com/customsearch/v1?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "TCG-Grader-v107/1.0"})
    try:
        with safe_urlopen_no_redirect(req, timeout=TIMEOUT, allowed_hosts=GOOGLE_API_HOSTS) as response:
            data = json.loads(response.read(1_500_000).decode("utf-8", "replace"))
        rows = []
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            title = _short(item.get("title"), 220); link = str(item.get("link") or "")
            snippet = _short(item.get("snippet"), 420); combined = f"{title} {snippet}"
            if not title or not link or not link.startswith("https://"):
                continue
            official = _host(link) in OFFICIAL_HOSTS
            social_host = _host(link) in SOCIAL_HOSTS
            rows.append({
                "game": game, "region": region, "category": _category(combined), "title": title,
                "source": link, "source_kind": "google_cse", "source_tier": "A-search" if official else "B-search",
                "source_label": "Google 검색 · 공식도메인" if official else ("Google 검색 · SNS" if social_host else "Google 검색 보조탐색"),
                "official_domain_match": official, "dates": _dates(combined), "excerpt": snippet,
                "status": "공식출처 검색후보" if official else "검색 교차확인 후보",
                "verified": official, "confidence": 0.90 if official else 0.58, "collected_at": _now(),
            })
        return rows, None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [], f"Google CSE {game}/{region}: {_secret_safe(type(exc).__name__)}"


def collect_google_cse() -> tuple[list[dict], list[str], dict]:
    key = os.environ.get("GOOGLE_CSE_API_KEY", "").strip(); cx = os.environ.get("GOOGLE_CSE_ID", "").strip()
    if not key or not cx:
        return [], [], {"configured": False, "status": "Google Custom Search 미설정/신규고객 종료 · Google News 사용"}
    rows: list[dict] = []; errors: list[str] = []
    # Existing customers only: keep calls intentionally bounded.
    for game in GAMES:
        for region in REGION_LANG:
            part, error = _google_cse_one(game, region, key, cx)
            rows.extend(part)
            if error: errors.append(error)
    return rows, errors, {"configured": True, "query_count": 9, "error_count": len(errors), "result_count": len(rows), "success_query_count": max(0, 9-len(errors)), "status": "Google Custom Search 기존고객 옵션"}


def merge_candidates(rows: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str, str, str], dict] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        game = raw.get("game"); region = raw.get("region"); source = str(raw.get("source") or "")
        if game not in GAMES or region not in REGION_LANG or not source.startswith("https://"):
            continue
        raw = dict(raw)
        raw["title"] = _short(raw.get("title"), 220)
        raw["excerpt"] = _short(raw.get("excerpt"), 300)
        raw["confidence"] = max(0.0, min(1.0, float(raw.get("confidence") or 0.0)))
        if raw["confidence"] < 0.45 or not raw["title"]:
            continue
        key = _candidate_key(raw)
        existing = merged.get(key)
        if existing is None:
            raw["cross_sources"] = [raw.get("source_kind")]
            merged[key] = raw
            continue
        kinds = [x for x in existing.get("cross_sources", []) if x]
        if raw.get("source_kind") not in kinds:
            kinds.append(raw.get("source_kind"))
        sources = int(existing.get("independent_source_count") or 1)
        if _host(str(existing.get("source") or "")) != _host(source) or raw.get("source_kind") != existing.get("source_kind"):
            sources += 1
        if raw["confidence"] > float(existing.get("confidence") or 0.0):
            winner, other = raw, existing
        else:
            winner, other = existing, raw
        winner = dict(winner)
        winner["cross_sources"] = kinds
        winner["independent_source_count"] = min(9, sources)
        if sources >= 2:
            winner["cross_checked"] = True
            winner["confidence"] = min(0.98, max(float(winner.get("confidence") or 0.0), float(other.get("confidence") or 0.0)) + 0.08)
            if winner.get("verified") is not True:
                winner["status"] = "복수출처 교차확인 후보"
        merged[key] = winner
    result = sorted(merged.values(), key=lambda x: (-float(x.get("confidence") or 0.0), str(x.get("published_at") or "")), reverse=False)
    # Above sorting puts confidence ascending because of reverse=False with negative score; keep deterministic tie order.
    result.sort(key=lambda x: (-float(x.get("confidence") or 0.0), str(x.get("game")), str(x.get("region")), str(x.get("title"))))
    return result[:MAX_ITEMS]


def main() -> dict:
    previous = None
    if OUT.exists():
        try:
            previous = json.loads(safe_read_text(OUT))
        except (OSError, ValueError, json.JSONDecodeError):
            previous = None
    registry, registry_errors = refresh_registry(force=False)
    collectors = {
        "google_news": lambda: collect_google_news(),
        "x": lambda: collect_x(registry),
        "instagram": lambda: collect_instagram(registry),
        "google_cse": lambda: collect_google_cse(),
    }
    rows: list[dict] = []
    errors: list[str] = []
    warnings: list[str] = [f"공식 SNS 계정 탐색: {x}" for x in registry_errors]
    channel_status: dict[str, dict] = {}
    workers = 2 if ('com.termux' in os.environ.get('PREFIX','') or 'ANDROID_ROOT' in os.environ) else 4
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tcg-social-event") as pool:
        future_map = {pool.submit(fn): name for name, fn in collectors.items()}
        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                part, part_errors, status = future.result()
                rows.extend(part); errors.extend(part_errors); channel_status[name] = status
            except Exception as exc:
                errors.append(f"{name}: {_secret_safe(f'{type(exc).__name__}: {exc}')}" )
                channel_status[name] = {"configured": True, "status": "수집기 예외 격리"}
    merged = merge_candidates(rows)
    google_status = channel_status.get("google_news", {}) if isinstance(channel_status.get("google_news", {}), dict) else {}
    baseline_ok = int(google_status.get("success_query_count") or 0) > 0
    usable_channels = [k for k, v in channel_status.items() if v.get("configured") is True and int(v.get("success_query_count") or 0) > 0]
    if not merged and previous and isinstance(previous.get("items"), list) and not baseline_ok:
        # Network/API outages should not erase the last known candidate set.
        payload = dict(previous)
        payload.update({
            "updated_at": _now(), "fresh_collection_ok": False, "degraded": True,
            "collection_errors": errors[:50], "collection_warnings": warnings[:50], "channel_status": channel_status,
            "registry_account_count": len(registry.get("accounts", [])),
            "preserved_previous_items": True,
        })
        atomic_write_json(OUT, payload, suffix=".social.tmp")
        return payload
    payload = {
        "version": "v107-full-audit-hardened",
        "updated_at": _now(), "fresh_collection_ok": bool(baseline_ok or usable_channels),
        "degraded": not baseline_ok,
        "policy": "공식 웹사이트 우선. 공식사이트에서 연결된 SNS 계정은 공식 SNS 후보로 표시하며, 그 외 X/Google 결과는 보조후보로만 저장. 공식확정 데이터는 update_promo_events의 공식 허용목록 검증을 통과해야 함.",
        "credential_policy": "토큰/API키는 환경변수에서만 읽고 JSON·로그에 저장하지 않음.",
        "google_policy": "Google News 검색을 기본 사용. Custom Search JSON API는 기존 고객 자격정보가 있을 때만 선택 사용하며 필수 의존성이 아님.",
        "items": merged, "item_count": len(merged),
        "official_social_candidate_count": sum(1 for x in merged if x.get("official_account_verified") is True),
        "official_domain_search_count": sum(1 for x in merged if x.get("official_domain_match") is True),
        "cross_checked_count": sum(1 for x in merged if x.get("cross_checked") is True),
        "channel_status": channel_status,
        "registry_account_count": len(registry.get("accounts", [])),
        "collection_errors": errors[:50],
        "collection_warnings": warnings[:50],
        "preserved_previous_items": False,
    }
    atomic_write_json(OUT, payload, suffix=".social.tmp")
    return payload


if __name__ == "__main__":
    result = main()
    print(json.dumps({
        "ok": result.get("fresh_collection_ok", False),
        "degraded": result.get("degraded", False),
        "items": result.get("item_count", len(result.get("items", []))),
        "official_social": result.get("official_social_candidate_count", 0),
        "errors": len(result.get("collection_errors", [])),
    }, ensure_ascii=False))
