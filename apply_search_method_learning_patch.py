#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise RuntimeError(f"patch anchor not found: {label}")
    return text.replace(old, new, 1)


def patch_multi_channel() -> None:
    path = ROOT / "multi_channel_agent.py"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "from safe_runtime import env_int, safe_urlopen\n",
        "from safe_runtime import env_int, safe_urlopen\nfrom search_method_learning import SearchMethodLearner\n",
        "search method import",
    )

    text = text.replace('    PROVIDER_COUNT = 3\n', '    PROVIDER_COUNT = 7\n', 1)
    if 'NAVER_HOSTS' not in text:
        text = text.replace(
            '    GOOGLE_NEWS_HOSTS = {"news.google.com"}\n',
            '    GOOGLE_NEWS_HOSTS = {"news.google.com"}\n'
            '    NAVER_HOSTS = {"search.naver.com", "m.search.naver.com"}\n',
            1,
        )

    text = replace_once(
        text,
        "        self.learner = learner or AdaptiveCollectionLearner()\n        self._learning_lock = threading.RLock()\n",
        "        self.learner = learner or AdaptiveCollectionLearner()\n"
        "        self.method_learner = SearchMethodLearner()\n"
        "        self.method_learner.start_run()\n"
        "        self._learning_lock = threading.RLock()\n",
        "method learner init",
    )

    insert_marker = "    def _search_once(self, query: str, limit: int, region: str = \"KR\") -> tuple[list[dict], list[str], int]:\n"
    if insert_marker not in text:
        raise RuntimeError("patch anchor not found: _search_once")

    methods = r'''    def _search_ddg_html_only(self, query: str, limit: int) -> tuple[list[dict], str | None, int, bool]:
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

'''
    if "def _search_bing_news_rss" not in text:
        text = text.replace(insert_marker, methods + insert_marker, 1)

    start = text.index('    def _search_once(self, query: str, limit: int, region: str = "KR")')
    end = text.index('    def _relaxed_query(', start)
    new_search_once = r'''    def _search_once(self, query: str, limit: int, region: str = "KR", family: str = "web") -> tuple[list[dict], list[str], int, bool, int]:
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
        budget = 5 if is_android else len(routes)
        with self._learning_lock:
            ordered = self.method_learner.ordered_routes(routes.keys(), region=region, family=family, budget=budget)
        errors: list[str] = []
        attempts = 0
        provider_rows: dict[str, list[dict]] = {}
        responded_any = False
        for method in ordered:
            fn = routes[method]
            started = time.monotonic()
            try:
                rows, error, used_attempts, responded = fn(query, max(limit, 8))
            except Exception as exc:
                rows, error, used_attempts, responded = [], f"{type(exc).__name__}: {exc}"[:500], 1, False
            elapsed_ms = (time.monotonic() - started) * 1000.0
            attempts += max(1, int(used_attempts or 1))
            responded_any = responded_any or responded
            for row in rows:
                row.setdefault("search_method", method)
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

'''
    text = text[:start] + new_search_once + text[end:]

    loop_start = text.index("        for plan in plans:\n")
    loop_end = text.index("\n        with self._learning_lock:\n", loop_start)
    new_loop = r'''        for plan in plans:
            query = str(plan.get("query") or "")
            family = str(plan.get("family") or "web")
            region = str(plan.get("region") or "KR")
            rows, attempt_errors, attempts, route_hard, route_count = self._search_once(query, max(limit, 8), region, family)
            used_query = query
            relaxed = False
            minimal = False
            transport_any = not route_hard
            request_baseline = route_count

            if not rows and transport_any:
                relaxed_query = self._relaxed_query(keyword, region, family, query)
                if relaxed_query and relaxed_query != query:
                    relaxed_rows, relaxed_errors, relaxed_attempts, relaxed_hard, relaxed_count = self._search_once(
                        relaxed_query, max(limit, 8), region, family + ":relaxed"
                    )
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
                    minimal_rows, minimal_errors, minimal_attempts, minimal_hard, minimal_count = self._search_once(
                        minimal_query, max(limit, 8), region, family + ":minimal"
                    )
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
'''
    text = text[:loop_start] + new_loop + text[loop_end:]

    old_final = '''        with self._learning_lock:\n            ranked_pool = self.learner.rank_results(keyword, all_rows, limit=max(30, int(limit) * 4))\n            final_rows = self._diversify_ranked(ranked_pool, limit)\n            self.learner.save()'''
    new_final = '''        with self._learning_lock:\n            ranked_pool = self.learner.rank_results(keyword, all_rows, limit=max(30, int(limit) * 4))\n            final_rows = self._diversify_ranked(ranked_pool, limit)\n            self.method_learner.observe_selected(final_rows)\n            self.learner.save()\n            self.method_learner.save()'''
    text = replace_once(text, old_final, new_final, "save method learning")

    old_learning = '''            "learning": {\n                "memory_file": self.learner.memory_path.name,\n                "strategy": "adaptive KR/JP/US + DDG HTML/Lite + Bing RSS + regional Google News RSS + double diversity merge + compact OR fallback",\n            },'''
    new_learning = '''            "learning": {\n                "memory_file": self.learner.memory_path.name,\n                "method_memory_file": self.method_learner.memory_path.name,\n                "strategy": "adaptive query + adaptive method routing: DDG HTML/Lite, Bing Web/News RSS, Google News compact/broad, Naver News + relaxed/minimal fallback",\n                "search_method_health": self.method_learner.report(),\n                "safety": "운영성공률만 학습. 403/429/timeout 경로는 임시 cooldown 후 재탐색하며 CAPTCHA/로그인/비공개 API 우회 금지",\n            },'''
    text = replace_once(text, old_learning, new_learning, "learning payload")

    text = text.replace("v115:", "v118:", 1)
    path.write_text(text, encoding="utf-8")


