#!/usr/bin/env python3
"""V557: official homepage reachability is not product/store directory proof."""
import json
import unittest
from pathlib import Path

import update_purchase_sources as purchase


ROOT=Path(__file__).resolve().parent
HOMEPAGE="https://pokemonkorea.co.kr/"
LEGACY={
    "https://pokemoncard.co.kr/card/225",
    "https://pokemoncard.co.kr/card/category/product",
}


class PokemonHomeEvidenceScopeV557(unittest.TestCase):
    def test_three_existing_sources_never_advertise_verified_detail(self):
        db=json.loads((ROOT/"purchase_sources.json").read_text(encoding="utf-8"))
        marked=[row for row in db["sources"] if purchase.official_home_only(row)]
        self.assertEqual(len(marked),3)
        self.assertEqual(
            {row["name"] for row in marked},
            {"포켓몬 카드 게임 코리아 제품",
             "포켓몬 공인 카드샵 안내",
             "포켓몬 카드 전문점 공식 매장 안내"},
        )
        for row in marked:
            with self.subTest(name=row["name"]):
                self.assertEqual(row["url"],HOMEPAGE)
                self.assertIn(row["original_url"],LEGACY)
                self.assertEqual(row["link_verification_scope"],"official_homepage_only")
                self.assertIs(row["detail_verified"],False)
                self.assertIn("미확인",row["link_status"])
                self.assertNotEqual(row["link_status"],"정상")

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
        self.assertIs(normalized["detail_verified"],False)
        self.assertNotIn("재고 확인",normalized.get("link_status",""))


if __name__=="__main__":
    unittest.main()
