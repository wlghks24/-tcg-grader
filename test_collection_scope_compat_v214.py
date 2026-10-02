from __future__ import annotations

import unittest

import feature_contract
import multi_route_event_discovery
import social_event_discovery
import update_promo_events
import update_purchase_sources
import validate_external_links


class CollectionScopeCompatV214Tests(unittest.TestCase):
    def test_feature_contract_accepts_extended_asia_scope_when_core_matrix_is_complete(self):
        report = feature_contract.audit_feature_contract()
        feature = next(row for row in report["features"] if row["id"] == "promo_collab_movies")
        self.assertTrue(feature["implemented"], feature)

    def test_retired_pokemon_korea_urls_canonicalize_to_stable_official_home(self):
        expected = "https://pokemonkorea.co.kr/"
        self.assertEqual(update_purchase_sources.checked_url("https://pokemoncard.co.kr/"), expected)
        self.assertEqual(update_purchase_sources.checked_url("https://pokemoncard.co.kr/card/225"), expected)
        self.assertEqual(update_purchase_sources.checked_url("https://new.pokemonkorea.co.kr/card"), expected)
        hosts = update_purchase_sources.OFFICIAL_CHAIN_HOSTS["포켓몬 카드샵"]
        self.assertIn("pokemoncard.co.kr", hosts)
        self.assertIn("pokemonkorea.co.kr", hosts)

    def test_retired_pokemon_korea_urls_are_not_active_discovery_routes(self):
        current = "https://pokemonkorea.co.kr/news/2"
        self.assertEqual((current,), multi_route_event_discovery.OFFICIAL_ROUTES[("포켓몬 카드", "KR")])
        pages = {row[:2]: row[2] for row in social_event_discovery.OFFICIAL_DISCOVERY_PAGES}
        self.assertEqual(current, pages[("포켓몬 카드", "KR")])
        self.assertIn("pokemoncard.co.kr", social_event_discovery.OFFICIAL_HOSTS)
        self.assertIn("pokemonkorea.co.kr", social_event_discovery.OFFICIAL_HOSTS)
        self.assertNotIn("new.pokemonkorea.co.kr", social_event_discovery.OFFICIAL_HOSTS)
        tracker = next(row for row in update_promo_events.KR_MOVIE_TRACKERS if row["game"] == "포켓몬 카드")
        self.assertEqual(current, tracker["source"])

    def test_event_and_link_audit_recovery_uses_current_official_hosts(self):
        home = "https://pokemonkorea.co.kr/"
        news = "https://pokemonkorea.co.kr/news/2"
        self.assertEqual(update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS["https://pokemoncard.co.kr/main"], news)
        self.assertEqual(update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS["https://pokemonkorea.co.kr/"], home)
        self.assertEqual(validate_external_links.FALLBACKS["pokemoncard.co.kr"], home)
        self.assertEqual(validate_external_links.FALLBACKS["pokemonkorea.co.kr"], home)


if __name__ == "__main__":
    unittest.main()
