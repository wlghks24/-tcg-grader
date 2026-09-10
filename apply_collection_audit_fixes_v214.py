#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one replacement target, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    replace_once(
        "feature_contract.py",
        '''    coverage = promos.get("coverage") if isinstance(promos.get("coverage"), dict) else {}
    add("promo_collab_movies", "한·일·미 포켓몬·원피스·나루토 행사·콜라보·영화",
        coverage.get("covered_game_region_pairs") == 9 and coverage.get("movie_game_region_pairs") == 9
        and {"promo", "collaboration", "movie"} <= {row.get("category") for row in promos.get("items", []) if isinstance(row, dict)},
        "3작품×3국 공식출처 9조합")
''',
        '''    promo_rows = [row for row in promos.get("items", []) if isinstance(row, dict)]
    core_games = {"포켓몬 카드", "원피스 카드", "나루토 카드"}
    core_regions = {"KR", "JP", "US"}
    expected_core_pairs = {(game, region) for game in core_games for region in core_regions}
    covered_core_pairs = {
        (row.get("game"), row.get("region")) for row in promo_rows
        if row.get("game") in core_games and row.get("region") in core_regions
    }
    movie_core_pairs = {
        (row.get("game"), row.get("region")) for row in promo_rows
        if row.get("game") in core_games and row.get("region") in core_regions
        and row.get("category") == "movie"
    }
    add("promo_collab_movies", "한·일·미 포켓몬·원피스·나루토 행사·콜라보·영화",
        expected_core_pairs <= covered_core_pairs and expected_core_pairs <= movie_core_pairs
        and {"promo", "collaboration", "movie"} <= {row.get("category") for row in promo_rows},
        "3작품×3국 핵심 9조합 + 확장 지역은 별도 허용")
''',
    )

    replace_once(
        "update_promo_events.py",
        '''OFFICIAL_SOURCE_REPLACEMENTS = {
    "https://pokemonkorea.co.kr/2026_battle_tournament3":
        "https://pokemonkorea.co.kr/2026_battle_tournament3/menu800",
}
''',
        '''OFFICIAL_SOURCE_REPLACEMENTS = {
    "https://pokemonkorea.co.kr/2026_battle_tournament3":
        "https://new.pokemonkorea.co.kr/card",
    "https://pokemonkorea.co.kr/2026_battle_tournament3/menu800":
        "https://new.pokemonkorea.co.kr/card",
    "https://pokemonkorea.co.kr/": "https://new.pokemonkorea.co.kr/card",
    "https://www.pokemonkorea.co.kr/": "https://new.pokemonkorea.co.kr/card",
}
''',
    )

    replace_once(
        "update_purchase_sources.py",
        '''CANONICAL_URLS = {
    "https://events.pokemon.com/en-us/locations": "https://events.pokemon.com/EventLocator",
    "https://www.gamestop.com/stores/": "https://www.gamestop.com/stores",
}
''',
        '''CANONICAL_URLS = {
    "https://events.pokemon.com/en-us/locations": "https://events.pokemon.com/EventLocator",
    "https://www.gamestop.com/stores/": "https://www.gamestop.com/stores",
    "https://pokemoncard.co.kr/": "https://new.pokemonkorea.co.kr/card",
    "https://www.pokemoncard.co.kr/": "https://new.pokemonkorea.co.kr/card",
    "https://pokemoncard.co.kr/card/225": "https://new.pokemonkorea.co.kr/card",
    "https://pokemoncard.co.kr/card/category/product": "https://new.pokemonkorea.co.kr/card",
    "https://pokemonkorea.co.kr/": "https://new.pokemonkorea.co.kr/card",
    "https://www.pokemonkorea.co.kr/": "https://new.pokemonkorea.co.kr/card",
}
''',
    )
    replace_once(
        "update_purchase_sources.py",
        '    "포켓몬 카드샵": {"pokemoncard.co.kr"},\n',
        '    "포켓몬 카드샵": {"pokemoncard.co.kr", "www.pokemoncard.co.kr", "new.pokemonkorea.co.kr"},\n',
    )

    replace_once(
        "validate_external_links.py",
        ''' "pokemoncard.co.kr":"https://pokemoncard.co.kr/",
 "www.pokemoncard.co.kr":"https://pokemoncard.co.kr/",
 "pokemonkorea.co.kr":"https://pokemonkorea.co.kr/",
 "www.pokemonkorea.co.kr":"https://pokemonkorea.co.kr/",
''',
        ''' "pokemoncard.co.kr":"https://new.pokemonkorea.co.kr/card",
 "www.pokemoncard.co.kr":"https://new.pokemonkorea.co.kr/card",
 "pokemonkorea.co.kr":"https://new.pokemonkorea.co.kr/card",
 "www.pokemonkorea.co.kr":"https://new.pokemonkorea.co.kr/card",
''',
    )

    (ROOT / "test_collection_scope_compat_v214.py").write_text(
        '''from __future__ import annotations

import unittest

import feature_contract
import update_promo_events
import update_purchase_sources
import validate_external_links


class CollectionScopeCompatV214Tests(unittest.TestCase):
    def test_feature_contract_accepts_extended_asia_scope_when_core_matrix_is_complete(self):
        report = feature_contract.audit_feature_contract()
        feature = next(row for row in report["features"] if row["id"] == "promo_collab_movies")
        self.assertTrue(feature["implemented"], feature)

    def test_retired_pokemon_korea_urls_canonicalize_to_current_official_card_page(self):
        expected = "https://new.pokemonkorea.co.kr/card"
        self.assertEqual(update_purchase_sources.checked_url("https://pokemoncard.co.kr/"), expected)
        self.assertEqual(update_purchase_sources.checked_url("https://pokemoncard.co.kr/card/225"), expected)
        self.assertIn("new.pokemonkorea.co.kr", update_purchase_sources.OFFICIAL_CHAIN_HOSTS["포켓몬 카드샵"])

    def test_event_and_link_audit_recovery_never_fall_back_to_retired_root(self):
        expected = "https://new.pokemonkorea.co.kr/card"
        self.assertEqual(update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS["https://pokemonkorea.co.kr/"], expected)
        self.assertEqual(update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS["https://www.pokemonkorea.co.kr/"], expected)
        self.assertEqual(validate_external_links.FALLBACKS["pokemoncard.co.kr"], expected)
        self.assertEqual(validate_external_links.FALLBACKS["pokemonkorea.co.kr"], expected)


if __name__ == "__main__":
    unittest.main()
''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
