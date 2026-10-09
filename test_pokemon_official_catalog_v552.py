#!/usr/bin/env python3
"""V552: official Pokémon product index is browsable, not proof of price/stock."""
import json
import unittest
from pathlib import Path
import update_purchase_sources as sources

ROOT=Path(__file__).resolve().parent
URL="https://new.pokemonkorea.co.kr/card"
LABEL="포켓몬코리아 공식 카드·BOX 제품 목록"

class PokemonOfficialCatalogV552(unittest.TestCase):
    def test_index_preserved_instead_of_replaced_by_generic_home(self):
        self.assertEqual(sources.checked_url(URL),URL)
        self.assertEqual(sources.checked_url(URL+"/"),URL)
        self.assertEqual(sources.checked_url("https://pokemoncard.co.kr/main"),sources.POKEMON_KR_OFFICIAL_HOME)

    def test_catalog_is_explicit_provenance_not_fabricated_stock(self):
        data=json.loads((ROOT/"purchase_sources.json").read_text(encoding="utf-8"))
        matched=[x for x in data["sources"] if x.get("name")==LABEL]
        self.assertEqual(len(matched),1)
        row=matched[0]
        self.assertEqual(row["url"],URL)
        self.assertEqual(row["region"],"KR")
        self.assertEqual(row["games"],["Pokemon"])
        self.assertEqual(row["type"],"official")
        self.assertNotIn("재고 확인",row.get("note",""))
        self.assertIn("재고",row["note"])
        self.assertIn("미확인",row["note"])
        self.assertIn("미확인",row.get("inventory_status",""))
        self.assertNotIn("verified_stock",row)
        normalized=sources.normalize_source(row)
        self.assertEqual(normalized["url"],URL)

    def test_unknown_legacy_card_number_never_promoted_to_product(self):
        old="https://pokemoncard.co.kr/card/668"
        self.assertNotEqual(sources.checked_url(old),URL)
        self.assertEqual(sources.checked_url(old),old)
        self.assertNotEqual(sources.checked_url("https://pokemoncard.co.kr/main"),URL)

if __name__=="__main__": unittest.main()
