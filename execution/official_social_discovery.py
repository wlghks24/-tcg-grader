"""Bounded account-scoped public RSS discovery; account hints never prove ownership.

Uses the existing verified registry, not a second account list. API credentials
are neither required nor read here. Generic Instagram post URLs stay candidates.
"""
from __future__ import annotations

import concurrent.futures
import datetime as dt
from email.utils import parsedate_to_datetime
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from safe_runtime import diagnostic_exception, safe_urlopen, validate_public_https_url

MAX_ACCOUNTS = 6
MAX_ITEMS = 8
MAX_BYTES = 1_000_000
REQUEST_INTERVAL = 2.0
TIMEOUT = 8
PROVIDER_HOSTS = {"google": {"news.google.com"}, "bing": {"www.bing.com", "bing.com"}}
PLATFORM_HOSTS = {
    "instagram": "instagram.com", "x": "x.com", "facebook": "facebook.com",
    "youtube": "youtube.com", "tiktok": "tiktok.com", "twitch": "twitch.tv",
}


def retry_after_seconds(value, now):
    """Honor both HTTP Retry-After forms without shortening a provider's wait."""
    if not isinstance(value,str) or len(value)>128:
        return 0
    value=value.strip()
    if re.fullmatch(r'[0-9]{1,64}',value):
        return int(value)
    try:
        stamp=parsedate_to_datetime(value)
        if stamp.tzinfo is None:return 0
        return max(0,stamp.timestamp()-now)
    except (ValueError,TypeError,OverflowError):
        return 0


def select_accounts(registry, now):
    """Rotate groups and accounts every six hours; never privilege array order."""
    import social_event_discovery as social
    groups = {}
    accounts = registry.get("accounts", []) if isinstance(registry, dict) else []
    if not isinstance(accounts, list):
        return [], 0
    seen = set()
    for account in accounts[:2000]:
        if not isinstance(account, dict) or account.get("trusted") is not True:
            continue
        game, region = account.get("game"), account.get("region")
        profile = account.get("profile_url")
        if game not in social.GAMES or region not in social.REGION_LANG or not isinstance(profile, str):
            continue
        parsed = social._parse_social_link(profile)
        if not parsed or parsed[0].split("_", 1)[0] not in PLATFORM_HOSTS:
            continue
        platform, username = parsed
        if (platform != account.get("platform") or
                username.lower().lstrip("@") != str(account.get("username", "")).lower().lstrip("@")):
            continue
        try:
            validate_public_https_url(profile, social.SOCIAL_HOSTS)
        except (ValueError, TypeError):
            continue
        key = (game, region, platform, username.casefold())
        if key in seen:
            continue
        seen.add(key)
        groups.setdefault((game, region), []).append(account)
    slot = int(now // (6 * 3600))
    keys = sorted(groups)
    if not keys:
        return [], 0
    for values in groups.values():
        values.sort(key=lambda a: (a["platform"], a["username"].casefold()))
    # Interleave groups once, then visit contiguous bounded blocks. Rotating
    # group and account indices by the same modulus can permanently starve
    # accounts when both group counts and account counts share a period.
    ordered = [groups[key][index]
               for index in range(max(map(len, groups.values())))
               for key in keys if index < len(groups[key])]
    offset = (slot * MAX_ACCOUNTS) % len(ordered)
    selected = [ordered[(offset + i) % len(ordered)]
                for i in range(min(MAX_ACCOUNTS, len(ordered)))]
    return selected, len(seen)


def search_url(provider, account):
    import social_event_discovery as social
    cfg = social.REGION_LANG[account["region"]]
    platform = account["platform"].split("_", 1)[0]
    username = account["username"].lstrip("@")
    # Validation in select_accounts excludes arbitrary search operators/URLs.
    terms = list(dict.fromkeys(term for topic in ("event", "promo", "collab", "release", "reprint", "stock", "tournament", "movie")
                               for term in social.multi_route_event_discovery.QUERY_FAMILIES[cfg["lang"]][topic].split()[:2]))
    names = " OR ".join(f'"{name}"' for name in social.GAMES[account["game"]][cfg["lang"]][:2])
    query = f'site:{PLATFORM_HOSTS[platform]} "{username}" ({names}) ({social._or_terms(" ".join(terms), 16)})'
    if provider == "google":
        query += " when:45d"
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": cfg["hl"], "gl": cfg["gl"], "ceid": cfg["ceid"]})
    else:
        url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "format": "rss", "mkt": {"KR":"ko-KR", "JP":"ja-JP", "US":"en-US"}[account["region"]]})
    if len(url) > 1900:
        raise ValueError("official account query exceeds safe URL budget")
    return url


