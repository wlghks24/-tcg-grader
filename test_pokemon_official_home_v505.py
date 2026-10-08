# -*- coding: utf-8 -*-
"""Verified current first-party replacement for GET-confirmed dead Pokémon KR root."""
import unittest
import validate_external_links as links
import update_purchase_sources as purchase

class PokemonOfficialHomeV505Tests(unittest.TestCase):
    def test_current_fallback_is_strictly_same_company(self):
        for host in ("new.pokemonkorea.co.kr", "pokemoncard.co.kr",
                     "www.pokemoncard.co.kr", "pokemonkorea.co.kr",
                     "www.pokemonkorea.co.kr"):
            with self.subTest(host=host):
                self.assertEqual(links.FALLBACKS[host], "https://pokemonkorea.com/")
        self.assertNotEqual(links.FALLBACKS["pokemonkorea.co.kr"], "https://pokemonkorea.co.kr/")
        self.assertNotIn("example.com", links.FALLBACKS)

    def test_confirmed_410_replaced_and_provenance_preserved(self):
        old="https://pokemonkorea.co.kr/"
        row={"source":old}
        tasks={old:[("promo_events.json",row,"source")]}
        result={old:{"state":"broken","code":410,"confirmed_by":"GET"}}
        counts,unresolved=links._apply_results(tasks,result,"2026-10-08T00:00:00+00:00")
        self.assertEqual(counts["unresolved_broken"],0)
        self.assertEqual(counts["repaired"],1)
        self.assertEqual(unresolved,[])
        self.assertEqual(row["source"],"https://pokemonkorea.com/")
        self.assertEqual(row["original_source"],old)

    def test_old_card_ids_never_become_invented_news_ids(self):
        url="https://pokemoncard.co.kr/card/668"
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url(url),url)
        # Historical purchase canonicalization is unchanged in this bounded fix.
        self.assertEqual(purchase.checked_url("https://pokemoncard.co.kr/main"),
                         purchase.POKEMON_KR_OFFICIAL_HOME)

if __name__=="__main__":
    unittest.main()
