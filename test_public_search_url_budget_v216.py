import unittest
import urllib.parse

import collection_learning_hardening_v144 as v144
import multi_route_event_discovery as routes
import social_event_discovery as social
from safe_runtime import validate_public_https_url


class _FanLearner:
    def preferred_authors(self, game, region, limit=6):
        return [f"collector_{region.lower()}_{i}" for i in range(limit)]


class _GapLearner:
    def top_terms_for_region(self, game, region, limit=8):
        base = ("limited promo", "official announcement", "special event", "registration deadline",
                "participant reward", "exclusive card", "restock notice", "tournament result")
        return base[:limit]


class PublicSearchUrlBudgetV216Tests(unittest.TestCase):
    def test_bing_reproduced_kr_social_case_fits_budget(self):
        query, url = routes._bounded_bing_request(
            "포켓몬 카드", "KR", hosts=routes.SOCIAL_DISCOVERY_HOSTS
        )
        self.assertIn("포켓몬", query)
        self.assertLessEqual(len(url), routes.MAX_PUBLIC_SEARCH_URL_CHARS)
        validate_public_https_url(url, routes.BING_HOSTS)

    def test_bing_all_core_broad_route_families_fit_budget(self):
        for game in routes.GAMES:
            for region in routes.REGIONS:
                groups = (
                    routes.SOCIAL_DISCOVERY_HOSTS,
                    routes.SERVICE_DISCOVERY_HOSTS,
                    routes.COMMUNITY_DISCOVERY_HOSTS,
                    tuple(routes.PARTNER_DOMAINS.get((game, region), ())),
                    tuple(routes.PRESS_DOMAINS.get(region, ())),
                )
                for hosts in groups:
                    if not hosts:
                        continue
                    with self.subTest(game=game, region=region, hosts=hosts[:2]):
                        _, url = routes._bounded_bing_request(game, region, hosts=tuple(hosts))
                        self.assertLessEqual(len(url), routes.MAX_PUBLIC_SEARCH_URL_CHARS)
                        validate_public_https_url(url, routes.BING_HOSTS)

    def test_broad_query_keeps_required_high_value_families(self):
        q = routes._query("포켓몬 카드", "KR")
        self.assertIn("출시", q)
        self.assertIn("프로모", q)
        self.assertIn("재입고", q)
        self.assertIn("이벤트", q)

    def test_google_news_all_game_region_urls_fit_budget(self):
        for game in social.GAMES:
            for region in social.REGION_LANG:
                with self.subTest(game=game, region=region):
                    url = social._google_news_url(game, region)
                    self.assertLessEqual(len(url), social.MAX_PUBLIC_SEARCH_URL_CHARS)
                    validate_public_https_url(url, social.GOOGLE_NEWS_HOSTS)

    def test_v144_social_query_with_watch_and_learned_terms_fits_budget(self):
        registry = {
            "watch_accounts": [
                {
                    "game": "포켓몬 카드",
                    "region": "KR",
                    "content_regions": ["KR"],
                    "trusted": False,
                    "role": "collector community watch",
                    "username": f"pokemon_watch_{i}",
                }
                for i in range(10)
            ]
        }
        query = v144.build_public_social_query(
            "포켓몬 카드", "KR", registry, _FanLearner(), _GapLearner()
        )
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        self.assertLessEqual(len(url), v144.MAX_PUBLIC_SEARCH_URL_CHARS)
        self.assertIn("site:x.com", query)
        self.assertIn("site:instagram.com", query)
        self.assertIn("포켓몬", query)
        validate_public_https_url(url, social.DDG_HOSTS)

    def test_cross_region_multilingual_anchors_survive_url_budget(self):
        class GapLearner:
            def top_terms_for_region(self, game, region, limit=8):
                return ("Nike", "応募者全員サービス")

        registry = {
            "watch_accounts": [{
                "game": "원피스 카드",
                "region": "JP",
                "content_regions": ["JP", "KR"],
                "trusted": False,
                "role": "collector community watch",
                "username": "onepiececard_news",
            }]
        }
        query = v144.build_public_social_query(
            "원피스 카드", "JP", registry, fan_learner=None, gap_learner=GapLearner()
        )
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        self.assertIn("onepiececard_news", query)
        self.assertIn("응모", query)
        self.assertIn("応募", query)
        self.assertIn("application", query)
        self.assertIn("Nike", query)
        self.assertLessEqual(len(url), v144.MAX_PUBLIC_SEARCH_URL_CHARS)

    def test_diagnostics_preserve_valueerror_reason_without_bypass(self):
        summary = routes._error_summary("Bing social 포켓몬 카드/KR", ValueError("invalid url"))
        self.assertIn("ValueError", summary)
        self.assertIn("invalid url", summary)
        self.assertNotIn("bypass", summary.lower())


if __name__ == "__main__":
    unittest.main()
