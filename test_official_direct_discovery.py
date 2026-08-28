#!/usr/bin/env python3
from __future__ import annotations

import unittest

import official_direct_discovery
from auto_pipeline_runner import _diverse_ranked


class OfficialDirectDiscoveryTests(unittest.TestCase):
    def test_parser_keeps_relevant_official_links_and_rejects_external(self):
        html = '''
        <html><body>
          <a href="/en/news/new-promo-card.php">New promo card event</a>
          <a href="/en/about/">About us</a>
          <a href="https://example.com/news/fake">External event</a>
        </body></html>
        '''
        rows = official_direct_discovery.parse_official_links(
            "나루토", "US", "https://www.naruto-cardgame.com/en/", html, limit=10
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["search_provider"], "official_direct")
        self.assertTrue(rows[0]["official_hint"])
        self.assertTrue(rows[0]["url"].startswith("https://www.naruto-cardgame.com/"))

    def test_parser_accepts_news_path_even_with_short_anchor(self):
        html = '<a href="/news/2026/important.php">Details</a>'
        rows = official_direct_discovery.parse_official_links(
            "나루토", "JP", "https://naruto-official.com/", html, limit=10
        )
        self.assertEqual(len(rows), 1)
        self.assertIn("/news/", rows[0]["url"])

    def test_final_diversity_keeps_official_direct_when_available(self):
        rows = [
            {"title": "Official", "url": "https://www.naruto-cardgame.com/en/news/a", "search_provider": "official_direct"},
        ] + [
            {"title": f"Bing {i}", "url": f"https://example.com/b{i}", "search_provider": "bing_rss"}
            for i in range(10)
        ]
        selected = _diverse_ranked(rows, limit=8)
        providers = [x["search_provider"] for x in selected]
        self.assertIn("official_direct", providers)
        self.assertEqual(len(selected), 8)


if __name__ == "__main__":
    unittest.main()
