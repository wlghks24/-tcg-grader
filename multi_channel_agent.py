#!/usr/bin/env python3
"""공개 웹 검색 결과를 참고 후보로만 저장하는 보조 수집기.

v62:
- 바깥 학습 엔진의 TCG_HTTP_TIMEOUT과 연동해 고정 8초 조기실패를 제거한다.
- 일시 네트워크 오류는 같은 호출 안에서 1회 짧게 재시도한다.
- 실패를 결과에 명시해 상위 파이프라인이 clean success로 잘못 학습하지 않게 한다.
"""
from __future__ import annotations
import html
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from safe_runtime import env_int, safe_urlopen


class MultiChannelCollector:
    SEARCH = "https://html.duckduckgo.com/html/?q="
    HEADERS = {"User-Agent": "Mozilla/5.0 TCG-Grader/75"}

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

    def search_web(self, keyword, limit=5):
        keyword = str(keyword or "").strip()[:80]
        query = urllib.parse.quote_plus(f"{keyword} 카드 프로모 콜라보 이벤트")
        req = urllib.request.Request(self.SEARCH + query, headers=self.HEADERS)
        raw = None
        errors = []
        timeout = self._timeout()
        for attempt in range(2):
            try:
                with safe_urlopen(req, timeout=timeout, allowed_hosts={'html.duckduckgo.com','duckduckgo.com'}) as response:
                    raw = response.read(600_000).decode("utf-8", "replace")
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                if attempt >= 1 or not self._transient(exc):
                    break
                time.sleep(1.0)
        if raw is None:
            return {"ok": False, "keyword": keyword, "results": [], "error": " / ".join(errors)[-1200:],
                    "retry_count": max(0, len(errors)-1), "timeout_seconds": timeout}
        rows = []
        for href, title in re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.I | re.S):
            clean_title = re.sub(r"<[^>]+>", " ", html.unescape(title))
            clean_title = re.sub(r"\s+", " ", clean_title).strip()
            rows.append({"title": clean_title, "url": html.unescape(href), "verified": False})
            if len(rows) >= limit:
                break
        return {"ok": True, "keyword": keyword, "results": rows, "retry_count": max(0, len(errors)),
                "timeout_seconds": timeout}
