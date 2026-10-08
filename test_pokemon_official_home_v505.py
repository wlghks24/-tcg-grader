# -*- coding: utf-8 -*-
"""Regression: the canonical official Korean Pokemon home must not be a known 410 URL."""
import unittest
import validate_external_links as links
import update_purchase_sources as purchase

class PokemonOfficialHomeV505Tests(unittest.TestCase):
    def test_official_home_uses_same_company_current_domain(self):
        self.assertEqual(purchase.POKEMON_KR_OFFICIAL_HOME, "https://pokemonkorea.com/")
        self.assertIn("pokemonkorea.com", purchase.OFFICIAL_CHAIN_HOSTS["포켓몬 카드샵"])
        for legacy in ("https://pokemoncard.co.kr/", "https://pokemoncard.co.kr/main",
                       "https://new.pokemonkorea.co.kr/card",
                       "https://pokemonkorea.co.kr/", "https://www.pokemonkorea.co.kr/"):
            with self.subTest(legacy=legacy):
                self.assertEqual(purchase.checked_url(legacy), "https://pokemonkorea.com/")

    def test_link_auditor_replaces_retired_official_root_without_inventing_details(self):
        for host in ("new.pokemonkorea.co.kr", "pokemoncard.co.kr",
                     "www.pokemoncard.co.kr", "pokemonkorea.co.kr",
                     "www.pokemonkorea.co.kr"):
            with self.subTest(host=host):
                self.assertEqual(links.FALLBACKS[host], "https://pokemonkorea.com/")
        # Exact old card IDs do not become invented new news IDs.
        detail="https://pokemoncard.co.kr/card/668"
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url(detail), detail)
        self.assertNotIn("pokemonkorea.com", links.FALLBACKS.get("kream.co.kr", ""))

if __name__ == "__main__":
    unittest.main()
