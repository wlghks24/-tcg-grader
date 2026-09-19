#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

import verified_public_search_url_repair_v217 as rule


class PublicSearchUrlAutoRepairV217Tests(unittest.TestCase):
    def test_healthy_current_markers_do_not_trigger(self):
        samples = {
            rule.MULTI_ROUTE_PATH: "\n".join(rule._MULTI_MARKERS) + "\ndef _bing_one():\n    pass\nhttps://www.bing.com/search?",
            rule.SOCIAL_EVENT_PATH: "\n".join(rule._SOCIAL_MARKERS) + "\ndef _google_news_url():\n    pass\nhttps://news.google.com/rss/search",
            rule.V144_PATH: "\n".join(rule._V144_MARKERS) + "\ndef _v144_ddg_social_one():\n    pass\nhttps://html.duckduckgo.com/html/",
        }
        for path, text in samples.items():
            with self.subTest(path=path):
                self.assertIsNone(rule.detect(path, text))

    def test_multi_route_regression_is_repaired_bounded(self):
        stale = '''import shlex\nimport urllib.parse\nDDG_HOSTS = {"html.duckduckgo.com", "duckduckgo.com", "www.duckduckgo.com"}\nREGION_LANG = {"KR": "ko"}\nGAMES = {"포켓몬 카드": {"ko": ("포켓몬 카드", "포켓몬")}}\nQUERY_FAMILIES = {"ko": {"event": "행사 이벤트 챌린지 도전 개최 대회"}}\ndef _query(game, region, *, scoped_hosts=(), topic=None, extra_terms=()):\n    return "x" * 3000\ndef _bing_one(game, region, route, hosts=(), topic=None, extra_terms=()):\n    q = _query(game, region, scoped_hosts=hosts, topic=topic, extra_terms=extra_terms)\n    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"format": "rss", "q": q})\n    return q, url\n'''
        diagnostic = rule.detect(rule.MULTI_ROUTE_PATH, stale)
        self.assertIsNotNone(diagnostic)
        fixed = rule.transform(rule.MULTI_ROUTE_PATH, stale)
        self.assertIn("def _bounded_bing_request(", fixed)
        self.assertIn("q, url = _bounded_bing_request(", fixed)
        self.assertIn("MAX_PUBLIC_SEARCH_URL_CHARS = 1900", fixed)
        self.assertIsNone(rule.detect(rule.MULTI_ROUTE_PATH, fixed))

    def test_google_news_regression_is_repaired_bounded(self):
        stale = '''import urllib.parse\nREGISTRY_TTL_HOURS = env_int("TCG_SOCIAL_REGISTRY_TTL_HOURS", 168, 6, 720)\nREGION_LANG = {"KR": {"lang": "ko", "hl": "ko", "gl": "KR", "ceid": "KR:ko"}}\nGAMES = {"포켓몬 카드": {"ko": ("포켓몬 카드", "포켓몬")}}\nEVENT_TERMS = {"ko": ("행사", "이벤트", "프로모")}\ndef _or_terms(values, limit):\n    return " OR ".join(values[:limit])\ndef _google_news_url(game: str, region: str) -> str:\n    cfg = REGION_LANG[region]; lang = cfg["lang"]; names = " OR ".join(f'"{x}"' for x in GAMES[game][lang][:2])\n    query = f"({names}) ({EVENT_TERMS[lang]}) when:45d"\n    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": cfg["hl"], "gl": cfg["gl"], "ceid": cfg["ceid"]})\ndef _parse_pubdate(value):\n    return value\n'''
        self.assertIsNotNone(rule.detect(rule.SOCIAL_EVENT_PATH, stale))
        fixed = rule.transform(rule.SOCIAL_EVENT_PATH, stale)
        self.assertIn("Google News query exceeds safe URL budget", fixed)
        self.assertIn("MAX_PUBLIC_SEARCH_URL_CHARS = 1900", fixed)
        self.assertIsNone(rule.detect(rule.SOCIAL_EVENT_PATH, fixed))

    def test_v144_regression_gets_fallback_guard(self):
        stale = '''import urllib.parse\nPATCH_ID = 144\ndef build_public_social_query(game, region, registry, fan_learner, gap_learner):\n    return "x" * 3000\ndef _v144_ddg_social_one(game: str, region: str, registry: dict, fan_learner=None):\n    gap_learner = event_gap_learning.EventGapLearner()\n    query = build_public_social_query(game, region, registry, fan_learner, gap_learner)\n    url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})\n    return url\n'''
        self.assertIsNotNone(rule.detect(rule.V144_PATH, stale))
        fixed = rule.transform(rule.V144_PATH, stale)
        self.assertIn("public social query exceeds safe URL budget", fixed)
        self.assertIn("MAX_PUBLIC_SEARCH_URL_CHARS = 1900", fixed)
        self.assertIsNone(rule.detect(rule.V144_PATH, fixed))

    def test_rule_is_exact_allowlist_and_fingerprint_stable(self):
        self.assertEqual(len(rule.RULE_PATHS), 3)
        self.assertEqual(rule.transform("other.py", "unchanged"), "unchanged")
        self.assertEqual(rule.fingerprint(), rule.fingerprint())
        payload = rule.fingerprint_payload()
        self.assertEqual(payload["limit"], 1900)
        self.assertEqual(set(payload["paths"]), set(rule.RULE_PATHS))


if __name__ == "__main__":
    unittest.main()
