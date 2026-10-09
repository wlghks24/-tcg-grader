#!/usr/bin/env python3
"""V552: verified manual official listing does not mutate canonical data ancestry."""
import json
import unittest
from pathlib import Path
import update_purchase_sources as purchase

ROOT=Path(__file__).resolve().parent
URL="https://new.pokemonkorea.co.kr/card/category/3"

class PokemonOfficialCatalogV552(unittest.TestCase):
    def test_expansion_catalog_is_public_https_and_old_alias_rules_stay_unchanged(self):
        self.assertEqual(purchase.checked_url(URL), URL)
        self.assertEqual(purchase.checked_url("https://new.pokemonkorea.co.kr/card"),
                         purchase.POKEMON_KR_OFFICIAL_HOME)
        self.assertEqual(purchase.checked_url("https://new.pokemonkorea.co.kr/card/"),
                         purchase.POKEMON_KR_OFFICIAL_HOME)
        self.assertEqual(purchase.checked_url("https://pokemoncard.co.kr/main"),
                         purchase.POKEMON_KR_OFFICIAL_HOME)

    def test_immutable_source_data_keeps_official_home_and_original_provenance(self):
        data=json.loads((ROOT/"purchase_sources.json").read_text(encoding="utf-8"))
        rows=[r for r in data["sources"] if r.get("name")=="포켓몬 카드 게임 코리아 제품"]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["url"], purchase.POKEMON_KR_OFFICIAL_HOME)
        self.assertEqual(rows[0]["original_url"],
                         "https://pokemoncard.co.kr/card/category/product")
        self.assertNotIn("포켓몬코리아 공식 확장팩 목록",
                         [r.get("name") for r in data["sources"]])

    def test_manual_link_is_read_only_and_stock_unknown(self):
        source=(ROOT/"tcg_market_expanded_v487.js").read_text(encoding="utf-8")
        self.assertIn(URL,source)
        self.assertIn("포켓몬 공식 확장팩 목록 · 판매처 재고 미확인",source)
        self.assertIn("includePokemonCatalog(activeGame)",source)
        self.assertIn("browserLink(",source)
        self.assertNotIn("fetch(\"https://new.pokemonkorea.co.kr/card/category/3",source)

if __name__=="__main__": unittest.main()
