#!/usr/bin/env python3
"""V552: new official expansion listing is additive to immutable alias recovery."""
import json
import unittest
from pathlib import Path
import update_purchase_sources as sources

ROOT=Path(__file__).resolve().parent
URL="https://new.pokemonkorea.co.kr/card/category/3"
LABEL="포켓몬코리아 공식 확장팩 목록"

class PokemonOfficialCatalogV552(unittest.TestCase):
    def test_expansion_index_is_not_retired_and_prior_aliases_unchanged(self):
        self.assertEqual(sources.checked_url(URL),URL)
        self.assertEqual(sources.checked_url("https://new.pokemonkorea.co.kr/card"),
                         sources.POKEMON_KR_OFFICIAL_HOME)
        self.assertEqual(sources.checked_url("https://new.pokemonkorea.co.kr/card/"),
                         sources.POKEMON_KR_OFFICIAL_HOME)
        self.assertEqual(sources.checked_url("https://pokemoncard.co.kr/main"),
                         sources.POKEMON_KR_OFFICIAL_HOME)

    def test_catalog_is_manual_official_provenance_not_fabricated_stock(self):
        data=json.loads((ROOT/"purchase_sources.json").read_text(encoding="utf-8"))
        matched=[x for x in data["sources"] if x.get("name")==LABEL]
        self.assertEqual(len(matched),1)
        row=matched[0]
        self.assertEqual(row["url"],URL)
        self.assertEqual(row["region"],"KR")
        self.assertEqual(row["games"],["Pokemon"])
        self.assertEqual(row["type"],"official")
        self.assertIn("확장팩",row["note"])
        self.assertIn("재고",row["note"])
        self.assertIn("미확인",row["note"])
        self.assertIn("미확인",row.get("inventory_status",""))
        self.assertNotIn("verified_stock",row)
        self.assertEqual(sources.normalize_source(row)["url"],URL)

    def test_legacy_item_ids_do_not_map_to_unrelated_new_products(self):
        old="https://pokemoncard.co.kr/card/668"
        self.assertEqual(sources.checked_url(old),old)
        self.assertNotEqual(sources.checked_url(old),URL)
        self.assertNotEqual(sources.checked_url("https://pokemoncard.co.kr/main"),URL)

if __name__=="__main__": unittest.main()
