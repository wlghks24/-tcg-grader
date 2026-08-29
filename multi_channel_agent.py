#!/usr/bin/env python3
"""Adaptive multi-provider public-web candidate collector.

v119:
- Keeps adaptive KR/JP/US + official/social query planning.
- DuckDuckGo HTML automatically falls back to DuckDuckGo Lite when the HTML
  result shape yields zero parsed links.
- Google News uses region-specific KR/JP/US locale settings and a compact OR
  query instead of sending one long learned query verbatim.
- Every no-key provider is queried for each plan and provider results are merged
  in round-robin order.
- Final learner ranking is diversified again so one provider cannot re-dominate
  after relevance scoring when other relevant providers also produced leads.
- A strict learned query that returns zero is retried with a compact OR query.
- HTTP-success + zero-result is an EMPTY search, not a hard collection failure.
- Official trust is never inferred merely from repeated discovery.
"""
from __future__ import annotations

import html
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

from adaptive_collection_learner import AdaptiveCollectionLearner, canonical_game
from safe_runtime import env_int, safe_urlopen
from search_method_learning import SearchMethodLearner


class MultiChannelCollector:
    HEADERS = {"User-Agent": "Mozilla/5.0 TCG-Grader/115"}
    DDG_HOSTS = {
        "html.duckduckgo.com", "lite.duckduckgo.com",
        "duckduckgo.com", "www.duckduckgo.com",
    }
    BING_HOSTS = {"www.bing.com", "bing.com"}
    GOOGLE_NEWS_HOSTS = {"news.google.com"}
    NAVER_HOSTS = {"search.naver.com", "m.search.naver.com"}
    PROVIDER_COUNT = 7

    GAME_NAMES = {
        "포켓몬": {"KR": "포켓몬 카드", "JP": "ポケモンカード", "US": "Pokemon TCG"},
        "원피스": {"KR": "원피스 카드", "JP": "ワンピースカード", "US": "One Piece Card Game"},
        "나루토": {"KR": "나루토 카드게임", "JP": "NARUTO カードゲーム", "US": "NARUTO CARD GAME"},
    }
    EVENT_OR = {
        "KR": ("행사", "이벤트", "콜라보", "프로모", "프로모카드", "출시", "발매", "재발매", "한정", "증정", "대회", "영화"),
        "JP": ("イベント", "コラボ", "プロモ", "プロモカード", "発売", "再販", "限定", "配布", "大会", "映画"),
        "US": ("event", "collab", "collaboration", "promo", "promo card", "release", "restock", "exclusive", "giveaway", "tournament", "movie"),
    }
    GOOGLE_LOCALE = {
        "KR": {"hl": "ko", "gl": "KR", "ceid": "KR:ko"},
        "JP": {"hl": "ja", "gl": "JP", "ceid": "JP:ja"},
        "US": {"hl": "en-US", "gl": "US", "ceid": "US:en"},
    }

    def __init__(self, learner: AdaptiveCollectionLearner | None = None):
        self.learner = learner or AdaptiveCollectionLearner()
        self.method_learner = SearchMethodLearner()
        self.method_learner.start_run()
        self._learning_lock = threading.RLock()
        self._route_local = threading.local()

    @staticmethod
    def _timeout() -> int:
        return env_int("TCG_HTTP_TIMEOUT", 20, 5, 60)

    @staticmethod
    def _transient(exc: Exception) -> bool:
        text = f"{type(exc).__name__}: {exc}".lower()
        return any(x in text for x in (
            "timeout", "timed out", "urlerror", "temporary", "name resolution",
            "connection", "remote end closed", "429", "502", "503",
        ))

    @staticmethod
    def _clean_title(value: object) -> str:
        text = re.sub(r"<[^>]+>", " ", html.unescape(str(value or "")))
        return re.sub(r"\s+", " ", text).strip()[:240]

    @staticmethod
    def _decode_result_url(href: str) -> str:
        value = html.unescape(str(href or "")).strip()
        if value.startswith("//"):
            value = "https:" + value
        if value.startswith("/"):
            value = "https://html.duckduckgo.com" + value
        try:
            parsed = urllib.parse.urlsplit(value)
        except ValueError:
            return ""
        host = (parsed.hostname or "").lower()
        if host in MultiChannelCollector.DDG_HOSTS:
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
            if target:
                value = urllib.parse.unquote(target)
        return value if value.startswith("https://") else ""

    @staticmethod
    def _dedupe(rows: list[dict], limit: int) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for row in rows:
            url = str(row.get("url") or "").strip()
            title = str(row.get("title") or "").strip()
            if not url.startswith("https://") or not title or url in seen:
                continue
            seen.add(url)
            out.append(row)
            if len(out) >= max(3, min(50, int(limit))):
                break
        return out

    @classmethod
    def _round_robin_merge(cls, provider_rows: dict[str, list[dict]], limit: int) -> list[dict]:
        order = ("duckduckgo", "bing_rss", "bing_news", "google_news", "naver_news")
        max_len = max((len(provider_rows.get(name, [])) for name in order), default=0)
        merged: list[dict] = []
        for index in range(max_len):
            for name in order:
                rows = provider_rows.get(name, [])
                if index < len(rows):
                    merged.append(rows[index])
        return cls._dedupe(merged, limit)

    @classmethod
    def _diversify_ranked(cls, ranked: list[dict], limit: int) -> list[dict]:
        """Keep relevance ordering within each provider, but prevent provider monopoly."""
        limit = max(1, min(30, int(limit)))
        provider_rows: dict[str, list[dict]] = {}
        leftovers: list[dict] = []
        for row in ranked:
            provider = str(row.get("search_provider") or "unknown")
            score = float(row.get("relevance_score") or 0.0)
            if score >= 2.0 or row.get("official_hint"):
                provider_rows.setdefault(provider, []).append(row)
            else:
                leftovers.append(row)
        preferred_order = ("duckduckgo", "google_news", "bing_rss", "bing_news", "naver_news")
        max_len = max((len(provider_rows.get(name, [])) for name in preferred_order), default=0)
        mixed: list[dict] = []
        seen: set[str] = set()
        for index in range(max_len):
            for provider in preferred_order:
                rows = provider_rows.get(provider, [])
                if index >= len(rows):
                    continue
                row = rows[index]
                url = str(row.get("url") or "")
                if url and url not in seen:
                    seen.add(url)
                    mixed.append(row)
                    if len(mixed) >= limit:
                        return mixed
        for row in ranked + leftovers:
            url = str(row.get("url") or "")
            if url and url not in seen:
                seen.add(url)
                mixed.append(row)
                if len(mixed) >= limit:
                    break
        return mixed[:limit]

    def _fetch_with_retry(self, req: urllib.request.Request, allowed_hosts: set[str], max_bytes: int = 900_000) -> tuple[bytes | None, str | None, int]:
        last_error = None
        attempts = 0
        runtime = getattr(self._route_local, "policy", {}) if hasattr(self, "_route_local") else {}
        timeout = int(runtime.get("timeout_seconds") or self._timeout())
        max_attempts = max(1, min(3, int(runtime.get("max_attempts") or 2)))
        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                with safe_urlopen(req, timeout=timeout, allowed_hosts=allowed_hosts) as response:
                    return response.read(max_bytes), None, attempts
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"[:500]
                if attempt >= max_attempts - 1 or not self._transient(exc):
                    break
                time.sleep(0.7)
        return None, last_error or "unknown provider error", attempts

    def _parse_ddg_html(self, text: str, limit: int) -> list[dict]:
        matches = re.findall(
            r'<a[^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
            text, re.I | re.S,
        )
        if not matches:
            matches = re.findall(
                r'<a[^>]+href=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*result__a[^"\']*["\'][^>]*>(.*?)</a>',
                text, re.I | re.S,
            )
        rows = []
        for href, title in matches:
            target = self._decode_result_url(href)
            clean = self._clean_title(title)
            if target and clean:
                rows.append({"title": clean, "url": target, "verified": False, "search_provider": "duckduckgo"})
        return self._dedupe(rows, limit)

    def _parse_ddg_lite(self, text: str, limit: int) -> list[dict]:
        rows = []
        for href, title in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', text, re.I | re.S):
            target = self._decode_result_url(href)
            clean = self._clean_title(title)
            if not target or not clean:
                continue
            try:
                host = (urllib.parse.urlsplit(target).hostname or "").lower()
            except ValueError:
                continue
            if host in self.DDG_HOSTS or len(clean) < 4:
                continue
            rows.append({"title": clean, "url": target, "verified": False, "search_provider": "duckduckgo"})
        return self._dedupe(rows, limit)

    def _search_ddg(self, query: str, limit: int) -> tuple[list[dict], str | None, int, bool]:
        attempts_total = 0
        html_url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(html_url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.DDG_HOSTS)
        attempts_total += attempts
        if raw is not None:
            rows = self._parse_ddg_html(raw.decode("utf-8", "replace"), limit)
            if rows:
                return rows, None, attempts_total, True
        first_error = error

        lite_url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(lite_url, headers=self.HEADERS)
        raw, lite_error, attempts = self._fetch_with_retry(req, self.DDG_HOSTS)
        attempts_total += attempts
        if raw is None:
            combined = " / ".join(x for x in (first_error, lite_error) if x)
            return [], combined or "DuckDuckGo unavailable", attempts_total, False
        rows = self._parse_ddg_lite(raw.decode("utf-8", "replace"), limit)
        return rows, None, attempts_total, True

    def _search_bing_rss(self, query: str, limit: int) -> tuple[list[dict], str | None, int, bool]:
        url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "format": "rss"})
        req = urllib.request.Request(url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.BING_HOSTS)
        if raw is None:
            return [], error, attempts, False
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            return [], f"ParseError: {exc}"[:500], attempts, False
        rows = []
        for item in root.findall("./channel/item"):
            title = self._clean_title(item.findtext("title"))
            link = str(item.findtext("link") or "").strip()
            if title and link.startswith("https://"):
                rows.append({"title": title, "url": link, "verified": False, "search_provider": "bing_rss"})
        return self._dedupe(rows, limit), None, attempts, True

    def _detect_game_name(self, query: str, region: str) -> str:
        low = str(query or "").lower()
        for game, by_region in self.GAME_NAMES.items():
            if any(name.lower() in low for name in by_region.values()):
                return by_region.get(region, by_region["KR"])
        return re.sub(r"\bsite:[A-Za-z0-9.-]+", "", str(query or "")).strip().split("  ", 1)[0][:80]

    def _compact_news_query(self, query: str, region: str) -> str:
        region = region if region in self.EVENT_OR else "KR"
        name = self._detect_game_name(query, region)
        terms = self.EVENT_OR[region]
        event_expr = " OR ".join(f'"{term}"' if " " in term else term for term in terms[:6])
        return f'"{name}" ({event_expr}) when:60d'[:280]

    def _search_google_news(self, query: str, limit: int, region: str = "KR") -> tuple[list[dict], str | None, int, bool]:
        region = region if region in self.GOOGLE_LOCALE else "KR"
        locale = self.GOOGLE_LOCALE[region]
        compact = self._compact_news_query(query, region)
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": compact, **locale})
        req = urllib.request.Request(url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.GOOGLE_NEWS_HOSTS, max_bytes=1_200_000)
        if raw is None:
            return [], error, attempts, False
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            return [], f"ParseError: {exc}"[:500], attempts, False
        rows = []
        for item in root.findall("./channel/item"):
            title = self._clean_title(item.findtext("title"))
            link = str(item.findtext("link") or "").strip()
            if title and link.startswith("https://"):
                rows.append({"title": title, "url": link, "verified": False, "search_provider": "google_news"})
        return self._dedupe(rows, limit), None, attempts, True

    def _search_ddg_html_only(self, query: str, limit: int) -> tuple[list[dict], str | None, int, bool]:
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.DDG_HOSTS)
        if raw is None:
            return [], error, attempts, False
        rows = self._parse_ddg_html(raw.decode("utf-8", "replace"), limit)
        for row in rows:
            row["search_method"] = "ddg_html"
            row["search_provider"] = "duckduckgo"
        return rows, None, attempts, True

    def _search_ddg_lite_only(self, query: str, limit: int) -> tuple[list[dict], str | None, int, bool]:
        url = "https://lite.duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
        req = urllib.request.Request(url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.DDG_HOSTS)
        if raw is None:
            return [], error, attempts, False
        rows = self._parse_ddg_lite(raw.decode("utf-8", "replace"), limit)
        for row in rows:
            row["search_method"] = "ddg_lite"
            row["search_provider"] = "duckduckgo"
        return rows, None, attempts, True

    def _search_bing_news_rss(self, query: str, limit: int, region: str = "KR") -> tuple[list[dict], str | None, int, bool]:
        market = {"KR": ("ko", "kr"), "JP": ("ja", "jp"), "US": ("en", "us")}.get(region, ("ko", "kr"))
        params = {"q": query, "format": "rss", "setlang": market[0], "cc": market[1]}
        url = "https://www.bing.com/news/search?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.BING_HOSTS, max_bytes=1_200_000)
        if raw is None:
            return [], error, attempts, False
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            return [], f"ParseError: {exc}"[:500], attempts, False
        rows = []
        for item in root.findall("./channel/item"):
            title = self._clean_title(item.findtext("title"))
            link = str(item.findtext("link") or "").strip()
            if title and link.startswith("https://"):
                rows.append({"title": title, "url": link, "verified": False,
                             "search_provider": "bing_news", "search_method": "bing_news_rss"})
        return self._dedupe(rows, limit), None, attempts, True

    def _search_google_news_broad(self, query: str, limit: int, region: str = "KR") -> tuple[list[dict], str | None, int, bool]:
        region = region if region in self.GOOGLE_LOCALE else "KR"
        locale = self.GOOGLE_LOCALE[region]
        name = self._detect_game_name(query, region)
        terms = self.EVENT_OR.get(region, self.EVENT_OR["KR"])
        rotation = sum(ord(ch) for ch in (name + region)) % len(terms)
        chosen = [terms[(rotation + i) % len(terms)] for i in range(3)]
        broad = f'{name} ("{chosen[0]}" OR "{chosen[1]}" OR "{chosen[2]}") when:120d'[:260]
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": broad, **locale})
        req = urllib.request.Request(url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.GOOGLE_NEWS_HOSTS, max_bytes=1_200_000)
        if raw is None:
            return [], error, attempts, False
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            return [], f"ParseError: {exc}"[:500], attempts, False
        rows = []
        for item in root.findall("./channel/item"):
            title = self._clean_title(item.findtext("title"))
            link = str(item.findtext("link") or "").strip()
            if title and link.startswith("https://"):
                rows.append({"title": title, "url": link, "verified": False,
                             "search_provider": "google_news", "search_method": "google_news_broad"})
        return self._dedupe(rows, limit), None, attempts, True

    def _search_naver_news(self, query: str, limit: int) -> tuple[list[dict], str | None, int, bool]:
        # Public news search page only. No login/private API/CAPTCHA bypass.
        url = "https://search.naver.com/search.naver?" + urllib.parse.urlencode({"where": "news", "query": query, "sort": "1"})
        req = urllib.request.Request(url, headers=self.HEADERS)
        raw, error, attempts = self._fetch_with_retry(req, self.NAVER_HOSTS, max_bytes=1_200_000)
        if raw is None:
            return [], error, attempts, False
        text = raw.decode("utf-8", "replace")
        rows = []
        seen = set()
        patterns = (
            r'<a[^>]+class=["\'][^"\']*(?:news_tit|title_link)[^"\']*["\'][^>]+href=["\'](https://[^"\']+)["\'][^>]*>(.*?)</a>',
            r'<a[^>]+href=["\'](https://[^"\']+)["\'][^>]+class=["\'][^"\']*(?:news_tit|title_link)[^"\']*["\'][^>]*>(.*?)</a>',
        )
        matches = []
        for pattern in patterns:
            matches.extend(re.findall(pattern, text, re.I | re.S))
        for href, raw_title in matches:
            clean = self._clean_title(raw_title)
            if not clean or href in seen:
                continue
            seen.add(href)
            rows.append({"title": clean, "url": html.unescape(href), "verified": False,
                         "search_provider": "naver_news", "search_method": "naver_news_html"})
            if len(rows) >= limit:
                break
        return self._dedupe(rows, limit), None, attempts, True

    def _minimal_query(self, keyword: str, region: str, family: str) -> str:
        game = canonical_game(keyword)
        name = self.GAME_NAMES.get(game, {}).get(region, str(keyword or "").strip())
        terms = self.EVENT_OR.get(region, self.EVENT_OR["KR"])
        rotation = (sum(ord(ch) for ch in (game + family + region)) + int(time.time() // 21600)) % len(terms)
        selected = [terms[rotation], terms[(rotation + 3) % len(terms)]]
        return f'{name} "{selected[0]}" "{selected[1]}"'[:220]

    def _search_once(self, query: str, limit: int, region: str = "KR", family: str = "web") -> tuple[list[dict], list[str], int, bool, int]:
        """Run multiple public methods in learned order and isolate blocked routes."""
        query = re.sub(r"\s+", " ", str(query or "")).strip()[:280]
        routes = {
            "ddg_html": lambda q, n: self._search_ddg_html_only(q, n),
            "ddg_lite": lambda q, n: self._search_ddg_lite_only(q, n),
            "bing_web_rss": lambda q, n: self._search_bing_rss(q, n),
            "bing_news_rss": lambda q, n: self._search_bing_news_rss(q, n, region),
            "google_news_rss": lambda q, n: self._search_google_news(q, n, region),
            "google_news_broad": lambda q, n: self._search_google_news_broad(q, n, region),
            "naver_news_html": lambda q, n: self._search_naver_news(q, n),
        }
        is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ
        with self._learning_lock:
            budget = self.method_learner.recommended_budget(routes.keys(), region=region, family=family, is_android=is_android)
            ordered = self.method_learner.ordered_routes(routes.keys(), region=region, family=family, budget=budget)
        errors: list[str] = []
        attempts = 0
        provider_rows: dict[str, list[dict]] = {}
        responded_any = False
        for method in ordered:
            fn = routes[method]
            with self._learning_lock:
                runtime_policy = self.method_learner.route_policy(method, region=region, family=family)
            self._route_local.policy = runtime_policy
            started = time.monotonic()
            try:
                rows, error, used_attempts, responded = fn(query, max(limit, 8))
            except Exception as exc:
                rows, error, used_attempts, responded = [], f"{type(exc).__name__}: {exc}"[:500], 1, False
            finally:
                self._route_local.policy = {}
            elapsed_ms = (time.monotonic() - started) * 1000.0
            attempts += max(1, int(used_attempts or 1))
            responded_any = responded_any or responded
            for row in rows:
                row.setdefault("search_method", method)
                row.setdefault("route_policy_score", runtime_policy.get("score"))
                row.setdefault("route_timeout_seconds", runtime_policy.get("timeout_seconds"))
            provider_rows[method] = rows
            with self._learning_lock:
                self.method_learner.observe(method, responded=responded, result_count=len(rows), error=error or "",
                                            elapsed_ms=elapsed_ms, region=region, family=family)
            if error:
                errors.append(f"{method}: {error}"[:600])
        # Interleave by learned route order so one method cannot monopolize the result pool.
        merged_pool = []
        max_len = max((len(provider_rows.get(name, [])) for name in ordered), default=0)
        for index in range(max_len):
            for method in ordered:
                rows = provider_rows.get(method, [])
                if index < len(rows):
                    merged_pool.append(rows[index])
        merged = self._dedupe(merged_pool, limit)
        all_hard_failed = not responded_any
        if all_hard_failed:
            skipped = [name for name in routes if name not in ordered]
            for name in skipped:
                errors.append(f"{name}: temporary cooldown or route budget")
        return merged, errors, attempts, all_hard_failed, len(ordered)

    def _normalize_once_result(self, result):
        """Accept v115 3-tuple mocks and v118 5-tuple route results.

        Existing regression tests and downstream extensions sometimes replace
        _search_once with the historical (rows, errors, attempts) contract.
        Empty + no-error remains a successful transport with zero results.
        """
        if isinstance(result, tuple) and len(result) == 5:
            rows, errors, attempts, hard, route_count = result
            return rows, errors, attempts, bool(hard), max(1, int(route_count or 1))
        if isinstance(result, tuple) and len(result) == 3:
            rows, errors, attempts = result
            errors = list(errors or [])
            # Legacy collector had three independent providers. No error means
            # transport succeeded even when the search result is empty.
            hard = not rows and len(errors) >= 3
            return list(rows or []), errors, int(attempts or 0), hard, 3
        raise ValueError("invalid _search_once result contract")

    def _relaxed_query(self, keyword: str, region: str, family: str, original: str) -> str:
        game = canonical_game(keyword)
        name = self.GAME_NAMES.get(game, {}).get(region, str(keyword or "").strip())
        terms = self.EVENT_OR.get(region, self.EVENT_OR["KR"])
        rotation = sum(ord(ch) for ch in (family + region + game)) % len(terms)
        chosen = [terms[(rotation + offset) % len(terms)] for offset in range(4)]
        event_expr = " OR ".join(f'"{term}"' if " " in term else term for term in chosen)
        site_match = re.search(r"\bsite:([A-Za-z0-9.-]+)", original or "", re.I)
        site = f" site:{site_match.group(1)}" if site_match else ""
        return f'"{name}" ({event_expr}){site}'.strip()[:280]

    def search_web(self, keyword, limit=8):
        keyword = str(keyword or "").strip()[:80]
        is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ
        query_budget = 5 if is_android else 8
        with self._learning_lock:
            plans = self.learner.plan_queries(keyword, max_queries=query_budget)
        all_rows: list[dict] = []
        errors: list[str] = []
        query_results: list[dict] = []
        total_retries = 0
        transport_successes = 0

        for plan in plans:
            query = str(plan.get("query") or "")
            family = str(plan.get("family") or "web")
            region = str(plan.get("region") or "KR")
            once_result = self._search_once(query, max(limit, 8), region, family)
            rows, attempt_errors, attempts, route_hard, route_count = self._normalize_once_result(once_result)
            used_query = query
            relaxed = False
            minimal = False
            transport_any = not route_hard
            request_baseline = route_count

            if not rows and transport_any:
                relaxed_query = self._relaxed_query(keyword, region, family, query)
                if relaxed_query and relaxed_query != query:
                    relaxed_result = self._search_once(
                        relaxed_query, max(limit, 8), region, family + ":relaxed"
                    )
                    relaxed_rows, relaxed_errors, relaxed_attempts, relaxed_hard, relaxed_count = self._normalize_once_result(relaxed_result)
                    attempts += relaxed_attempts
                    request_baseline += relaxed_count
                    attempt_errors.extend(relaxed_errors)
                    transport_any = transport_any or not relaxed_hard
                    if relaxed_rows:
                        rows = relaxed_rows
                        used_query = relaxed_query
                        relaxed = True

            if not rows and transport_any:
                minimal_query = self._minimal_query(keyword, region, family)
                if minimal_query and minimal_query not in {query, used_query}:
                    minimal_result = self._search_once(
                        minimal_query, max(limit, 8), region, family + ":minimal"
                    )
                    minimal_rows, minimal_errors, minimal_attempts, minimal_hard, minimal_count = self._normalize_once_result(minimal_result)
                    attempts += minimal_attempts
                    request_baseline += minimal_count
                    attempt_errors.extend(minimal_errors)
                    transport_any = transport_any or not minimal_hard
                    if minimal_rows:
                        rows = minimal_rows
                        used_query = minimal_query
                        minimal = True

            total_retries += max(0, attempts - request_baseline)
            hard_failure = not transport_any
            if not hard_failure:
                transport_successes += 1
            error_text = " / ".join(attempt_errors)
            with self._learning_lock:
                learned = self.learner.observe_search(
                    keyword, used_query, rows, error=error_text if hard_failure else "", family=family, region=region
                )
            for row in rows:
                enriched = dict(row)
                enriched["query_family"] = family
                enriched["query_region"] = region
                enriched["query_relaxed"] = relaxed
                enriched["query_minimal"] = minimal
                all_rows.append(enriched)
            if hard_failure and error_text:
                errors.append(f"{family}/{region}: {error_text}"[:900])
            query_results.append({
                "family": family,
                "region": region,
                "query": query,
                "effective_query": used_query,
                "relaxed": relaxed,
                "minimal": minimal,
                "result_count": len(rows),
                "provider_counts": dict(Counter(str(x.get("search_provider") or "unknown") for x in rows)),
                "method_counts": dict(Counter(str(x.get("search_method") or x.get("search_provider") or "unknown") for x in rows)),
                "transport_ok": not hard_failure,
                "empty": not rows and not hard_failure,
                "error": error_text if hard_failure else None,
                "provider_warnings": attempt_errors if not hard_failure else [],
                "learned": learned,
            })

        with self._learning_lock:
            ranked_pool = self.learner.rank_results(keyword, all_rows, limit=max(30, int(limit) * 4))
            final_rows = self._diversify_ranked(ranked_pool, limit)
            self.method_learner.observe_selected(final_rows)
            self.learner.save()
            self.method_learner.save()
        successful_queries = sum(1 for row in query_results if row["result_count"] > 0 and row["transport_ok"])
        empty_queries = sum(1 for row in query_results if row["empty"])
        provider_counts = dict(Counter(str(x.get("search_provider") or "unknown") for x in final_rows))
        provider_pool_counts = dict(Counter(str(x.get("search_provider") or "unknown") for x in ranked_pool))
        return {
            "ok": bool(transport_successes),
            "degraded": bool(errors or not final_rows),
            "empty": not bool(final_rows),
            "keyword": keyword,
            "results": final_rows,
            "provider_counts": provider_counts,
            "provider_pool_counts": provider_pool_counts,
            "provider_diversity": len([k for k, v in provider_counts.items() if v > 0]),
            "query_count": len(plans),
            "successful_query_count": successful_queries,
            "transport_successful_query_count": transport_successes,
            "empty_query_count": empty_queries,
            "query_results": query_results,
            "error": " / ".join(errors)[-1600:] if errors else "",
            "collection_errors": errors[:20],
            "retry_count": total_retries,
            "timeout_seconds": self._timeout(),
            "learning": {
                "memory_file": self.learner.memory_path.name,
                "method_memory_file": self.method_learner.memory_path.name,
                "engine_profile_file": "search_engine_profile.json",
                "strategy": "adaptive query + learned meta-search routing: cumulative response/yield/adoption/403/429/timeout/latency/failure metrics drive route order, timeout, attempt budget and recovery exploration",
                "search_method_health": self.method_learner.report(),
                "safety": "운영성공률만 학습. 403/429/timeout 경로는 임시 cooldown 후 재탐색하며 CAPTCHA/로그인/비공개 API 우회 금지",
            },
        }
