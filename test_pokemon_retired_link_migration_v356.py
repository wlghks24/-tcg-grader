#!/usr/bin/env python3
import unittest
import validate_external_links as links


class PokemonRetiredLinkMigrationV356Tests(unittest.TestCase):
    def test_numeric_detail_id_is_preserved_on_current_official_host(self):
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url("https://new.pokemonkorea.co.kr/card/668"), "https://pokemoncard.co.kr/card/668")
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url("https://new.pokemonkorea.co.kr/card/797?from=archive#detail"), "https://pokemoncard.co.kr/card/797?from=archive#detail")

    def test_retired_card_root_moves_to_stable_official_home(self):
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url("https://new.pokemonkorea.co.kr/card"), "https://pokemonkorea.co.kr/")

    def test_unknown_retired_path_is_not_invented(self):
        old = "https://new.pokemonkorea.co.kr/card/category/3"
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url(old), old)

    def test_retired_host_has_safe_official_home_fallback(self):
        self.assertEqual(links.FALLBACKS["new.pokemonkorea.co.kr"], "https://pokemonkorea.co.kr/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
