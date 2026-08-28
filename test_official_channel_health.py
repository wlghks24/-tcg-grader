from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import official_channel_feed_discovery as channel
import official_sitemap_discovery as sitemap
import provider_health_learning as health
from auto_pipeline_runner import _diverse_ranked


class OfficialChannelAndHealthTests(unittest.TestCase):
    def test_youtube_atom_feed_parses_official_candidates(self):
        raw = b'''<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <title>NARUTO CARD GAME Tournament Promo Card Event</title>
            <link rel="alternate" href="https://www.youtube.com/watch?v=abc123"/>
            <published>2026-08-29T00:00:00+00:00</published>
          </entry>
        </feed>'''
        account = {"username": "@NARUTO_TCG_EN", "profile_url": "https://www.youtube.com/@NARUTO_TCG_EN"}
        rows = channel.parse_youtube_feed(raw, game="나루토", region="US", account=account, limit=6)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["search_provider"], "official_youtube_feed")
        self.assertTrue(rows[0]["official_account_verified"])
        self.assertTrue(rows[0]["event_hint"])

    def test_sitemap_parser_and_relevance_filter(self):
        root = ET.fromstring('''<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://www.naruto-cardgame.com/en/news/test.php</loc><lastmod>2026-08-28</lastmod></url>
          <url><loc>https://www.naruto-cardgame.com/en/privacy/</loc></url>
        </urlset>''')
        locs = sitemap._xml_locs(root)
        self.assertEqual(len(locs), 2)
        self.assertTrue(sitemap._looks_relevant(locs[0][0]))
        self.assertFalse(sitemap._looks_relevant(locs[1][0]))

    def test_provider_health_persists_without_affecting_trust(self):
        with tempfile.TemporaryDirectory() as td:
            memory = Path(td) / "health.json"
            report1 = health.observe([
                {"provider": "google_news", "responded": True, "results": 8, "selected": 4, "errors": 0},
                {"provider": "duckduckgo", "responded": False, "results": 0, "selected": 0, "errors": 1},
            ], memory_path=memory)
            self.assertEqual(report1["runs"], 1)
            report2 = health.observe([
                {"provider": "google_news", "responded": True, "results": 6, "selected": 3, "errors": 0},
            ], memory_path=memory)
            self.assertEqual(report2["runs"], 2)
            rows = {x["provider"]: x for x in report2["providers"]}
            self.assertGreater(rows["google_news"]["score"], rows["duckduckgo"]["score"])
            self.assertTrue(memory.exists())
            self.assertTrue(memory.with_suffix(".json.bak").exists())

    def test_final_diversity_keeps_official_channel_and_search(self):
        rows = [
            {"title": "YT official", "url": "https://www.youtube.com/watch?v=1", "search_provider": "official_youtube_feed"},
            {"title": "Sitemap", "url": "https://www.naruto-cardgame.com/en/news/1", "search_provider": "official_sitemap"},
        ] + [
            {"title": f"Bing {i}", "url": f"https://example.com/{i}", "search_provider": "bing_rss"}
            for i in range(10)
        ]
        selected = _diverse_ranked(rows, limit=8)
        providers = {x["search_provider"] for x in selected}
        self.assertIn("official_youtube_feed", providers)
        self.assertIn("official_sitemap", providers)
        self.assertIn("bing_rss", providers)


if __name__ == "__main__":
    unittest.main()