def _parse(raw, provider, account, registry, now):
    import social_event_discovery as social
    if len(raw) > MAX_BYTES or re.search(br"<!\s*(DOCTYPE|ENTITY)\b", raw, re.I):
        raise ValueError("oversized or entity-bearing RSS")
    root = ET.fromstring(raw)
    if root.tag != "rss":
        raise ValueError("expected RSS, not an HTML challenge")
    rows = []
    seen = set()
    for item in root.findall("./channel/item")[:MAX_ITEMS * 3]:
        title = social._short(item.findtext("title"), 220)
        description = social._short(item.findtext("description"), 500)
        source = (item.findtext("link") or "").strip()
        combined = title + " " + description
        if not title or not social.multi_route_event_discovery.KEYWORD_RE.search(combined):
            continue
        # A shared publisher account does not prove which game a post concerns.
        shared_games = {a.get("game") for a in registry.get("accounts", [])
                        if isinstance(a, dict) and a.get("trusted") is True
                        and a.get("platform") == account["platform"]
                        and str(a.get("username", "")).casefold() == account["username"].casefold()}
        lang = social.REGION_LANG[account["region"]]["lang"]
        if len(shared_games) > 1 and not any(name.casefold() in combined.casefold()
                for name in social.GAMES[account["game"]][lang]):
            continue
        try:
            validate_public_https_url(source, social.SOCIAL_HOSTS | PROVIDER_HOSTS["google"])
        except (TypeError, ValueError):
            continue
        if source in seen:
            continue
        seen.add(source)
        official, author = social._official_social_match(registry, source, title, account["game"], account["region"])
        rows.append({
            "game": account["game"], "region": account["region"], "title": title,
            "category": social._category(title + " " + description), "source": source,
            "source_kind": provider + "_official_account_search",
            "source_tier": "A-social" if official else "B-search",
            "source_label": provider.title() + " · 등록 공식계정 지정 탐색",
            "requested_account": account["username"], "requested_profile": account["profile_url"],
            "author": author, "official_account_verified": official, "verified": official,
            "status": "공식 SNS 후보" if official else "계정 지정 검색후보 · 게시자 확인 필요",
            "confidence": 0.93 if official else 0.55,
            "published_at": social._parse_pubdate(item.findtext("pubDate")),
            # Search snippets/publication dates cannot establish event dates.
            "dates": [], "excerpt": description or title,
            "route_family": "official_account_search", "collected_at": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"),
        })
        if len(rows) >= MAX_ITEMS:
            break
    return rows


def _provider(provider, accounts, registry, prior, now):
    rows, errors = [], []
    prior = prior if isinstance(prior, dict) else {}
    until = prior.get("blocked_until", 0)
    if type(until) not in (int, float) or not math.isfinite(until) or until<0:
        until = 0
    status = {"attempted": 0, "successful": 0, "result_count": 0, "state": "UNKNOWN", "blocked_until": until}
    if until > now:
        status["state"] = "COOLDOWN"
        if type(prior.get("last_slot")) is int: status["last_slot"] = prior["last_slot"]
        return rows, errors, status
    slot = int(now // (6 * 3600))
    last_slot = prior.get("last_slot")
    if type(last_slot) is int and last_slot == slot:
        status.update(state="SLOT_ALREADY_ATTEMPTED", last_slot=slot)
        return rows, errors, status
    status["last_slot"] = slot
    for index, account in enumerate(accounts):
        if index:
            time.sleep(REQUEST_INTERVAL)
        status["attempted"] += 1
        try:
            request = urllib.request.Request(search_url(provider, account), headers={"User-Agent": "TCG-Grader-OfficialAccountDiscovery/1.0"})
            with safe_urlopen(request, timeout=TIMEOUT, allowed_hosts=PROVIDER_HOSTS[provider]) as response:
                raw = response.read(MAX_BYTES + 1)
            rows.extend(_parse(raw, provider, account, registry, now))
            status["successful"] += 1
        except (urllib.error.URLError, OSError, ValueError, TypeError, ET.ParseError) as exc:
            errors.append(provider + " official account: " + diagnostic_exception(exc))
            code = exc.code if isinstance(exc, urllib.error.HTTPError) else 0
            if code in (403, 429):
                delay = 86400 if code == 403 else 21600
                retry = exc.headers.get("Retry-After", "") if exc.headers else ""
                delay = max(delay, retry_after_seconds(retry,now))
                status.update(state="BLOCKED" if code == 403 else "RATE_LIMITED", blocked_until=now + delay)
                break
    status["result_count"] = len(rows)
    if status["state"] == "UNKNOWN":
        status["state"] = "HEALTHY" if status["successful"] == len(accounts) and accounts else "DEGRADED"
    return rows, errors, status


def collect(registry, previous=None, *, now=None):
    now = time.time() if now is None else now
    accounts, eligible = select_accounts(registry, now)
    previous = previous if isinstance(previous, dict) else {}
    providers = previous.get("providers", {})
    providers = providers if isinstance(providers, dict) else {}
    rows, errors, statuses = [], [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_provider, name, accounts, registry, providers.get(name), now): name for name in PROVIDER_HOSTS}
        for future in concurrent.futures.as_completed(futures):
            part, failures, status = future.result()
            rows.extend(part); errors.extend(failures); statuses[futures[future]] = status
    return rows, errors, {
        "configured": True, "eligible_account_count": eligible, "selected_account_count": len(accounts),
        "query_count": len(accounts) * 2, "attempted_query_count": sum(s["attempted"] for s in statuses.values()),
        "success_query_count": sum(s["successful"] for s in statuses.values()),
        "result_count": len(rows), "error_count": len(errors), "providers": statuses,
        "status": "공식 등록계정 6시간 순환 · Google/Bing RSS · 게시자 별도 확인",
    }
