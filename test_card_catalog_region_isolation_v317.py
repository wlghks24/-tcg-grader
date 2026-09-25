from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity


class CardCatalogRegionIsolationV317Tests(unittest.TestCase):
    def setUp(self) -> None:
        identity._CATALOG_CACHE_SIGNATURE = None
        identity._CATALOG_CACHE_ROWS = []

    def tearDown(self) -> None:
        identity._CATALOG_CACHE_SIGNATURE = None
        identity._CATALOG_CACHE_ROWS = []

    def test_same_name_and_number_in_different_editions_are_all_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            market = root / "market.json"
            reference = root / "reference.json"
            market.write_text(json.dumps({
                "entries": {
                    "JP|Pikachu|HIT": {
                        "game": "pokemon",
                        "card_name": "Pikachu",
                        "card_number": "025",
                    }
                }
            }), encoding="utf-8")
            reference.write_text(json.dumps({
                "cards": [
                    {
                        "game": "pokemon",
                        "region": "KR",
                        "card_name": "Pikachu",
                        "card_number": "025",
                        "aliases": ["피카츄"],
                    },
                    {
                        "game": "pokemon",
                        "region": "US",
                        "card_name": "Pikachu",
                        "card_number": "025",
                        "aliases": ["Pikachu"],
                    },
                ]
            }), encoding="utf-8")
            with mock.patch.object(identity, "MARKET", market), mock.patch.object(identity, "REFERENCE", reference):
                rows = identity.catalog()

            matches = {
                (row["region"], row["card_name"], row["card_number"])
                for row in rows
                if row["game"] == "pokemon" and row["card_name"] == "Pikachu" and row["card_number"] == "025"
            }
            self.assertEqual({
                ("JP", "Pikachu", "025"),
                ("KR", "Pikachu", "025"),
                ("US", "Pikachu", "025"),
            }, matches)

    def test_region_filtered_learning_does_not_cross_editions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "learning.json"
            store.write_text(json.dumps({
                "version": 1,
                "confirmed": [
                    {"image_hash": "0000000000000001", "game": "pokemon", "card_name": "Pikachu", "card_number": "025", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000002", "game": "pokemon", "card_name": "Pikachu", "card_number": "025", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000004", "game": "pokemon", "card_name": "Pikachu", "card_number": "025", "market_key": "", "region": "JP"},
                ],
                "conflicts": [],
            }), encoding="utf-8")
            with mock.patch.object(identity, "LEARNING", store):
                self.assertEqual([], identity.match_learning("0000000000000000", "pokemon", "KR"))
                self.assertTrue(identity.match_learning("0000000000000000", "pokemon", "JP"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
