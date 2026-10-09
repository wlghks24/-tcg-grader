#!/usr/bin/env python3
"""V555: free-source price evidence must match the requested printing/product."""
import unittest

import market_public_crosscheck as market


class CrosscheckIdentifierAndAmountV555(unittest.TestCase):
    def setUp(self):
        self.row = {
            "key": "KR|인페르노X|HIT", "game": "Pokémon",
            "card_name": "리자몽 ex", "card_number": "116/080",
            "name": "리자몽 ex",
        }

    def test_same_name_different_card_number_rejected(self):
        text = "리자몽 ex 115/080 현재 시세 ₩390,000 거래 5"
        self.assertEqual(market._match_confidence(text, self.row),
                         (0.0, "card_number_missing"))
        self.assertIsNone(market.parse_collectory(
            text, self.row, "https://collectory.cc/cards?search=charizard"))
        self.assertIsNone(market.parse_kream(
            text, self.row, "https://kream.co.kr/search?keyword=charizard"))

    def test_correct_number_and_card_name_accepted(self):
        text = "리자몽 ex 116/080 현재 시세 ₩390,000 거래 5"
        self.assertEqual(market._match_confidence(text, self.row),
                         (0.99, "card_number+card_name"))
        for parser, url in [
            (market.parse_collectory, "https://collectory.cc/cards?search=charizard"),
            (market.parse_kream, "https://kream.co.kr/search?keyword=charizard"),
        ]:
            with self.subTest(parser=parser.__name__):
                result = parser(text, self.row, url)
                self.assertIsNotNone(result)
                self.assertEqual(result["price_krw"], 390000)

    def test_box_code_missing_is_not_replaced_by_generic_name(self):
        row = {"key":"JP|Booster|BOX","name":"Booster Box","product_code":"BOX-XYZ",
               "card_name":"","card_number":""}
        text = "Booster Box edition BOX-ABC price ₩250,000"
        self.assertEqual(market._match_confidence(text,row),
                         (0.0,"product_code_missing"))
        self.assertIsNone(market.parse_collectory(text,row,
                             "https://collectory.cc/cards?search=booster"))
        found = market._match_confidence("Booster Box BOX-XYZ price ₩250,000",row)
        self.assertEqual(found,(0.96,"product_code+name"))

    def test_implausible_collectory_amounts_are_rejected(self):
        for bad in ("₩9,999,999,999", "₩0,099"):
            with self.subTest(bad=bad):
                text = "리자몽 ex 116/080 현재 시세 " + bad
                self.assertIsNone(market.parse_collectory(text,self.row,
                                  "https://collectory.cc/cards?search=charizard"))

    def test_collectory_boundary_amount_is_still_accepted(self):
        text = "리자몽 ex 116/080 현재 시세 ₩500,000,000"
        parsed = market.parse_collectory(text,self.row,
                          "https://collectory.cc/cards?search=charizard")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["price_krw"],500000000)

    def test_number_only_original_contract_is_preserved(self):
        row = {"key":"JP|sample|HIT","card_number":"001/100","card_name":"",
               "name":""}
        self.assertEqual(market._match_confidence("001/100 ₩50,000",row),
                         (0.97,"card_number"))

if __name__ == "__main__":
    unittest.main()