def patch_gitignore() -> None:
    path = ROOT / ".gitignore"
    text = path.read_text(encoding="utf-8")
    block = "\n# Adaptive public-search method health is device-local runtime state.\nsearch_method_learning.json\nsearch_method_learning.json.bak\n"
    if "search_method_learning.json" not in text:
        text = text.rstrip() + "\n" + block
    path.write_text(text, encoding="utf-8")


def write_tests() -> None:
    path = ROOT / "test_search_method_learning.py"
    path.write_text('''import datetime as dt\nimport tempfile\nimport unittest\nfrom pathlib import Path\n\nfrom search_method_learning import SearchMethodLearner, classify_error\n\n\nclass SearchMethodLearningTests(unittest.TestCase):\n    def make_learner(self):\n        td = tempfile.TemporaryDirectory()\n        root = Path(td.name)\n        learner = SearchMethodLearner(root / "memory.json", root / "memory.bak")\n        learner._test_tmp = td\n        learner.start_run()\n        return learner\n\n    def test_error_classification(self):\n        self.assertEqual(classify_error("HTTP Error 429"), "rate_limited")\n        self.assertEqual(classify_error("HTTP Error 403 Forbidden"), "blocked")\n        self.assertEqual(classify_error("TimeoutError timed out"), "timeout")\n\n    def test_blocked_route_cools_down_without_blacklist(self):\n        learner = self.make_learner()\n        learner.observe("ddg_html", responded=False, result_count=0, error="HTTP Error 403 Forbidden", elapsed_ms=100)\n        report = learner.report()\n        row = next(x for x in report["methods"] if x["method"] == "ddg_html")\n        self.assertTrue(row["cooling_down"])\n        ordered = learner.ordered_routes(["ddg_html", "bing_web_rss"], budget=2)\n        self.assertIn("bing_web_rss", ordered)\n        # Recovery is possible: a successful observation clears cooldown.\n        learner.observe("ddg_html", responded=True, result_count=2, error="", elapsed_ms=80)\n        row = next(x for x in learner.report()["methods"] if x["method"] == "ddg_html")\n        self.assertFalse(row["cooling_down"])\n\n    def test_fast_useful_route_ranks_above_repeated_timeout(self):\n        learner = self.make_learner()\n        for _ in range(4):\n            learner.observe("bing_news_rss", responded=True, result_count=5, elapsed_ms=120)\n            learner.observe("naver_news_html", responded=False, result_count=0, error="TimeoutError timed out", elapsed_ms=20000)\n        order = learner.ordered_routes(["naver_news_html", "bing_news_rss"], budget=2)\n        self.assertEqual(order[0], "bing_news_rss")\n\n    def test_selection_is_learned_separately_from_trust(self):\n        learner = self.make_learner()\n        learner.observe("google_news_rss", responded=True, result_count=4, elapsed_ms=100)\n        learner.observe_selected([{\"search_method\": \"google_news_rss\", \"verified\": False}])\n        row = next(x for x in learner.report()["methods"] if x["method"] == "google_news_rss")\n        self.assertEqual(row["selected"], 1)\n        self.assertNotIn("verified", row)\n\n\nif __name__ == "__main__":\n    unittest.main()\n''', encoding="utf-8")


def main() -> None:
    patch_multi_channel()
    patch_gitignore()
    write_tests()
    print("adaptive search method routing patch applied")


if __name__ == "__main__":
    main()
