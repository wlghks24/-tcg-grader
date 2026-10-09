#!/usr/bin/env python3
"""V558: reject substring identifier collisions without hiding exact matches."""
import unittest

import market_public_crosscheck as market


class ExactIdentifierBoundariesV558(unittest.TestCase):
    def setUp(self):
        self.card = {"key": "KR|인페르노X|HIT", "card_name": "리자몽 ex",
                     "name": "리자몽 ex", "card_number": "116/080"}
        self.box = {"key": "JP|Box|BOX", "name": "Booster Box",
                    "card_number": "", "product_code": "BOX-XYZ"}

    def test_card_number_partial_prefix_suffix_and_variant_rejected(self):
        for wrong in ("1116/080", "116/0800", "A116/080", "116/080-ALT",
                      "116/080/1", "116/080.X"):
            with self.subTest(wrong=wrong):
                page = f"리자몽 ex {wrong} 현재 시세 ₩390,000"
                self.assertEqual(market._match_confidence(page, self.card),
                                 (0.0, "card_number_missing"))
                self.assertIsNone(market.parse_collectory(
                    page, self.card, "https://collectory.cc/cards?search=charizard"))
                self.assertIsNone(market.parse_kream(
                    page, self.card, "https://kream.co.kr/search?keyword=charizard"))

    def test_exact_card_number_and_fullwidth_japanese_code(self):
        for number in ("116/080", "１１６／０８０"):
            with self.subTest(number=number):
                page = f"리자몽 ex {number} 현재 시세 ₩390,000"
                self.assertEqual(market._match_confidence(page, self.card),
                                 (0.99, "card_number+card_name"))
                result = market.parse_collectory(
                    page, self.card, "https://collectory.cc/cards?search=charizard")
                self.assertIsNotNone(result)
                self.assertEqual(result["price_krw"], 390000)

    def test_first_false_substring_must_not_steal_price_window(self):
        page = ("리자몽 ex 1116/080 ₩999,000 " + "x" * 1000 +
                " 리자몽 ex 116/080 ₩390,000")
        parsed = market.parse_collectory(
            page, self.card, "https://collectory.cc/cards?search=charizard")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["price_krw"], 390000)

    def test_product_code_partial_match_rejected(self):
        for wrong in ("XBOX-XYZ", "BOX-XYZ2", "BOX-XYZ-PR", "BOX-XYZ/2"):
            with self.subTest(wrong=wrong):
                page = f"Booster Box {wrong} ₩250,000"
                self.assertEqual(market._match_confidence(page, self.box),
                                 (0.0, "product_code_missing"))
                self.assertIsNone(market.parse_collectory(
                    page, self.box, "https://collectory.cc/cards?search=box"))
        self.assertEqual(market._match_confidence(
            "Booster Box BOX-XYZ ₩250,000", self.box),
            (0.96, "product_code+name"))

    def test_number_only_and_japanese_adjoining_script(self):
        row = {"key": "JP|test|HIT", "card_number": "001/100",
               "card_name": "", "name": ""}
        self.assertEqual(market._match_confidence("001/100 ₩50,000", row),
                         (0.97, "card_number"))
        self.assertEqual(market._identifier_location(
            "リザードン００１／１００", "001/100"), len("リザードン"))
        self.assertEqual(market._identifier_location("001/1000", "001/100"), -1)


if __name__ == "__main__":
    unittest.main()
