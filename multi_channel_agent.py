#!/usr/bin/env python3
"""Adaptive public-web candidate collector.

v112:
- KR/JP/US, official domains, X, Instagram and YouTube are searched through a
  rotating query plan instead of one fixed Korean query.
- Successful query families, useful terms and source hosts are learned by
  adaptive_collection_learner.py.
- Low-use query concepts keep an exploration budget so historical success does
  not create a blind spot.
- Network failures are learned separately from relevance; official trust is
  never inferred merely from repeated discovery.
"""
from __future__ import annotations

import html
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from adaptive_collection_learner import AdaptiveCollectionLearner
from safe_runtime import env_int, safe_urlopen


class MultiChannelCollector:
    SEARCH = "https://html.duckduckgo.com/html/?q="
    HEADERS = {"User-Agent": "Mozilla/5.0 TCG-Grader/112"}
    ALLOWED_SEARCH_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}

    def __init__(self, learner: AdaptiveCollectionLearner | None = None):
        self.learner = learner or AdaptiveCollectionLearner()

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
        if host in MultiChannelCollector.ALLOWED_SEARCH_HOSTS:
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
            if target:
                value = urllib.parse.unquote(target)
        return value if value.startswith("https://") else ""

    def _search_once(self, query: str, limit: int) -> tuple[list[dict], list[str], int]:
        query = re.sub(r"\s+", " ", str(query or "")).strip()[:280]
        req = urllib.request.Request(self.SEARCH + urllib.parse.quote_plus(query), headers=self.HEADERS)
        raw = None
        errors: list[str] = []
        timeout = self._timeout()
        attempts = 0
        for attempt in range(2):
            attempts = attempt + 1
            try:
                with safe_urlopen(req, timeout=timeout, allowed_hosts=self.ALLOWED_SEARCH_HOSTS) as response:
                    raw = response.read(700_000).decode("utf-8", "replace")
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                errors.append(f"{type(exc).__name__}: {exc}"[:500])
                if attempt >= 1 or not self._transient(exc):
                    break
                time.sleep(1.0)
        if raw is None:
            return [], errors, attempts

        rows: list[dict] = []
        for href, title in re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S):
            clean_title = re.sub(r"<[^>]+>", " ", html.unescape(title))
            clean_title = re.sub(r"\s+", " ", clean_title).strip()[:240]
            target = self._decode_result_url(href)
            if not clean_title or not target:
                continue
            rows.append({"title": clean_title, "url": target, "verified": False})
            if len(rows) >= max(3, min(30, limit)):
                break
        return rows, errors, attempts

    def search_web(self, keyword, limit=8):
        keyword = str(keyword or "").strip()[:80]
        is_android = "com.termux" in os.environ.get("PREFIX", "") or "ANDROID_ROOT" in os.environ
        query_budget = 5 if is_android else 8
        plans = self.learner.plan_queries(keyword, max_queries=query_budget)
        all_rows: list[dict] = []
        errors: list[str] = []
        query_results: list[dict] = []
        total_retries = 0

        for plan in plans:
            query = str(plan.get("query") or "")
            family = str(plan.get("family") or "web")
            region = str(plan.get("region") or "KR")
            rows, attempt_errors, attempts = self._search_once(query, max(limit, 8))
            total_retries += max(0, attempts - 1)
            error_text = " / ".join(attempt_errors)
            learned = self.learner.observe_search(
                keyword, query, rows, error=error_text, family=family, region=region
            )
            for row in rows:
                enriched = dict(row)
                enriched["query_family"] = family
                enriched["query_region"] = region
                all_rows.append(enriched)
            if attempt_errors:
                errors.append(f"{family}/{region}: {error_text}"[:700])
            query_results.append({
                "family": family,
                "region": region,
                "query": query,
                "result_count": len(rows),
                "error": error_text or None,
                "learned": learned,
            })

        ranked = self.learner.rank_results(keyword, all_rows, limit=max(limit, 12))
        self.learner.save()
        successful_queries = sum(1 for row in query_results if row["result_count"] > 0 and not row["error"])
        return {
            "ok": bool(successful_queries or ranked),
            "degraded": bool(errors),
            "keyword": keyword,
            "results": ranked[: max(1, min(30, int(limit)))],
            "query_count": len(plans),
            "successful_query_count": successful_queries,
            "query_results": query_results,
            "error": " / ".join(errors)[-1600:] if errors and not ranked else "",
            "collection_errors": errors[:20],
            "retry_count": total_retries,
            "timeout_seconds": self._timeout(),
            "learning": {
                "memory_file": self.learner.memory_path.name,
                "strategy": "regional + official + X/Instagram/YouTube + learned terms/hosts + exploration rotation",
            },
        }
