#!/usr/bin/env python3
import unittest
import validate_external_links as links


LIVE_HOME = "https://pokemonkorea.co.kr/"


class PokemonRetiredLinkMigrationV356Tests(unittest.TestCase):
    def test_numeric_detail_id_is_preserved_until_broken_link_fallback(self):
        self.assertEqual(
            links._canonicalize_retired_pokemon_kr_url(
                "https://pokemoncard.co.kr/card/668"
            ),
            "https://pokemoncard.co.kr/card/668",
        )
        self.assertEqual(
            links._canonicalize_retired_pokemon_kr_url(
                "https://www.pokemoncard.co.kr/card/797?from=archive#detail"
            ),
            "https://www.pokemoncard.co.kr/card/797?from=archive#detail",
        )

    def test_old_card_root_and_main_move_to_live_card_root(self):
        for old in (
            "https://pokemoncard.co.kr/",
            "https://pokemoncard.co.kr/main",
            "https://pokemoncard.co.kr/card",
        ):
            self.assertEqual(links._canonicalize_retired_pokemon_kr_url(old), LIVE_HOME)

    def test_live_alias_is_idempotent_and_unknown_old_path_is_not_invented(self):
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url("https://new.pokemonkorea.co.kr/card"), LIVE_HOME)
        unknown = "https://pokemoncard.co.kr/card/category/3"
        self.assertEqual(links._canonicalize_retired_pokemon_kr_url(unknown), unknown)

    def test_all_pokemon_korea_link_fallbacks_point_to_live_official_alias(self):
        for host in (
            "new.pokemonkorea.co.kr",
            "pokemoncard.co.kr",
            "www.pokemoncard.co.kr",
            "pokemonkorea.co.kr",
            "www.pokemonkorea.co.kr",
        ):
            self.assertEqual(links.FALLBACKS[host], LIVE_HOME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
