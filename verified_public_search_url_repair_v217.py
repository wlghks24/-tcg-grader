#!/usr/bin/env python3
"""Code-defined repair for regressions that can recreate oversized public-search URLs.

This rule is intentionally narrow. It only repairs three allowlisted TCG discovery
modules and only when the current URL-budget markers are missing. It never changes
the shared HTTPS/SSRF guard, never writes git state, and never turns arbitrary error
or research text into executable code.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

RULE_ID = "public-search-url-budget-v217"
STAGE = "PUBLIC_SEARCH_URL_BUDGET_REGRESSION"
MULTI_ROUTE_PATH = "multi_route_event_discovery.py"
SOCIAL_EVENT_PATH = "social_event_discovery.py"
V144_PATH = "collection_learning_hardening_v144.py"
RULE_PATHS = frozenset({MULTI_ROUTE_PATH, SOCIAL_EVENT_PATH, V144_PATH})
MAX_PUBLIC_SEARCH_URL_CHARS = 1900

_MULTI_MARKERS = (
    "MAX_PUBLIC_SEARCH_URL_CHARS = 1900",
    "def _bounded_bing_request(",
    "q, url = _bounded_bing_request(",
)
_SOCIAL_MARKERS = (
    "MAX_PUBLIC_SEARCH_URL_CHARS = 1900",
    "Google News query exceeds safe URL budget",
)
_V144_MARKERS = (
    "MAX_PUBLIC_SEARCH_URL_CHARS = 1900",
    "public social query exceeds safe URL budget",
)


def _normalized(relative: str) -> str:
    return str(relative).replace("\\", "/")


def _has_all(text: str, markers: tuple[str, ...]) -> bool:
    return all(marker in text for marker in markers)


def detect(relative: str, text: str) -> dict[str, str] | None:
    relative = _normalized(relative)
    if relative == MULTI_ROUTE_PATH:
        relevant = "def _bing_one(" in text and "https://www.bing.com/search?" in text
        healthy = _has_all(text, _MULTI_MARKERS)
    elif relative == SOCIAL_EVENT_PATH:
        relevant = "def _google_news_url(" in text and "news.google.com/rss/search" in text
        healthy = _has_all(text, _SOCIAL_MARKERS)
    elif relative == V144_PATH:
        relevant = "def _v144_ddg_social_one(" in text and "html.duckduckgo.com/html/" in text
        healthy = _has_all(text, _V144_MARKERS)
    else:
        return None
    if not relevant or healthy:
        return None
    return {
        "stage": STAGE,
        "root_cause": "known public-search URL budget guard missing or regressed",
        "evidence": f"{relative} no longer contains the verified bounded-search guard",
        "fix_rule": RULE_ID,
    }


def fingerprint_payload() -> dict[str, Any]:
    return {
        "rule_id": RULE_ID,
        "paths": sorted(RULE_PATHS),
        "limit": MAX_PUBLIC_SEARCH_URL_CHARS,
        "markers": {
            MULTI_ROUTE_PATH: list(_MULTI_MARKERS),
            SOCIAL_EVENT_PATH: list(_SOCIAL_MARKERS),
            V144_PATH: list(_V144_MARKERS),
        },
        "strategy": "exact allowlisted bounded-query guard restoration",
    }


def fingerprint() -> str:
    raw = json.dumps(fingerprint_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def _insert_after(text: str, anchor: str, addition: str) -> str:
    if addition.strip() in text:
        return text
    if anchor not in text:
        return text
    return text.replace(anchor, anchor + addition, 1)


def _replace_function(text: str, name: str, next_name: str, replacement: str) -> str:
    start_token = f"def {name}("
    next_token = f"def {next_name}("
    start = text.find(start_token)
    if start < 0:
        return text
    end = text.find(next_token, start)
    if end < 0:
        return text
    return text[:start] + replacement.rstrip() + "\n\n" + text[end:]


def _repair_multi_route(text: str) -> str:
    if _has_all(text, _MULTI_MARKERS):
        return text
    updated = _insert_after(
        text,
        'DDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}\n',
        'MAX_PUBLIC_SEARCH_URL_CHARS = 1900\n',
    )
    helper = '''def _bounded_bing_request(game: str, region: str, *, hosts: tuple[str, ...] = (),\n                          topic: str | None = None, extra_terms: tuple[str, ...] = ()) -> tuple[str, str]:\n    """Keep Bing RSS requests below the shared HTTPS URL guard."""\n    host_limits = []\n    for value in (len(hosts), min(4, len(hosts)), min(2, len(hosts)), min(1, len(hosts)), 0):\n        if value not in host_limits:\n            host_limits.append(value)\n    extra_limits = []\n    for value in (len(extra_terms), min(3, len(extra_terms)), min(1, len(extra_terms)), 0):\n        if value not in extra_limits:\n            extra_limits.append(value)\n    for host_count in host_limits:\n        for extra_count in extra_limits:\n            query = _query(\n                game, region, scoped_hosts=tuple(hosts[:host_count]), topic=topic,\n                extra_terms=tuple(extra_terms[:extra_count]),\n            )\n            url = "https://www.bing.com/search?" + urllib.parse.urlencode({"format": "rss", "q": query})\n            if len(url) <= MAX_PUBLIC_SEARCH_URL_CHARS:\n                return query, url\n    lang = REGION_LANG[region]\n    names = " OR ".join(f'"{x}"' for x in GAMES[game][lang][:2])\n    family_name = topic if topic in QUERY_FAMILIES[lang] else "event"\n    tokens = shlex.split(QUERY_FAMILIES[lang][family_name])[:4]\n    terms = " OR ".join(f'"{token}"' if " " in token else token for token in tokens)\n    query = f"({names}) ({terms})"\n    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"format": "rss", "q": query})\n    if len(url) > MAX_PUBLIC_SEARCH_URL_CHARS:\n        raise ValueError("public search query exceeds safe URL budget")\n    return query, url\n\n\n'''
    if "def _bounded_bing_request(" not in updated:
        anchor = "def _bing_one("
        pos = updated.find(anchor)
        if pos >= 0:
            updated = updated[:pos] + helper + updated[pos:]
    unsafe = (
        "    q = _query(game, region, scoped_hosts=hosts, topic=topic, extra_terms=extra_terms)\n"
        "    url = \"https://www.bing.com/search?\" + urllib.parse.urlencode({\"format\": \"rss\", \"q\": q})\n"
    )
    safe = "    q, url = _bounded_bing_request(game, region, hosts=hosts, topic=topic, extra_terms=extra_terms)\n"
    updated = updated.replace(unsafe, safe, 1)
    return updated


def _repair_social_event(text: str) -> str:
    if _has_all(text, _SOCIAL_MARKERS):
        return text
    updated = _insert_after(
        text,
        'REGISTRY_TTL_HOURS = env_int("TCG_SOCIAL_REGISTRY_TTL_HOURS", 168, 6, 720)\n',
        'MAX_PUBLIC_SEARCH_URL_CHARS = 1900\n',
    )
    replacement = '''def _google_news_url(game: str, region: str) -> str:\n    cfg = REGION_LANG[region]\n    lang = cfg["lang"]\n    names = " OR ".join(f'"{x}"' for x in GAMES[game][lang][:2])\n    for limit in (16, 12, 9, 6, 4):\n        terms = _or_terms(EVENT_TERMS[lang], limit)\n        query = f"({names}) ({terms}) when:45d"\n        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({\n            "q": query, "hl": cfg["hl"], "gl": cfg["gl"], "ceid": cfg["ceid"],\n        })\n        if len(url) <= MAX_PUBLIC_SEARCH_URL_CHARS:\n            return url\n    raise ValueError("Google News query exceeds safe URL budget")\n'''
    return _replace_function(updated, "_google_news_url", "_parse_pubdate", replacement)


def _repair_v144(text: str) -> str:
    if _has_all(text, _V144_MARKERS):
        return text
    updated = _insert_after(text, "PATCH_ID = 144\n", "MAX_PUBLIC_SEARCH_URL_CHARS = 1900\n")
    anchor = (
        "    query = build_public_social_query(game, region, registry, fan_learner, gap_learner)\n"
        "    url = \"https://html.duckduckgo.com/html/?\" + urllib.parse.urlencode({\"q\": query})\n"
    )
    guarded = '''    query = build_public_social_query(game, region, registry, fan_learner, gap_learner)\n    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})\n    if len(url) > MAX_PUBLIC_SEARCH_URL_CHARS:\n        lang = social_event_discovery.REGION_LANG[region]["lang"]\n        names = " OR ".join(f'"{x}"' for x in social_event_discovery.GAMES[game][lang][:2])\n        events = social_event_discovery._or_terms(social_event_discovery.EVENT_TERMS[lang], 4)\n        query = f"(({names}) ({events})) (site:x.com OR site:instagram.com OR site:youtube.com)"\n        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})\n        if len(url) > MAX_PUBLIC_SEARCH_URL_CHARS:\n            raise ValueError("public social query exceeds safe URL budget")\n'''
    updated = updated.replace(anchor, guarded, 1)
    return updated


def transform(relative: str, text: str) -> str:
    relative = _normalized(relative)
    if relative == MULTI_ROUTE_PATH:
        return _repair_multi_route(text)
    if relative == SOCIAL_EVENT_PATH:
        return _repair_social_event(text)
    if relative == V144_PATH:
        return _repair_v144(text)
    return text
