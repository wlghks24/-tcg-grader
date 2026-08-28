#!/usr/bin/env python3
"""Adaptive multi-provider public-web candidate collector.

v115:
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


class MultiChannelCollector:
    HEADERS = {"User-Agent": "Mozilla/5.0 TCG-Grader/115"}
    DDG_HOSTS = {
        "html.duckduckgo.com", "lite.duckduckgo.com",
        "duckduckgo.com", "www.duckduckgo.com",
    }
    BING_HOSTS = {"www.bing.com", "bing.com"}
    GOOGLE_NEWS_HOSTS = {"news.google.com"}
    PROVIDER_COUNT = 3

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
        self._learning_lock = threading.RLock()

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
        order = ("duckduckgo", "bing_rss", "google_news")
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
        preferred_order = ("duckduckgo", "google_news", "bing_rss")
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
        for attempt in range(2):
            attempts = attempt + 1
            try:
                with safe_urlopen(req, timeout=self._timeout(), allowed_hosts=allowed_hosts) as response:
                    return response.read(max_bytes), None, attempts
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"[:500]
                if attempt >= 1 or not self._transient(exc):
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

    def _search_once(self, query: str, limit: int, region: str = "KR") -> tuple[list[dict], list[str], int]:
        """Run every independent provider and fairly merge results."""
        query = re.sub(r"\s+", " ", str(query or "")).strip()[:280]
        errors: list[str] = []
        attempts = 0
        provider_rows: dict[str, list[dict]] = {}
        successful_provider = False
        providers = (
            ("duckduckgo", lambda q, n: self._search_ddg(q, n)),
            ("bing_rss", lambda q, n: self._search_bing_rss(q, n)),
            ("google_news", lambda q, n: self._search_google_news(q, n, region)),
        )
        for provider, fn in providers:
            rows, error, used_attempts, responded = fn(query, max(limit, 8))
            attempts += used_attempts
            successful_provider = successful_provider or responded
            provider_rows[provider] = rows
            if error:
                errors.append(f"{provider}: {error}"[:600])
        merged = self._round_robin_merge(provider_rows, limit)
        if successful_provider and not merged:
            errors = [x for x in errors if x]
        return merged, errors, attempts

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
            rows, attempt_errors, attempts = self._search_once(query, max(limit, 8), region)
            used_query = query
            relaxed = False
            if not rows and len(attempt_errors) < self.PROVIDER_COUNT:
                relaxed_query = self._relaxed_query(keyword, region, family, query)
                if relaxed_query and relaxed_query != query:
                    relaxed_rows, relaxed_errors, relaxed_attempts = self._search_once(relaxed_query, max(limit, 8), region)
                    attempts += relaxed_attempts
                    attempt_errors.extend(relaxed_errors)
                    if relaxed_rows:
                        rows = relaxed_rows
                        used_query = relaxed_query
                        relaxed = True
            total_retries += max(0, attempts - self.PROVIDER_COUNT)
            hard_failure = not rows and len(attempt_errors) >= self.PROVIDER_COUNT * (2 if relaxed else 1)
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
                all_rows.append(enriched)
            if hard_failure and error_text:
                errors.append(f"{family}/{region}: {error_text}"[:900])
            query_results.append({
                "family": family,
                "region": region,
                "query": query,
                "effective_query": used_query,
                "relaxed": relaxed,
                "result_count": len(rows),
                "provider_counts": dict(Counter(str(x.get("search_provider") or "unknown") for x in rows)),
                "transport_ok": not hard_failure,
                "empty": not rows and not hard_failure,
                "error": error_text if hard_failure else None,
                "provider_warnings": attempt_errors if not hard_failure else [],
                "learned": learned,
            })

        with self._learning_lock:
            ranked_pool = self.learner.rank_results(keyword, all_rows, limit=max(30, int(limit) * 4))
            final_rows = self._diversify_ranked(ranked_pool, limit)
            self.learner.save()
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
                "strategy": "adaptive KR/JP/US + DDG HTML/Lite + Bing RSS + regional Google News RSS + double diversity merge + compact OR fallback",
            },
        }
