#!/usr/bin/env python3
from __future__ import annotations

import unittest

import collection_meta_learning as meta


class CollectionRegionProvenanceV16Tests(unittest.TestCase):
    def test_query_region_wins_over_generic_com_url(self):
        self.assertEqual(
            meta._region({
                "query_region": "JP",
                "url": "https://www.pokemon-card.com/info/",
            }),
            "JP",
        )

    def test_target_region_and_market_region_are_preserved(self):
        self.assertEqual(
            meta._region({
                "target_region": "US",
                "url": "https://example.com/card",
            }),
            "US",
        )
        self.assertEqual(
            meta._region({
                "market_region": "KR",
                "url": "https://example.com/card",
            }),
            "KR",
        )

    def test_generic_dot_com_is_not_automatically_us(self):
        self.assertEqual(
            meta._region({"url": "https://example.com/card"}),
            "KR",
        )

    def test_known_japanese_dot_com_official_host_infers_jp(self):
        self.assertEqual(
            meta._region({"url": "https://www.onepiece-cardgame.com/products/"}),
            "JP",
        )
        self.assertEqual(
            meta._region({"url": "https://www.pokemon-card.com/products/"}),
            "JP",
        )

    def test_known_english_onepiece_host_infers_us(self):
        self.assertEqual(
            meta._region({"url": "https://en.onepiece-cardgame.com/events/"}),
            "US",
        )


if __name__ == "__main__":
    unittest.main()
