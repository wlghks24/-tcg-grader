#!/usr/bin/env python3
"""V1009 offline marketplace product-local price/name/sale fail-closed regression."""
from __future__ import annotations
import unittest
from unittest.mock import patch

import wyyyes_market_source as market


URL = "https://wyyyes.com/category/pokemon-card/7063331"
TITLE = "포켓몬 카드 뮤 ex SAR 135/103 일본판"
PRICE = "17,000원"
RECOMMENDED = """
<section>
  <h1>포켓몬카드 모아 보기</h1>
  <h1>원피스 카드 루피 OP05-119 한국판</h1><h2>950,000원</h2>
  <h1>포켓몬 카드 피카츄 112/100 한국판</h1><h2>2,000,000원</h2>
  <p>추천 상품 판매완료 낙찰 3,000,000원</p>
</section>
"""


def html(body: str, *, title: str = TITLE, head: str = "") -> str:
    return (f"<html><head>{head}</head><body>"
            f"<h1>포켓몬카드</h1><h1>{title}</h1>{body}"
            f"{RECOMMENDED}</body></html>")


class V1009LocalProductEvidenceTests(unittest.TestCase):
    def parse(self, body, **kwargs):
        return market.parse_public_listing(html(body, **kwargs), URL,
                                           fallback_title="추천 피카츄 112/100 한국판",
                                           snippet="판매완료 낙찰 3,000,000원")

    def test_category_h1_skipped_exact_main_title_and_price_only(self):
        row = self.parse("<h2>판매 시작가: 17,000원 ㆍ 배송비: 5,000원</h2>")
        self.assertIsNotNone(row)
        self.assertEqual(TITLE, row["title"])
        self.assertEqual(17000, row["price"])
        self.assertEqual("135/103", row["card_number"])
        self.assertEqual("JP", row["card_region"])
        self.assertEqual("Pokémon", row["game"])
        self.assertEqual("asking", row["price_type"])
        self.assertFalse(row["is_completed_sale"])

    def test_missing_primary_price_does_not_borrow_recommendations_or_shipping(self):
        for body in ("<p>본문 가격 없음</p>",
                     "<h2>배송비: 5,000원</h2>",
                     "<p>30,000원 추천 매물</p>"):
            with self.subTest(body=body):
                self.assertIsNone(self.parse(body))

    def test_no_primary_title_or_multiple_primary_titles_refused(self):
        page = "<html><h1>포켓몬카드</h1><h2>20,000원</h2>" + RECOMMENDED + "</html>"
        self.assertIsNone(market.parse_public_listing(page, URL,
                         fallback_title="뮤 ex 135/103 일본판 포켓몬 카드",
                         snippet="20,000원"))
        self.assertIsNone(self.parse("<h1>피카츄 112/100 한국판 포켓몬 카드</h1>"
                                     "<h2>17,000원</h2>"))

    def test_meta_only_product_price_can_be_used_without_body_fallback(self):
        row = self.parse("<p>가격 제안하기</p>",
                         head='<meta itemprop="price" content="17000">')
        self.assertEqual(17000, row["price"])
        self.assertFalse(row["is_completed_sale"])

    def test_conflicting_or_duplicate_prices_are_held(self):
        samples = (
            ("<h2>17,000원</h2><h2>99,000원</h2>", ""),
            ("<h2>17,000원 + 30,000원</h2>", ""),
            ("<h2>17,000원</h2>", '<meta itemprop="price" content="99000">'),
            ("<h2>17,000원</h2>", '<meta itemprop="price" content="17000"><meta name="price" content="17000">'),
        )
        for body, head in samples:
            with self.subTest(body=body, head=head):
                self.assertIsNone(self.parse(body, head=head))

    def test_script_json_price_and_fake_script_heading_cannot_be_hijacked(self):
        with_script = ('<script>{"price":980000,"html":"<h2>98,000원</h2>'
                       '<h1>원피스 카드 루피 OP05-119 한국판</h1>"}</script>')
        self.assertIsNone(self.parse(with_script))
        ok = self.parse('<h2>17,000원</h2>' + with_script)
        self.assertEqual(17000, ok["price"])
        self.assertEqual(TITLE, ok["title"])

    def test_snippet_and_footer_sold_or_auction_are_never_proof(self):
        row = self.parse("<h2>17,000원</h2><p>즉시 구매하기 가격 제안</p>"
                         "<footer>낙찰완료 추천 판매완료</footer>")
        self.assertFalse(row["is_completed_sale"])
        self.assertEqual("asking", row["price_type"])

    def test_scoped_explicit_product_sale_is_distinct_from_generic_stock(self):
        sold = self.parse("<h2>17,000원</h2><p>판매완료</p>")
        auction = self.parse("<h2>17,000원</h2><p>낙찰완료</p>")
        stock = self.parse("<h2>17,000원</h2><p>SOLD OUT 가격제안</p>")
        self.assertEqual("sold", sold["price_type"])
        self.assertEqual("auction_result", auction["price_type"])
        self.assertEqual("asking", stock["price_type"])

    def test_no_card_id_from_related_product_even_if_price_matches(self):
        row = self.parse("<h2>17,000원</h2>", title="일본판 포켓몬 카드")
        self.assertIsNotNone(row)
        self.assertEqual("", row["card_number"])
        self.assertEqual("JP", row["card_region"])

    def test_unknown_or_wrong_public_host_is_not_collected(self):
        page = html("<h2>17,000원</h2>")
        for url in ("https://evil.invalid/category/pokemon-card/1",
                    "https://wyyyes.com.evil.invalid/category/pokemon-card/1",
                    "http://wyyyes.com/category/pokemon-card/1",
                    "https://wyyyes.com/recommended/1"):
            with self.subTest(url=url):
                self.assertIsNone(market.parse_public_listing(page, url))

    def test_collector_degraded_old_rows_are_not_new_independent_evidence(self):
        with patch.object(market, "_rss", return_value=[
                {"url": URL, "title": "검색엔진이 조작한 제목", "snippet": "판매완료 98,000원"}]):
            with patch.object(market, "_fetch_public",
                              return_value=html("<p>17,000원 본문 설명</p>")):
                result = market.collect_quotes(previous=[])
        self.assertEqual("degraded_empty", result["status"])
        self.assertEqual([], result["quotes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
