#!/usr/bin/env python3
"""V557: official homepage reachability is not product/store directory proof."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import update_purchase_sources as purchase


ROOT=Path(__file__).resolve().parent
HOMEPAGE="https://pokemonkorea.co.kr/"
LEGACY={
    "https://pokemoncard.co.kr/card/225",
    "https://pokemoncard.co.kr/card/category/product",
}


class PokemonHomeEvidenceScopeV557(unittest.TestCase):
    def test_immutable_original_sources_are_classified_during_refresh(self):
        db=json.loads((ROOT/"purchase_sources.json").read_text(encoding="utf-8"))
        candidates=[row for row in db["sources"] if purchase.official_home_only(row)]
        self.assertEqual(len(candidates),3)
        self.assertEqual(
            {row["name"] for row in candidates},
            {"포켓몬 카드 게임 코리아 제품",
             "포켓몬 공인 카드샵 안내",
             "포켓몬 카드 전문점 공식 매장 안내"},
        )
        # The audited historical data is pinned by older Tablet GPT contracts.
        # Do not rewrite it merely to change the display's inference.
        for row in candidates:
            self.assertEqual(row["url"],HOMEPAGE)
            self.assertIn(row["original_url"],LEGACY)
            self.assertIn("미검증",purchase.official_scope_status(row,"정상"))

        with patch.object(purchase,"safe_read_text",
                          return_value=json.dumps({"sources":candidates},ensure_ascii=False)), \
             patch.object(purchase,"ensure_gyeonggi_lotte_stores",side_effect=lambda x:x), \
             patch.object(purchase,"ensure_diverse_retail_channels",side_effect=lambda x:x), \
             patch.object(purchase,"ensure_registry_tcg_sources",side_effect=lambda x:x), \
             patch.object(purchase,"probe",side_effect=lambda row:(row["name"],"정상")), \
             patch.object(purchase,"atomic_write_json"), \
             patch("social_stock_discovery.main",return_value={}):
            refreshed=purchase.main()
        self.assertEqual(len(refreshed["sources"]),3)
        for row in refreshed["sources"]:
            with self.subTest(row=row["name"]):
                self.assertEqual(row["link_verification_scope"],"official_homepage_only")
                self.assertIs(row["detail_verified"],False)
                self.assertIn("상세 미검증",row["link_status"])
                self.assertTrue(all("상세 미검증" in value for value in row["link_statuses"].values()))
                self.assertEqual(row["url"],HOMEPAGE)
                self.assertIn(row["original_url"],LEGACY)

    def test_homepage_status_never_proves_specific_product_or_store(self):
        row={"name":"포켓몬 공인 카드샵 안내","type":"official","url":HOMEPAGE,
             "original_url":"https://pokemoncard.co.kr/card/225"}
        for raw in ("정상","정상 · 안전한 공식 리디렉션 확인",
                    "리디렉션 응답·안전 대상 확인·기존 주소 유지 (HTTP 301)"):
            with self.subTest(raw=raw):
                state=purchase.official_scope_status(row,raw)
                self.assertIn("상세 미검증",state)
                self.assertNotEqual(state,raw)
        self.assertIn("형식만 확인",purchase.official_scope_status(row,"주소 형식 검증 완료"))
        blocked="재확인 필요·기존 주소 유지 (HTTPError: status 410)"
        self.assertEqual(purchase.official_scope_status(row,blocked),blocked)

    def test_unrelated_sources_and_changed_exact_url_not_downgraded(self):
        base={"name":"공식","type":"official","url":HOMEPAGE,
              "original_url":"https://pokemoncard.co.kr/card/225"}
        cases=[
            {**base,"url":"https://new.pokemonkorea.co.kr/card/category/3"},
            {**base,"original_url":"https://pokemoncard.co.kr/card/668"},
            {**base,"type":"marketplace"},
            {**base,"original_url":"https://fakepokemonkorea.co.kr/card/225"},
            {"name":"일본 공식","type":"official","url":"https://www.pokemon-card.com/products/"}
        ]
        for row in cases:
            with self.subTest(row=row):
                self.assertFalse(purchase.official_home_only(row))
                self.assertEqual(purchase.official_scope_status(row,"정상"),"정상")

    def test_registry_normalization_preserves_original_and_scope(self):
        db=json.loads((ROOT/"purchase_sources.json").read_text(encoding="utf-8"))
        row=next(row for row in db["sources"] if row["name"]=="포켓몬 카드 게임 코리아 제품")
        normalized=purchase.normalize_source(row)
        self.assertEqual(normalized["url"],HOMEPAGE)
        self.assertEqual(normalized["original_url"],"https://pokemoncard.co.kr/card/category/product")
        self.assertEqual(purchase.official_scope_status(normalized,"정상"),
                         "공식 홈페이지 접속 확인 · 상품/매장 상세 미검증")
        self.assertNotIn("재고 확인",normalized.get("link_status",""))


if __name__=="__main__":
    unittest.main()
