#!/usr/bin/env python3
import urllib.parse
import unittest

import auto_pipeline_runner
import multi_channel_agent
import multi_route_event_discovery as routes
import provider_health_learning as health
import social_event_discovery as social


class SourceGapTaxonomyV6Tests(unittest.TestCase):
    def test_gap_matrix_tracks_117_cells(self):
        self.assertEqual(len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS), 117)
        self.assertEqual(len(health._expected_keys()), 117)
        for topic in ("stock", "entry", "broadcast"):
            self.assertIn(topic, health.TOPICS)
            self.assertIn(topic, routes.COVERAGE_TOPICS)

    def test_recent_official_announcement_shapes_are_classified(self):
        self.assertEqual(routes._topic("事前応募 抽選 当選発表 BANDAI TCG+ ENTRY"), "entry")
        self.assertEqual(routes._topic("ライブ配信 Twitch Drops 視聴コードを受け取る"), "broadcast")
        self.assertEqual(routes._topic("재입고 안내 현재 재고 품절 매장"), "stock")
        self.assertEqual(health._topic({"title": "Apply for event registration lottery"}), "entry")
        self.assertEqual(health._topic({"title": "Livestream reward code via Twitch Drops"}), "broadcast")
        self.assertEqual(health._topic({"title": "Sold out then restock at retailer"}), "stock")

    def test_keyword_filter_keeps_entry_broadcast_and_stock_headlines(self):
        for text in (
            "ENTRY 事前応募 抽選",
            "カードゲーム部門のライブ配信が決定 Twitch Drops",
            "재입고 및 품절 매장 안내",
        ):
            self.assertIsNotNone(routes.KEYWORD_RE.search(text), text)

    def test_query_families_include_new_time_sensitive_topics(self):
        for lang in ("ko", "ja", "en"):
            for topic in ("stock", "entry", "broadcast"):
                self.assertIn(topic, routes.QUERY_FAMILIES[lang])
        self.assertIn("응모", multi_channel_agent.MultiChannelCollector.EVENT_OR["KR"])
        self.assertIn("抽選", multi_channel_agent.MultiChannelCollector.EVENT_OR["JP"])
        self.assertIn("livestream", {x.lower() for x in multi_channel_agent.MultiChannelCollector.EVENT_OR["US"]})

    def test_x_query_terms_cover_application_and_live_reward_words(self):
        kr = social._game_query_terms("포켓몬 카드", "KR")
        jp = social._game_query_terms("원피스 카드", "JP")
        us = social._game_query_terms("나루토 카드", "US")
        self.assertIn("응모", kr)
        self.assertIn("추첨", kr)
        self.assertIn("応募", jp)
        self.assertIn("配信", jp)
        self.assertIn("registration", us.lower())
        self.assertIn("twitch", us.lower())

    def test_facebook_is_public_discovery_and_official_link_registry_capable(self):
        self.assertIn("www.facebook.com", social.SOCIAL_HOSTS)
        self.assertEqual(
            social._parse_social_link("https://www.facebook.com/NarutoCardGame"),
            ("facebook", "NarutoCardGame"),
        )
        self.assertEqual(auto_pipeline_runner.SOCIAL_HOST_KIND["www.facebook.com"], "facebook_public_search")

    def test_public_social_fallback_queries_facebook_without_network(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc, tb):
                return False
            def read(self, _limit):
                return b""

        def fake_urlopen(req, **_kwargs):
            captured["url"] = req.full_url
            return Response()

        original = social.safe_urlopen
        social.safe_urlopen = fake_urlopen
        try:
            rows, error = social._ddg_social_one("나루토 카드", "US", {"watch_accounts": []}, None)
        finally:
            social.safe_urlopen = original
        self.assertEqual(rows, [])
        self.assertIsNone(error)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(captured["url"]).query)["q"][0]
        self.assertIn("site:facebook.com", query)

    def test_unregistered_facebook_result_never_auto_verifies(self):
        rows = social._annotate_social_rows([
            {
                "game": "나루토 카드",
                "region": "US",
                "title": "NARUTO CARD GAME giveaway registration",
                "source": "https://www.facebook.com/randomcollector/posts/123",
                "source_kind": "facebook_public_search",
                "confidence": 0.61,
            }
        ], {"accounts": [], "watch_accounts": []})
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["verified"])
        self.assertFalse(rows[0]["official_account_verified"])
        self.assertTrue(rows[0]["fan_candidate"])
        self.assertEqual(rows[0]["source_tier"], "C-community")


if __name__ == "__main__":
    unittest.main()
