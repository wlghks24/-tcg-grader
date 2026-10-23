import unittest
from pathlib import Path

import update_market_prices as market


class PackMagikMarketParserV353Tests(unittest.TestCase):
    def test_market_value_label(self):
        self.assertEqual(market.packmagik_market_value("Market Value $11.49"), "11.49")

    def test_legacy_market_label(self):
        self.assertEqual(market.packmagik_market_value("Market $17.15"), "17.15")

    def test_does_not_capture_graded_price_without_market_label(self):
        self.assertIsNone(market.packmagik_market_value("PSA 10 $63.20"))

    def test_source_is_japanese_scoped_and_old_kr_merge_is_removed(self):
        source = Path("update_market_prices.py").read_text(encoding="utf-8")
        self.assertIn("https://www.packmagik.com/cards/1767522330718x781330136463076700", source)
        self.assertIn("JP|창해의 칠걸 일본판 OP14-009|HIT", source)
        self.assertIn("'card_number':'OP14-009'", source)
        self.assertIn("'language':'JP'", source)
        self.assertIn("'variant':'alternate_art'", source)
        self.assertNotIn("https://www.packmagik.com/cards/op-op14-op14-009-p1", source)
        self.assertNotIn("set_price(db,'KR|창해의 칠걸|HIT'", source)


if __name__ == "__main__":
    unittest.main()
