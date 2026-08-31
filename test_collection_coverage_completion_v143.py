from __future__ import annotations

import unittest

import collection_meta_learning as meta
import official_direct_discovery as direct
from auto_pipeline_runner import _diverse_ranked


class CollectionCoverageCompletionV143Tests(unittest.TestCase):
    def test_rare_merch_and_anniversary_topics_are_not_folded_into_event(self):
        self.assertEqual(
            meta.classify_topic({"title": "JUMP SHOP 공식 굿즈 한정판매"}),
            "merch",
        )
        self.assertEqual(
            meta.classify_topic({"title": "포켓몬 카드게임 30주년 기념 행사"}),
            "anniversary",
        )
        self.assertEqual(
            meta.classify_topic({"title": "4th Anniversary release event promo"}),
            "anniversary",
        )

    def test_direct_source_matrix_includes_specialized_official_indexes(self):
        pokemon_jp = direct.OFFICIAL_ENTRY_PAGES["포켓몬"]["JP"]
        onepiece_kr = direct.OFFICIAL_ENTRY_PAGES["원피스"]["KR"]
        onepiece_us = direct.OFFICIAL_ENTRY_PAGES["원피스"]["US"]
        self.assertIn("https://www.30th.pokemon-card.com/", pokemon_jp)
        self.assertIn("https://onepiece-cardgame.kr/topics.do", onepiece_kr)
        self.assertIn("https://onepiece-cardgame.kr/events.do", onepiece_kr)
        self.assertIn("https://onepiece-cardgame.kr/products.do", onepiece_kr)
        self.assertIn("https://en.onepiece-cardgame.com/events/", onepiece_us)
        self.assertIn("https://en.onepiece-cardgame.com/products/", onepiece_us)

    def test_direct_parser_keeps_merch_and_anniversary_but_never_auto_verifies(self):
        html = (
            '<a href="/special/30th/">30th anniversary commemorative merchandise</a>'
            '<a href="https://evil.example/special/promo">Official promo</a>'
        )
        rows = direct.parse_official_links(
            "포켓몬", "JP", "https://www.pokemon-card.com/", html, limit=8
        )
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["official_hint"])
        self.assertFalse(rows[0]["verified"])

    def test_region_balancer_prevents_first_region_starvation(self):
        rows = [
            {"url": f"https://example.com/kr/{i}", "query_region": "KR"}
            for i in range(10)
        ] + [
            {"url": "https://example.com/jp/1", "query_region": "JP"},
            {"url": "https://example.com/us/1", "query_region": "US"},
        ]
        selected = direct.balance_regions(rows, 5)
        self.assertEqual({row["query_region"] for row in selected}, {"KR", "JP", "US"})

    def test_final_provider_selection_rotates_regions(self):
        rows = [
            {
                "title": f"KR {i}", "url": f"https://example.com/kr/{i}",
                "query_region": "KR", "search_provider": "official_direct",
            }
            for i in range(8)
        ] + [
            {
                "title": "JP", "url": "https://example.com/jp/1",
                "query_region": "JP", "search_provider": "official_direct",
            },
            {
                "title": "US", "url": "https://example.com/us/1",
                "query_region": "US", "search_provider": "official_direct",
            },
        ]
        selected = _diverse_ranked(rows, limit=5)
        self.assertEqual({row["query_region"] for row in selected}, {"KR", "JP", "US"})


if __name__ == "__main__":
    unittest.main()
