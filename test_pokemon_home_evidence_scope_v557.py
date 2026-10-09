#!/usr/bin/env python3
"""V557: preserve historic source snapshots and show unverified home scope in a read-only UI."""
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
NAMES={
    "포켓몬 카드 게임 코리아 제품",
    "포켓몬 공인 카드샵 안내",
    "포켓몬 카드 전문점 공식 매장 안내",
}

class PokemonHomeEvidenceScopeV557(unittest.TestCase):
    def test_legacy_product_store_provenance_is_not_rewritten(self):
        original=json.loads((ROOT/"purchase_sources.json").read_text(encoding="utf-8"))
        matches=[row for row in original.get("sources",[])
                 if isinstance(row,dict) and row.get("name") in NAMES]
        self.assertEqual(len(matches),3)
        self.assertEqual({row["name"] for row in matches},NAMES)
        for row in matches:
            with self.subTest(row=row["name"]):
                self.assertEqual(row["type"],"official")
                self.assertEqual(row["url"],HOMEPAGE)
                self.assertIn(row["original_url"],LEGACY)
                # Immutable historical snapshot: the UI must reinterpret
                # generic homepage reachability, not change archived evidence.
                self.assertEqual(row["link_status"],"정상")

    def test_ui_addon_is_read_only_and_does_not_claim_detail_or_stock(self):
        js=(ROOT/"tcg_market_expanded_v487.js").read_text(encoding="utf-8")
        self.assertIn("function homepageOnlyOfficialSources(data)",js)
        self.assertIn("function renderHomepageScopeWarning(target, game)",js)
        self.assertIn("개별 제품·공인 매장 상세 정보나 재고까지 검증된 것은 아닙니다",js)
        self.assertIn('load("purchase_sources.json"',js)
        self.assertIn("sourceListRequested",js)
        self.assertIn('"https://pokemoncard.co.kr/card/225"',js)
        self.assertIn('"https://pokemoncard.co.kr/card/category/product"',js)
        self.assertNotIn("fetch(\"https://pokemonkorea.co.kr/",js)

    def test_no_deprecated_detail_becomes_auto_verified(self):
        self.assertEqual(purchase.checked_url("https://pokemoncard.co.kr/main"),
                         purchase.POKEMON_KR_OFFICIAL_HOME)
        self.assertEqual(purchase.checked_url("https://new.pokemonkorea.co.kr/card/category/3"),
                         "https://new.pokemonkorea.co.kr/card/category/3")
        self.assertNotIn("homepageOnlyOfficialSources",
                         (ROOT/"update_purchase_sources.py").read_text(encoding="utf-8"))

if __name__=="__main__":
    unittest.main()
