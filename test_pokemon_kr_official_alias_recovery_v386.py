import unittest
import urllib.error

import release_history_backfill as backfill
import multi_route_event_discovery as multi_route
import social_event_discovery as social
import update_promo_events as promo
import update_purchase_sources as purchase
import validate_external_links as link_audit


LIVE_ALIAS = "https://new.pokemonkorea.co.kr/card"


class PokemonKrOfficialAliasRecoveryV386Tests(unittest.TestCase):
    def test_release_backfill_prefers_same_company_live_alias(self):
        self.assertEqual(LIVE_ALIAS, backfill.POKEMON_KR_INDEXES[0])
        self.assertEqual("https://pokemoncard.co.kr/card", backfill.POKEMON_KR_INDEXES[1])

    def test_retired_release_index_failure_does_not_poison_live_alias(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if url == LIVE_ALIAS:
                return '<a href="/card/907">MEGA 확장팩 「어비스아이」</a>'
            if url == LIVE_ALIAS + "/907":
                return 'MEGA 확장팩 「어비스아이」 발매일 2026-06-26 가격 1,500원'
            raise urllib.error.HTTPError(url, 410, "Gone", {}, None)

        rows, errors = backfill._collect_pokemon_region_details(fetch, lambda value: value, "KR")
        self.assertEqual([], errors)
        self.assertTrue(any(row.get("release_date") == "2026-06-26" for row in rows))
        self.assertIn(LIVE_ALIAS, calls)
        self.assertIn("https://pokemoncard.co.kr/card", calls)

    def test_promo_sources_use_only_approved_same_company_alias(self):
        self.assertIn("new.pokemonkorea.co.kr", promo.ALLOWED)
        self.assertEqual(LIVE_ALIAS, promo.INDEXES[2][2])
        self.assertEqual(
            LIVE_ALIAS + "/969",
            promo.canonical_pokemon_kr_card_url("https://pokemoncard.co.kr/card/969"),
        )
        self.assertEqual(
            LIVE_ALIAS,
            promo.canonical_pokemon_kr_card_url("https://pokemoncard.co.kr/main"),
        )
        self.assertEqual(
            LIVE_ALIAS,
            promo._pokemon_kr_same_company_event_index(LIVE_ALIAS + "/969"),
        )
        self.assertIsNone(
            promo._pokemon_kr_same_company_event_index("https://example.com/card/969")
        )

    def test_purchase_persisted_main_urls_migrate_to_live_alias(self):
        self.assertEqual(
            LIVE_ALIAS,
            purchase.CANONICAL_URLS["https://pokemoncard.co.kr/main"],
        )
        self.assertEqual(
            LIVE_ALIAS,
            purchase.CANONICAL_URLS["https://www.pokemoncard.co.kr/main"],
        )
        source = {
            "name": "포켓몬 카드 게임 코리아 제품",
            "region": "KR",
            "games": ["Pokemon"],
            "type": "official",
            "url": "https://pokemoncard.co.kr/main",
            "note": "한국 공식 제품·출시정보",
        }
        normalized = purchase.normalize_source(source)
        self.assertEqual(LIVE_ALIAS, normalized["url"])

    def test_purchase_cardshop_official_host_allowlist_is_narrow(self):
        hosts = purchase.OFFICIAL_CHAIN_HOSTS["포켓몬 카드샵"]
        self.assertIn("new.pokemonkorea.co.kr", hosts)
        self.assertNotIn("example.com", hosts)
        source = {
            "name": "포켓몬 카드 전문점 공식 매장 안내",
            "region": "KR",
            "games": ["Pokemon", "ONE PIECE", "NARUTO"],
            "type": "official",
            "channel": "offline",
            "retailer_category": "cardshop",
            "chain": "포켓몬 카드샵",
            "url": "https://pokemoncard.co.kr/main",
            "official_reference_url": "https://pokemoncard.co.kr/main",
        }
        normalized = purchase.normalize_source(source)
        self.assertEqual(LIVE_ALIAS, normalized["url"])
        self.assertEqual(LIVE_ALIAS, normalized["official_reference_url"])
        self.assertFalse(normalized["inventory_verified"])

    def test_all_active_kr_discovery_and_link_recovery_routes_use_live_alias(self):
        self.assertEqual((LIVE_ALIAS,), multi_route.OFFICIAL_ROUTES[("포켓몬 카드", "KR")])
        pages = {row[:2]: row[2] for row in social.OFFICIAL_DISCOVERY_PAGES}
        self.assertEqual(LIVE_ALIAS, pages[("포켓몬 카드", "KR")])
        self.assertIn("new.pokemonkorea.co.kr", social.OFFICIAL_HOSTS)
        for host in (
            "new.pokemonkorea.co.kr",
            "pokemoncard.co.kr",
            "www.pokemoncard.co.kr",
            "pokemonkorea.co.kr",
            "www.pokemonkorea.co.kr",
        ):
            self.assertEqual(LIVE_ALIAS, link_audit.FALLBACKS[host])
        self.assertEqual(
            LIVE_ALIAS + "/969",
            link_audit._canonicalize_retired_pokemon_kr_url(
                "https://pokemoncard.co.kr/card/969"
            ),
        )
        self.assertEqual(
            LIVE_ALIAS,
            link_audit._canonicalize_retired_pokemon_kr_url(LIVE_ALIAS),
        )
        self.assertEqual(
            "https://example.com/card/969",
            link_audit._canonicalize_retired_pokemon_kr_url(
                "https://example.com/card/969"
            ),
        )

    def test_no_verification_threshold_or_cross_company_fallback_is_added(self):
        promo_text = open("update_promo_events.py", encoding="utf-8").read()
        purchase_text = open("update_purchase_sources.py", encoding="utf-8").read()
        release_text = open("release_history_backfill.py", encoding="utf-8").read()
        for text in (promo_text, purchase_text, release_text):
            self.assertNotIn("fail-on-degraded=false", text)
            self.assertNotIn("allow_unverified", text)
        self.assertNotIn("example.com", " ".join(backfill.POKEMON_KR_INDEXES))
        self.assertNotIn("example.com", " ".join(promo.ALLOWED))


if __name__ == "__main__":
    unittest.main(verbosity=2)
