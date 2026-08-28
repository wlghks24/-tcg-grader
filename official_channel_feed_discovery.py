#!/usr/bin/env python3
"""Direct official-channel feed discovery independent from search engines.

v117 goals
- Read only trusted/manual official accounts from social_source_registry.json.
- Resolve verified YouTube handles to channel IDs without API keys.
- Pull YouTube's public Atom feed directly, so event/video announcements do not
  depend on Bing/Google/DDG indexing.
- Keep X/Instagram accounts in health diagnostics even when no stable public feed
  exists; never scrape private/session-protected content.
- Return provider="official_youtube_feed" candidates with source identity verified
  by the registry, while leaving event-content confirmation to the existing
  candidate verification pipeline.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from adaptive_collection_learner import canonical_game
from safe_runtime import env_int, safe_read_text, safe_urlopen

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / "social_source_registry.json"
TIMEOUT = env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com"}
ATOM = {"a": "http://www.w3.org/2005/Atom"}
CHANNEL_ID_RE = (
    re.compile(r'"channelId"\s*:\s*"(UC[A-Za-z0-9_-]{20,})"'),
    re.compile(r'"externalId"\s*:\s*"(UC[A-Za-z0-9_-]{20,})"'),
    re.compile(r'itemprop=["\']channelId["\'][^>]+content=["\'](UC[A-Za-z0-9_-]{20,})["\']', re.I),
)

EVENT_TERMS = (
    "event", "events", "promo", "promotion", "tournament", "release", "launch",
    "collab", "collaboration", "campaign", "giveaway", "exclusive", "limited",
    "preorder", "movie", "film", "live", "livestream", "championship",
    "행사", "이벤트", "프로모", "콜라보", "대회", "출시", "발매", "한정", "증정", "생중계",
    "イベント", "プロモ", "コラボ", "大会", "発売", "限定", "配布", "生配信",
)


def _load_registry() -> dict:
    try:
        data = json.loads(safe_read_text(REGISTRY))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _trusted_accounts(game: str | None = None) -> list[dict]:
    data = _load_registry()
    out = []
    for row in data.get("accounts") or []:
        if not isinstance(row, dict) or row.get("trusted") is not True:
            continue
        row_game = canonical_game(row.get("game"))
        if game and row_game != game:
            continue
        out.append(dict(row))
    return out


def _resolve_channel_id(profile_url: str) -> tuple[str | None, str | None]:
    if not str(profile_url).startswith("https://"):
        return None, "invalid profile url"
    req = urllib.request.Request(
        profile_url,
        headers={"User-Agent": "Mozilla/5.0 TCG-Grader-OfficialYouTube/117"},
    )
    try:
        with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=YOUTUBE_HOSTS) as response:
            raw = response.read(1_500_000).decode("utf-8", "replace")
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"[:500]
    for pattern in CHANNEL_ID_RE:
        match = pattern.search(raw)
        if match:
            return match.group(1), None
    return None, "channel id not found"


def parse_youtube_feed(raw: bytes, *, game: str, region: str, account: dict, limit: int = 6) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    rows = []
    for entry in root.findall("a:entry", ATOM):
        title = re.sub(r"\s+", " ", str(entry.findtext("a:title", default="", namespaces=ATOM) or "")).strip()
        published = str(entry.findtext("a:published", default="", namespaces=ATOM) or "").strip() or None
        link = ""
        for node in entry.findall("a:link", ATOM):
            href = str(node.attrib.get("href") or "").strip()
            if href.startswith("https://www.youtube.com/watch") or href.startswith("https://youtube.com/watch"):
                link = href
                break
        if not title or not link:
            continue
        lower = title.lower()
        event_hint = any(term.lower() in lower for term in EVENT_TERMS)
        rows.append({
            "title": title[:240],
            "url": link,
            "published_at": published,
            "verified": False,
            "official_hint": True,
            "official_account_verified": True,
            "search_provider": "official_youtube_feed",
            "query_family": "official-youtube-feed",
            "query_region": region,
            "channel_username": account.get("username"),
            "channel_profile": account.get("profile_url"),
            "event_hint": event_hint,
            "game": game,
        })
        if len(rows) >= max(2, min(12, int(limit))):
            break
    # Event-like titles first, but retain a small recent-official exploration budget.
    rows.sort(key=lambda x: (bool(x.get("event_hint")), str(x.get("published_at") or "")), reverse=True)
    return rows[: max(2, min(12, int(limit)))]


def _collect_youtube_account(game: str, account: dict, limit: int) -> tuple[list[dict], dict]:
    region = str(account.get("region") or "KR")
    profile = str(account.get("profile_url") or "")
    channel_id, error = _resolve_channel_id(profile)
    if not channel_id:
        return [], {
            "platform": "youtube", "username": account.get("username"), "region": region,
            "ok": False, "result_count": 0, "error": error or "channel id resolution failed",
        }
    feed_url = "https://www.youtube.com/feeds/videos.xml?" + urllib.parse.urlencode({"channel_id": channel_id})
    req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0 TCG-Grader-OfficialYouTube/117"})
    try:
        with safe_urlopen(req, timeout=TIMEOUT, allowed_hosts=YOUTUBE_HOSTS) as response:
            raw = response.read(1_200_000)
        rows = parse_youtube_feed(raw, game=game, region=region, account=account, limit=limit)
        return rows, {
            "platform": "youtube", "username": account.get("username"), "region": region,
            "ok": True, "channel_id": channel_id, "result_count": len(rows), "feed_url": feed_url,
        }
    except Exception as exc:
        return [], {
            "platform": "youtube", "username": account.get("username"), "region": region,
            "ok": False, "channel_id": channel_id, "result_count": 0,
            "error": f"{type(exc).__name__}: {exc}"[:500],
        }


def collect_game(keyword: str, limit: int = 6) -> dict:
    game = canonical_game(keyword)
    accounts = _trusted_accounts(game)
    rows: list[dict] = []
    status: list[dict] = []
    errors: list[str] = []
    for account in accounts:
        platform = str(account.get("platform") or "")
        if platform == "youtube_handle":
            part, st = _collect_youtube_account(game, account, limit)
            rows.extend(part)
            status.append(st)
            if not st.get("ok") and st.get("error"):
                errors.append(f"{game}/{account.get('username')}: {st.get('error')}"[:700])
        elif platform in {"x", "instagram"}:
            # These channels remain explicit health/coverage records. Their content is
            # discovered by official-site links and public-search fallback because stable
            # no-auth feeds are not guaranteed.
            status.append({
                "platform": platform,
                "username": account.get("username"),
                "region": account.get("region"),
                "ok": True,
                "result_count": 0,
                "mode": "registry-covered/public-search-fallback",
            })
    deduped = []
    seen = set()
    for row in rows:
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
        "accounts": status,
        "errors": errors[:20],
        "provider": "official_youtube_feed",
    }


if __name__ == "__main__":
    print(json.dumps({k: collect_game(k) for k in ("포켓몬", "원피스", "나루토")}, ensure_ascii=False, indent=2))
