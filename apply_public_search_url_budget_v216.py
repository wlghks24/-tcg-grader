#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Apply v216 public-search URL budget hardening.

Root cause reproduced on Termux: valid TCG discovery queries could exceed the
shared 2048-character public-HTTPS syntax limit after percent encoding.  The
shared safety guard is intentionally unchanged.  Collectors must fit their
queries inside a smaller 1900-character budget before network I/O.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def write(name: str, text: str) -> None:
    (ROOT / name).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_block(text: str, start_marker: str, end_marker: str, new_block: str, label: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise RuntimeError(f"{label}: start marker missing")
    end = text.find(end_marker, start)
    if end < 0:
        raise RuntimeError(f"{label}: end marker missing")
    return text[:start] + new_block.rstrip() + "\n\n" + text[end + 1:]


def patch_multi_route() -> None:
    name = "multi_route_event_discovery.py"
    text = read(name)
    text = replace_once(
        text,
        "from safe_runtime import env_int, safe_urlopen, validate_public_https_url",
        "from safe_runtime import diagnostic_exception, env_int, safe_urlopen, validate_public_https_url",
        "multi-route safe_runtime import",
    )
    text = replace_once(
        text,
        'DDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}\n',
        'DDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}\n'
        'MAX_PUBLIC_SEARCH_URL_CHARS = 1900\n'
        'BROAD_QUERY_TOPICS = ("event", "promo", "release", "reprint", "stock")\n',
        "multi-route URL budget constants",
    )

    error_block = '''def _error_summary(label: str, exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        retry_after = str(exc.headers.get("Retry-After") or "").strip() if exc.headers else ""
        if exc.code == 429:
            cooldown = f"Retry-After={retry_after}" if retry_after else "Retry-After=미제공"
            return f"{label}: HTTP 429 · {cooldown} · cooldown-required"
        if exc.code == 403:
            return f"{label}: HTTP 403 · access-denied · no-bypass"
        return f"{label}: HTTP {exc.code}"
    return f"{label}: {diagnostic_exception(exc)}"
'''
    text = replace_block(text, "def _error_summary(label: str, exc: Exception) -> str:", "\ndef _parse_pubdate", error_block, "multi-route error summary")

    query_block = '''def _query(game: str, region: str, *, scoped_hosts: tuple[str, ...] = (), topic: str | None = None,
           extra_terms: tuple[str, ...] = ()) -> str:
    lang = REGION_LANG[region]
    names = GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{x}"' for x in names)
    families = QUERY_FAMILIES[lang]
    if topic in families:
        selected = {topic: families[topic]}
    else:
        # Broad source-family probes run in addition to the complete per-topic
        # matrix.  Repeating every topic in one request only bloats the encoded
        # URL and previously crossed safe_runtime's 2048-character ceiling.
        selected = {name: families[name] for name in BROAD_QUERY_TOPICS if name in families}
    terms = " OR ".join(
        "(" + " OR ".join(f'\\"{token}\\"' if " " in token else token for token in shlex.split(value)) + ")"
        for value in selected.values()
    )
    learned = ""
    if extra_terms:
        learned = " OR (" + " OR ".join(f'\\"{term}\\"' if " " in term else term for term in extra_terms[:6]) + ")"
    region_expr = ""
    region_terms = REGION_QUERY_TERMS.get(region, ())
    if region_terms:
        region_expr = " (" + " OR ".join(f'"{term}"' if " " in term else term for term in region_terms) + ")"
    site_expr = ""
    if scoped_hosts:
        site_expr = " (" + " OR ".join(f"site:{host}" for host in scoped_hosts[:8]) + ")"
    return f"({name_expr}) ({terms}{learned}){region_expr}{site_expr}"


def _bing_search_url(query: str) -> str:
    return "https://www.bing.com/search?" + urllib.parse.urlencode({"format": "rss", "q": query})


def _bounded_bing_request(game: str, region: str, *, hosts: tuple[str, ...] = (),
                          topic: str | None = None, extra_terms: tuple[str, ...] = ()) -> tuple[str, str]:
    """Build a valid Bing RSS URL without weakening the shared HTTPS guard."""
    host_limits = []
    for value in (len(hosts), min(4, len(hosts)), min(2, len(hosts)), min(1, len(hosts)), 0):
        if value not in host_limits:
            host_limits.append(value)
    extra_limits = []
    for value in (len(extra_terms), min(3, len(extra_terms)), min(1, len(extra_terms)), 0):
        if value not in extra_limits:
            extra_limits.append(value)
    for host_count in host_limits:
        for extra_count in extra_limits:
            query = _query(
                game,
                region,
                scoped_hosts=tuple(hosts[:host_count]),
                topic=topic,
                extra_terms=tuple(extra_terms[:extra_count]),
            )
            url = _bing_search_url(query)
            if len(url) <= MAX_PUBLIC_SEARCH_URL_CHARS:
                return query, url

    # Deterministic last-resort query: preserve identity + one topic family.
    lang = REGION_LANG[region]
    name_expr = " OR ".join(f'"{x}"' for x in GAMES[game][lang][:2])
    family_name = topic if topic in QUERY_FAMILIES[lang] else "event"
    tokens = shlex.split(QUERY_FAMILIES[lang][family_name])[:4]
    term_expr = " OR ".join(f'"{token}"' if " " in token else token for token in tokens)
    query = f"({name_expr}) ({term_expr})"
    url = _bing_search_url(query)
    if len(url) > MAX_PUBLIC_SEARCH_URL_CHARS:
        raise ValueError("public search query exceeds safe URL budget")
    return query, url
'''
    text = replace_block(text, "def _query(game: str, region: str, *, scoped_hosts:", "\ndef _bing_one", query_block, "multi-route query builder")
    text = replace_once(
        text,
        '    q = _query(game, region, scoped_hosts=hosts, topic=topic, extra_terms=extra_terms)\n    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"format": "rss", "q": q})',
        '    q, url = _bounded_bing_request(game, region, hosts=hosts, topic=topic, extra_terms=extra_terms)',
        "multi-route bounded Bing request",
    )
    write(name, text)


def patch_social_event() -> None:
    name = "social_event_discovery.py"
    text = read(name)
    text = replace_once(
        text,
        "    atomic_write_json,\n    env_int,",
        "    atomic_write_json,\n    diagnostic_exception,\n    env_int,",
        "social diagnostic import",
    )
    text = replace_once(
        text,
        'REGISTRY_TTL_HOURS = env_int("TCG_SOCIAL_REGISTRY_TTL_HOURS", 168, 6, 720)\n',
        'REGISTRY_TTL_HOURS = env_int("TCG_SOCIAL_REGISTRY_TTL_HOURS", 168, 6, 720)\nMAX_PUBLIC_SEARCH_URL_CHARS = 1900\n',
        "social URL budget constant",
    )
    google_block = '''def _google_news_url(game: str, region: str) -> str:
    cfg = REGION_LANG[region]
    lang = cfg["lang"]
    names = " OR ".join(f'"{x}"' for x in GAMES[game][lang][:2])
    for limit in (16, 12, 9, 6, 4):
        terms = _or_terms(EVENT_TERMS[lang], limit)
        query = f"({names}) ({terms}) when:45d"
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
            "q": query,
            "hl": cfg["hl"],
            "gl": cfg["gl"],
            "ceid": cfg["ceid"],
        })
        if len(url) <= MAX_PUBLIC_SEARCH_URL_CHARS:
            return url
    raise ValueError("Google News query exceeds safe URL budget")
'''
    text = replace_block(text, "def _google_news_url(game: str, region: str) -> str:", "\ndef _parse_pubdate", google_block, "Google News bounded URL")
    text = replace_once(
        text,
        '        return [], f"Google News {game}/{region}: {type(exc).__name__}"',
        '        return [], f"Google News {game}/{region}: {diagnostic_exception(exc)}"',
        "Google News diagnostic detail",
    )
    write(name, text)


def patch_v144_social() -> None:
    name = "collection_learning_hardening_v144.py"
    text = read(name)
    text = replace_once(
        text,
        "from safe_runtime import safe_urlopen",
        "from safe_runtime import diagnostic_exception, safe_urlopen",
        "v144 diagnostic import",
    )
    text = replace_once(
        text,
        "PATCH_ID = 144\n",
        "PATCH_ID = 144\nMAX_PUBLIC_SEARCH_URL_CHARS = 1900\n",
        "v144 URL budget constant",
    )
    query_block = '''def build_public_social_query(game: str, region: str, registry: dict, fan_learner=None, gap_learner=None) -> str:
    """Build a multilingual discovery query that always fits the HTTPS URL budget."""
    lang = social_event_discovery.REGION_LANG[region]["lang"]
    names = social_event_discovery.GAMES[game][lang][:2]
    name_expr = " OR ".join(f'"{x}"' for x in names)

    watch_names = _watch_names_for(registry, game, region)
    learned_names = []
    if fan_learner is not None:
        try:
            learned_names = fan_learner.preferred_authors(game, region, limit=6)
        except Exception:
            learned_names = []
    account_names = list(dict.fromkeys(watch_names + [str(x).lstrip("@") for x in learned_names]))[:12]

    if gap_learner is None:
        gap_learner = event_gap_learning.EventGapLearner()
    try:
        learned_terms = tuple(gap_learner.top_terms_for_region(game, region, limit=8))
    except Exception:
        learned_terms = ()

    lang_order = (lang,) + tuple(key for key in ("ko", "ja", "en") if key != lang)
    multilingual = []
    for key in lang_order:
        multilingual.extend(RECOVERY_TERMS[key])
    multilingual.extend(learned_terms)

    # Richest-first presets.  Query semantics degrade gracefully by dropping
    # optional fan/account/learned expansion before the shared HTTPS guard would
    # reject the encoded URL. Game identity and the public social site scope are
    # never removed.
    presets = (
        (18, 14, 12, 28, 8),
        (14, 10, 9, 20, 6),
        (10, 8, 6, 14, 4),
        (8, 6, 4, 10, 3),
        (6, 4, 2, 6, 2),
    )
    site_clause = "(site:x.com OR site:instagram.com OR site:youtube.com)"
    for event_limit, fan_limit, account_limit, watch_limit, learned_limit in presets:
        local_event = social_event_discovery._or_terms(social_event_discovery.EVENT_TERMS[lang], event_limit)
        local_fan = social_event_discovery._or_terms(social_event_discovery.FAN_TERMS[lang], fan_limit)
        account_expr = _quoted_terms(account_names, account_limit)
        watch_term_expr = _quoted_terms(multilingual, watch_limit)
        chosen_learned = learned_terms[:learned_limit]

        general = f"({name_expr}) (({local_event}) OR ({local_fan}))"
        if chosen_learned:
            learned_expr = _quoted_terms(chosen_learned, learned_limit)
            if learned_expr:
                general = f"({general}) OR (({name_expr}) ({learned_expr}))"
        if account_expr and watch_term_expr:
            general = f"({general}) OR (({account_expr}) ({watch_term_expr}))"
        query = f"({general}) {site_clause}"
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        if len(url) <= MAX_PUBLIC_SEARCH_URL_CHARS:
            return query

    local_event = social_event_discovery._or_terms(social_event_discovery.EVENT_TERMS[lang], 4)
    query = f"(({name_expr}) ({local_event})) {site_clause}"
    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    if len(url) > MAX_PUBLIC_SEARCH_URL_CHARS:
        raise ValueError("public social query exceeds safe URL budget")
    return query
'''
    text = replace_block(text, "def build_public_social_query(game: str, region: str, registry: dict, fan_learner=None, gap_learner=None) -> str:", "\ndef _infer_region", query_block, "v144 bounded public social query")
    text = replace_once(
        text,
        '        return [], f"공개 SNS/YouTube v144 검색 {game}/{region}: {type(exc).__name__}"',
        '        return [], f"공개 SNS/YouTube v144 검색 {game}/{region}: {diagnostic_exception(exc)}"',
        "v144 diagnostic detail",
    )
    write(name, text)


def write_tests() -> None:
    test = r'''import unittest
import urllib.parse

import collection_learning_hardening_v144 as v144
import multi_route_event_discovery as routes
import social_event_discovery as social
from safe_runtime import validate_public_https_url


class _FanLearner:
    def preferred_authors(self, game, region, limit=6):
        return [f"collector_{region.lower()}_{i}" for i in range(limit)]


class _GapLearner:
    def top_terms_for_region(self, game, region, limit=8):
        base = ("limited promo", "official announcement", "special event", "registration deadline",
                "participant reward", "exclusive card", "restock notice", "tournament result")
        return base[:limit]


class PublicSearchUrlBudgetV216Tests(unittest.TestCase):
    def test_bing_reproduced_kr_social_case_fits_budget(self):
        query, url = routes._bounded_bing_request(
            "포켓몬 카드", "KR", hosts=routes.SOCIAL_DISCOVERY_HOSTS
        )
        self.assertIn("포켓몬", query)
        self.assertLessEqual(len(url), routes.MAX_PUBLIC_SEARCH_URL_CHARS)
        validate_public_https_url(url, routes.BING_HOSTS)

    def test_bing_all_core_broad_route_families_fit_budget(self):
        for game in routes.GAMES:
            for region in routes.REGIONS:
                groups = (
                    routes.SOCIAL_DISCOVERY_HOSTS,
                    routes.SERVICE_DISCOVERY_HOSTS,
                    routes.COMMUNITY_DISCOVERY_HOSTS,
                    tuple(routes.PARTNER_DOMAINS.get((game, region), ())),
                    tuple(routes.PRESS_DOMAINS.get(region, ())),
                )
                for hosts in groups:
                    if not hosts:
                        continue
                    with self.subTest(game=game, region=region, hosts=hosts[:2]):
                        _, url = routes._bounded_bing_request(game, region, hosts=tuple(hosts))
                        self.assertLessEqual(len(url), routes.MAX_PUBLIC_SEARCH_URL_CHARS)
                        validate_public_https_url(url, routes.BING_HOSTS)

    def test_broad_query_keeps_required_high_value_families(self):
        q = routes._query("포켓몬 카드", "KR")
        self.assertIn("출시", q)
        self.assertIn("프로모", q)
        self.assertIn("재입고", q)
        self.assertIn("이벤트", q)

    def test_google_news_all_game_region_urls_fit_budget(self):
        for game in social.GAMES:
            for region in social.REGION_LANG:
                with self.subTest(game=game, region=region):
                    url = social._google_news_url(game, region)
                    self.assertLessEqual(len(url), social.MAX_PUBLIC_SEARCH_URL_CHARS)
                    validate_public_https_url(url, social.GOOGLE_NEWS_HOSTS)

    def test_v144_social_query_with_watch_and_learned_terms_fits_budget(self):
        registry = {
            "watch_accounts": [
                {
                    "game": "포켓몬 카드",
                    "region": "KR",
                    "content_regions": ["KR"],
                    "trusted": False,
                    "role": "collector community watch",
                    "username": f"pokemon_watch_{i}",
                }
                for i in range(10)
            ]
        }
        query = v144.build_public_social_query(
            "포켓몬 카드", "KR", registry, _FanLearner(), _GapLearner()
        )
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        self.assertLessEqual(len(url), v144.MAX_PUBLIC_SEARCH_URL_CHARS)
        self.assertIn("site:x.com", query)
        self.assertIn("site:instagram.com", query)
        self.assertIn("포켓몬", query)
        validate_public_https_url(url, social.DDG_HOSTS)

    def test_diagnostics_preserve_valueerror_reason_without_bypass(self):
        summary = routes._error_summary("Bing social 포켓몬 카드/KR", ValueError("invalid url"))
        self.assertIn("ValueError", summary)
        self.assertIn("invalid url", summary)
        self.assertNotIn("bypass", summary.lower())


if __name__ == "__main__":
    unittest.main()
'''
    write("test_public_search_url_budget_v216.py", test)


def main() -> None:
    patch_multi_route()
    patch_social_event()
    patch_v144_social()
    write_tests()
    print("v216 public-search URL budget patch applied")


if __name__ == "__main__":
    main()
