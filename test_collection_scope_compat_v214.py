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

    def test_retired_pokemon_korea_urls_canonicalize_by_current_source_role(self):
        self.assertEqual(
            update_purchase_sources.checked_url("https://pokemoncard.co.kr/"),
            update_purchase_sources.POKEMON_KR_PRODUCT_INDEX,
        )
        product = update_purchase_sources.normalize_source({
            "name": "포켓몬 카드 게임 코리아 제품",
            "region": "KR",
            "games": ["Pokemon"],
            "type": "official",
            "url": "https://new.pokemonkorea.co.kr/card",
            "original_url": "https://pokemoncard.co.kr/card/category/product",
        })
        shop = update_purchase_sources.normalize_source({
            "name": "포켓몬 공인 카드샵 안내",
            "region": "KR",
            "games": ["Pokemon"],
            "type": "official",
            "url": "https://new.pokemonkorea.co.kr/card",
            "original_url": "https://pokemoncard.co.kr/card/225",
        })
        self.assertEqual(product["url"], update_purchase_sources.POKEMON_KR_PRODUCT_INDEX)
        self.assertEqual(shop["url"], update_purchase_sources.POKEMON_KR_CARD_SHOP_DIRECTORY)
        self.assertIn("pokemonkorea.co.kr", update_purchase_sources.OFFICIAL_CHAIN_HOSTS["포켓몬 카드샵"])
        self.assertNotIn("new.pokemonkorea.co.kr", update_purchase_sources.OFFICIAL_CHAIN_HOSTS["포켓몬 카드샵"])

    def test_canonical_pokemon_korea_event_source_uses_current_news_index(self):
        current = "https://pokemonkorea.co.kr/news/2"
        self.assertEqual(update_promo_events.POKEMON_KR_EVENT_INDEX, current)
        self.assertIn(("KR", "포켓몬 카드", current), update_promo_events.INDEXES)
        tracker = next(row for row in update_promo_events.KR_MOVIE_TRACKERS if row["game"] == "포켓몬 카드")
        self.assertEqual(current, tracker["source"])
        self.assertEqual(current, tracker["collection_source"])
        self.assertNotIn("verification_source", tracker)
        self.assertNotIn("new.pokemonkorea.co.kr", update_promo_events.ALLOWED)

    def test_retired_event_sources_use_role_specific_current_evidence(self):
        expected = update_promo_events.POKEMON_KR_EVENT_INDEX
        for legacy in (
            "https://new.pokemonkorea.co.kr/card",
            "https://new.pokemonkorea.co.kr/card/",
            "https://new.pokemonkorea.co.kr/card/category/5",
            "https://pokemoncard.co.kr/card/category/5",
            "https://pokemonkorea.co.kr/",
            "https://www.pokemonkorea.co.kr/",
        ):
            self.assertEqual(update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[legacy], expected)
        self.assertEqual(
            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[
                "https://pokemonkorea.co.kr/2026_battle_tournament3"
            ],
            update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,
        )
        self.assertNotIn(
            update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,
            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS,
        )

    def test_auxiliary_discovery_routes_use_current_event_source(self):
        current = update_promo_events.POKEMON_KR_EVENT_INDEX
        self.assertEqual((current,), multi_route_event_discovery.OFFICIAL_ROUTES[("포켓몬 카드", "KR")])
        pages = {row[:2]: row[2] for row in social_event_discovery.OFFICIAL_DISCOVERY_PAGES}
        self.assertEqual(current, pages[("포켓몬 카드", "KR")])
        self.assertIn("pokemonkorea.co.kr", social_event_discovery.OFFICIAL_HOSTS)
        self.assertNotIn("new.pokemonkorea.co.kr", social_event_discovery.OFFICIAL_HOSTS)

    def test_link_audit_uses_role_safe_current_fallbacks(self):
        product = update_purchase_sources.POKEMON_KR_PRODUCT_INDEX
        self.assertEqual(validate_external_links.FALLBACKS["pokemoncard.co.kr"], product)
        self.assertEqual(validate_external_links.FALLBACKS["www.pokemoncard.co.kr"], product)
        self.assertNotIn("pokemonkorea.co.kr", validate_external_links.FALLBACKS)
        self.assertNotIn("www.pokemonkorea.co.kr", validate_external_links.FALLBACKS)
        self.assertNotIn(
            "new.pokemonkorea.co.kr",
            " ".join(validate_external_links.FALLBACKS.values()),
        )

if __name__ == "__main__":
    unittest.main()
