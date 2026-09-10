from __future__ import annotations

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
