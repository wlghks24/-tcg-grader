import unittest
import urllib.error
from pathlib import Path

import release_history_backfill as backfill
import multi_route_event_discovery as multi_route
import social_event_discovery as social
import update_promo_events as promo
import update_purchase_sources as purchase
import validate_external_links as link_audit


STABLE_NEWS = "https://pokemonkorea.co.kr/news/2"
STABLE_HOME = "https://pokemonkorea.co.kr/"


class PokemonKrOfficialAliasRecoveryV387Tests(unittest.TestCase):
    def test_release_backfill_prefers_same_company_live_alias(self):
        self.assertEqual(STABLE_NEWS, backfill.POKEMON_KR_INDEXES[0])
        self.assertEqual("https://new.pokemonkorea.co.kr/card/category/3", backfill.POKEMON_KR_INDEXES[1])

    def test_retired_release_index_failure_does_not_poison_live_alias(self):
        calls = []

        def fetch(url):
            calls.append(url)
            if url == STABLE_NEWS:
                return '<a href="/news/2/19432">MEGA 확장팩 「어비스아이」</a>'
            if url == STABLE_NEWS + "/19432":
                return 'MEGA 확장팩 「어비스아이」 발매일 2026-06-26 가격 1,500원'
            raise urllib.error.HTTPError(url, 410, "Gone", {}, None)

        rows, errors = backfill._collect_pokemon_region_details(fetch, lambda value: value, "KR")
        self.assertEqual([], errors)
        self.assertTrue(any(row.get("release_date") == "2026-06-26" for row in rows))
        self.assertIn(STABLE_NEWS, calls)
        self.assertIn("https://new.pokemonkorea.co.kr/card/category/3", calls)

    def test_promo_sources_use_only_approved_same_company_alias(self):
        self.assertIn("new.pokemonkorea.co.kr", promo.ALLOWED)
        self.assertEqual(STABLE_NEWS, promo.INDEXES[2][2])
        self.assertEqual(
            "https://pokemoncard.co.kr/card/969",
            promo.canonical_pokemon_kr_card_url("https://pokemoncard.co.kr/card/969"),
        )
        self.assertEqual(
            STABLE_NEWS,
            promo.canonical_pokemon_kr_card_url("https://pokemoncard.co.kr/main"),
        )
        self.assertEqual(
            STABLE_NEWS,
            promo._pokemon_kr_same_company_event_index("https://new.pokemonkorea.co.kr/card/969"),
        )
        self.assertIsNone(
            promo._pokemon_kr_same_company_event_index("https://example.com/card/969")
        )

    def test_purchase_persisted_main_urls_migrate_to_live_alias(self):
        self.assertEqual(
            STABLE_HOME,
            purchase.CANONICAL_URLS["https://pokemoncard.co.kr/main"],
        )
        self.assertEqual(
            STABLE_HOME,
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
        self.assertEqual(STABLE_HOME, normalized["url"])

    def test_purchase_cardshop_official_host_allowlist_is_narrow(self):
        hosts = purchase.OFFICIAL_CHAIN_HOSTS["포켓몬 카드샵"]
        self.assertIn("pokemonkorea.co.kr", hosts)
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
        self.assertEqual(STABLE_HOME, normalized["url"])
        self.assertEqual(STABLE_HOME, normalized["official_reference_url"])
        self.assertFalse(normalized["inventory_verified"])

    def test_all_active_kr_discovery_and_link_recovery_routes_use_live_alias(self):
        self.assertEqual((STABLE_NEWS,), multi_route.OFFICIAL_ROUTES[("포켓몬 카드", "KR")])
        pages = {row[:2]: row[2] for row in social.OFFICIAL_DISCOVERY_PAGES}
        self.assertEqual(STABLE_NEWS, pages[("포켓몬 카드", "KR")])
        self.assertIn("new.pokemonkorea.co.kr", social.OFFICIAL_HOSTS)
        for host in (
            "new.pokemonkorea.co.kr",
            "pokemoncard.co.kr",
            "www.pokemoncard.co.kr",
            "pokemonkorea.co.kr",
            "www.pokemonkorea.co.kr",
        ):
            self.assertEqual(STABLE_HOME, link_audit.FALLBACKS[host])
        self.assertEqual(
            "https://pokemoncard.co.kr/card/969",
            link_audit._canonicalize_retired_pokemon_kr_url(
                "https://pokemoncard.co.kr/card/969"
            ),
        )
        self.assertEqual(
            STABLE_HOME,
            link_audit._canonicalize_retired_pokemon_kr_url("https://new.pokemonkorea.co.kr/card"),
        )
        self.assertEqual(
            "https://example.com/card/969",
            link_audit._canonicalize_retired_pokemon_kr_url(
                "https://example.com/card/969"
            ),
        )

    def test_no_verification_threshold_or_cross_company_fallback_is_added(self):
        promo_text = Path("update_promo_events.py").read_text(encoding="utf-8")
        purchase_text = Path("update_purchase_sources.py").read_text(encoding="utf-8")
        release_text = Path("release_history_backfill.py").read_text(encoding="utf-8")
        for text in (promo_text, purchase_text, release_text):
            self.assertNotIn("fail-on-degraded=false", text)
            self.assertNotIn("allow_unverified", text)
        self.assertNotIn("example.com", " ".join(backfill.POKEMON_KR_INDEXES))
        self.assertNotIn("example.com", " ".join(promo.ALLOWED))


if __name__ == "__main__":
    unittest.main(verbosity=2)
