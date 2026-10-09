#!/usr/bin/env python3
"""V554 regression: Unicode card-name evidence must match the same listing."""
import unittest
import market_public_crosscheck as market

class CollectorUnicodeEvidenceV554(unittest.TestCase):
    def setUp(self):
        self.row={"key":"JP|テスト|HIT","region":"JP","game":"Pokémon",
                  "card_name":"リザードン","card_number":"001/100",
                  "name":"リザードン"}
        self.url="https://kream.co.kr/search?keyword=JP-test"

    def test_distinct_japanese_names_do_not_collapse(self):
        self.assertEqual(market.norm("リザードン"),"リザードン")
        self.assertEqual(market.norm("ピカチュウ"),"ピカチュウ")
        self.assertNotEqual(market.norm("リザードン"),market.norm("ピカチュウ"))
        self.assertEqual(market.norm("ＪＰ　リザードン 001/100"),"jpリザードン001100")
        self.assertEqual(market.norm("메가리자몽X ex"),"메가리자몽xex")

    def test_reject_other_card_with_same_number(self):
        page="ポケモンカード ピカチュウ 001/100 390,000원 거래 4"
        self.assertEqual(market._match_confidence(page,self.row),(0.0,"card_number_name_mismatch"))
        self.assertIsNone(market.parse_kream(page,self.row,self.url))
        self.assertIsNone(market.parse_collectory(
            "ピカチュウ 001/100 현재 시세 ₩390,000",self.row,
            "https://collectory.cc/cards?search=JP-test"))

    def test_verified_same_card_name_and_number_is_accepted(self):
        page="ポケモンカード リザードン 001/100 390,000원 거래 4"
        result=market.parse_kream(page,self.row,self.url)
        self.assertIsNotNone(result)
        self.assertEqual(result["price_krw"],390000)
        self.assertEqual(result["confidence"],.99)
        self.assertEqual(result["matched_by"],"card_number+card_name")

    def test_distant_matching_name_cannot_validate_another_listing(self):
        page=("リザードン"+"。"*1400+
              "ピカチュウ 001/100 390,000원 거래 4")
        self.assertIsNone(market.parse_kream(page,self.row,self.url))

    def test_number_only_rows_still_use_number_evidence(self):
        record={"key":"JP|test|HIT","card_number":"001/100","card_name":"","name":""}
        grade,label=market._match_confidence("001/100 120,000원",record)
        self.assertEqual(grade,.97)
        self.assertEqual(label,"card_number")

    def test_name_missing_from_page_cannot_fabricate_match(self):
        self.assertEqual(market._match_confidence("001/100 120,000원",self.row)[0],0.0)
        self.assertIsNone(market.parse_kream("001/100 120,000원",self.row,self.url))

if __name__=="__main__":
    unittest.main()
