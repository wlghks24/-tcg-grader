#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

import wyyyes_market_source as wyyyes

ROOT = Path(__file__).resolve().parent


class WyyyesMarketSourceV267Tests(unittest.TestCase):
    def test_card_region_is_separate_from_korean_market(self):
        self.assertEqual("JP", wyyyes.infer_card_region("일판 메가팬텀ex PSA10"))
        self.assertEqual("KR", wyyyes.infer_card_region("한국판 M 메가 레쿠쟈 EX"))
        self.assertEqual("US", wyyyes.infer_card_region("English US Pokemon card"))
        self.assertEqual("UNKNOWN", wyyyes.infer_card_region("포켓몬 카드"))

    def test_asking_price_is_never_promoted_to_completed_sale(self):
        self.assertEqual("asking", wyyyes.infer_price_type("가격 제안하기 즉시 구매하기"))
        self.assertEqual("sold", wyyyes.infer_price_type("판매완료 상품"))
        self.assertEqual("auction_result", wyyyes.infer_price_type("경매 종료 낙찰 120,000원"))

    def test_public_listing_parser_keeps_edition_market_currency_and_grade(self):
        html = """
        <html><body>
          <h1>뮤 V SR PSA 10 퓨전아츠 106/100 일본판 포켓몬 카드</h1>
          <h2>600,000원</h2>
          <p>가격 제안하기</p><p>즉시 구매하기</p>
          <p>PSA 10 GEM MT 등급 2021 일본판 포켓몬 카드</p>
        </body></html>
        """
        row = wyyyes.parse_public_listing(
            html,
            "https://wyyyes.com/category/pokemon-card/6502248",
        )
        self.assertIsNotNone(row)
        self.assertEqual("WYYYES", row["platform"])
        self.assertEqual("KR", row["market_region"])
        self.assertEqual("JP", row["card_region"])
        self.assertEqual("KRW", row["currency"])
        self.assertEqual(600000, row["price"])
        self.assertEqual("asking", row["price_type"])
        self.assertFalse(row["is_completed_sale"])
        self.assertEqual("PSA", row["grading_company"])
        self.assertEqual(10, row["grade"])
        self.assertEqual("106/100", row["card_number"])

    def test_brg_title_wins_over_unrelated_platform_badge(self):
        html = """
        <html><body>
          <h1>뮤Vmax BRG10 일판 포켓몬 카드</h1>
          <h2>80,000원</h2>
          <p>PSA 10</p><p>가격 제안하기</p>
        </body></html>
        """
        row = wyyyes.parse_public_listing(html, "https://wyyyes.com/category/pokemon-card/6567798")
        self.assertEqual("BRG", row["grading_company"])
        self.assertEqual(10, row["grade"])

    def test_runtime_wiring_is_fail_closed_and_visible(self):
        wrapper = (ROOT / "update_market_prices_parallel_v260.py").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        flow = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("import wyyyes_market_source as wyyyes", wrapper)
        self.assertIn('db.setdefault("platform_quotes", {})', wrapper)
        self.assertIn('"wyyyes_market_source.py"', manifest)
        self.assertIn("asking_price_is_not_completed_sale", wrapper)
        self.assertIn("판본별 공개시장 시세", flow)
        self.assertIn("판매중/제안가", flow)
        self.assertIn("체결/판매완료", flow)
        self.assertIn("card_region", flow)


if __name__ == "__main__":
    unittest.main()
