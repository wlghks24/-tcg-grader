#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

import update_releases as releases


class PokemonReleaseParserRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.original_memory = releases.PARSER_MEMORY
        self.original_html = releases._collect_pokemon_jp_html
        self.original_api = releases._collect_pokemon_jp_api
        self.original_events = list(releases.PARSER_RUN_EVENTS)
        self.tmp = tempfile.TemporaryDirectory()
        releases.PARSER_MEMORY = Path(self.tmp.name) / "release_parser_learning.json"
        releases.PARSER_RUN_EVENTS.clear()

    def tearDown(self):
        releases.PARSER_MEMORY = self.original_memory
        releases._collect_pokemon_jp_html = self.original_html
        releases._collect_pokemon_jp_api = self.original_api
        releases.PARSER_RUN_EVENTS[:] = self.original_events
        self.tmp.cleanup()

    @staticmethod
    def _valid_payload():
        return {
            "result": 1,
            "hitCnt": 1,
            "maxPage": 1,
            "thisPage": 1,
            "products": [
                {
                    "productType": "拡張パック",
                    "productTitle": "拡張パック「30th CELEBRATION」",
                    "releaseDate": "2026年9月16日",
                    "priceTxt": "1パック 360円（税込）",
                }
            ],
        }

    def test_official_api_payload_is_strictly_validated_and_normalized(self):
        rows = releases._parse_pokemon_jp_api_payload(
            self._valid_payload(),
            transport_url="https://www.pokemon-card.com/products/resultAPI.php?productType=expansion&page=1",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "30th CELEBRATION")
        self.assertEqual(rows[0]["release_date"], "2026-09-16")
        self.assertEqual(rows[0]["price"], "¥360/팩")
        self.assertEqual(rows[0]["parser"], "official-result-api-v1")
        self.assertTrue(rows[0]["source"].startswith("https://www.pokemon-card.com/"))

        malformed = dict(self._valid_payload())
        malformed["result"] = 0
        with self.assertRaises(ValueError):
            releases._parse_pokemon_jp_api_payload(malformed, transport_url="https://www.pokemon-card.com/products/resultAPI.php")

        malformed = dict(self._valid_payload())
        malformed["products"] = "not-a-list"
        with self.assertRaises(ValueError):
            releases._parse_pokemon_jp_api_payload(malformed, transport_url="https://www.pokemon-card.com/products/resultAPI.php")

    def test_zero_html_then_verified_api_success_is_learned(self):
        calls = []
        api_rows = releases._parse_pokemon_jp_api_payload(
            self._valid_payload(),
            transport_url="https://www.pokemon-card.com/products/resultAPI.php?productType=expansion&page=1",
        )

        def fake_html():
            calls.append("html_chain_v1")
            return [], "htmlfingerprint123"

        def fake_api():
            calls.append("official_result_api_v1")
            return api_rows, "apifingerprint1234"

        releases._collect_pokemon_jp_html = fake_html
        releases._collect_pokemon_jp_api = fake_api

        first = releases.collect_pokemon_jp()
        self.assertEqual(first, api_rows)
        self.assertEqual(calls, ["html_chain_v1", "official_result_api_v1"])
        self.assertEqual(
            [event["outcome"] for event in releases.PARSER_RUN_EVENTS],
            ["zero_verified_rows", "recovered"],
        )

        summary = releases.parser_public_summary(
            releases.PARSER_MEMORY,
            {"Pokémon JP": releases.POKEMON_JP_STRATEGIES},
        )
        learned = summary["sources"]["Pokémon JP"]
        self.assertEqual(learned["preferred_strategy"], "official_result_api_v1")
        self.assertEqual(learned["last_row_count"], 1)
        self.assertEqual(learned["consecutive_failures"], 0)

        calls.clear()
        releases.PARSER_RUN_EVENTS.clear()
        second = releases.collect_pokemon_jp()
        self.assertEqual(second, api_rows)
        self.assertEqual(calls, ["official_result_api_v1"])
        self.assertEqual(releases.PARSER_RUN_EVENTS[0]["outcome"], "success")

    def test_all_verified_strategies_zero_keeps_collection_unverified(self):
        releases._collect_pokemon_jp_html = lambda: ([], "htmlfingerprint123")
        releases._collect_pokemon_jp_api = lambda: ([], "apifingerprint1234")
        rows = releases.collect_pokemon_jp()
        self.assertEqual(rows, [])
        self.assertEqual(len(releases.PARSER_RUN_EVENTS), 2)
        self.assertTrue(all(event["rows"] == 0 for event in releases.PARSER_RUN_EVENTS))
        self.assertTrue(all(event["outcome"] == "zero_verified_rows" for event in releases.PARSER_RUN_EVENTS))


if __name__ == "__main__":
    unittest.main()
