#!/usr/bin/env python3
import unittest
import auto_pipeline_runner
import collection_meta_learning as meta
import event_gap_learning as event_gap
import multi_channel_agent
import multi_route_event_discovery as routes
import provider_health_learning as health
import social_event_discovery as social

class SourceGapTaxonomyV8Tests(unittest.TestCase):
    def test_gap_matrix_tracks_153_cells(self):
        self.assertGreaterEqual(len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS), 153)
        self.assertEqual(len(health._expected_keys()), len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS))
        for topic in ("rules", "access"):
            self.assertIn(topic, health.TOPICS)
            self.assertIn(topic, routes.COVERAGE_TOPICS)
            self.assertIn(topic, meta.TOPICS)
            self.assertIn(topic, meta.SEARCH_TOPICS)
        self.assertGreaterEqual(event_gap.MAX_CELLS, 153)

    def test_rules_and_access_classification(self):
        samples = (
            ("금지/제한 카드 추가 및 에라타 안내", "rules"),
            ("Banned Restricted Cards legality update", "rules"),
            ("禁止カード・制限カード レギュレーション更新", "rules"),
            ("참가자격 체크인 플레이어 ID 덱리스트 안내", "access"),
            ("Spectator pass waitlist check-in Player ID", "access"),
            ("参加資格 チェックイン 入場券 キャンセル待ち", "access"),
        )
        for text, expected in samples:
            self.assertEqual(routes._topic(text), expected, text)
            self.assertEqual(health._topic({"title": text}), expected, text)
            self.assertEqual(event_gap._topic({"title": text}), expected, text)
            self.assertEqual(meta.classify_topic({"title": text}), expected, text)

    def test_query_families_and_broad_collectors_cover_new_terms(self):
        for lang in ("ko","ja","en"):
            self.assertIn("rules", routes.QUERY_FAMILIES[lang])
            self.assertIn("access", routes.QUERY_FAMILIES[lang])
        self.assertIn("규칙", multi_channel_agent.MultiChannelCollector.EVENT_OR["KR"])
        self.assertIn("禁止", multi_channel_agent.MultiChannelCollector.EVENT_OR["JP"])
        self.assertIn("legality", {x.lower() for x in multi_channel_agent.MultiChannelCollector.EVENT_OR["US"]})
        self.assertIn("RK9", multi_channel_agent.MultiChannelCollector.EVENT_OR["US"])

    def test_official_rules_and_play_pokemon_routes_are_directly_watched(self):
        pkm = routes.OFFICIAL_ROUTES[("포켓몬 카드","US")]
        self.assertTrue(any("play.pokemon.com/en-us/news" in u for u in pkm))
        self.assertTrue(any("support.play.pokemon.com" in u for u in pkm))
        self.assertTrue(any("community.pokemon.com" in u for u in pkm))
        for key in (("원피스 카드","KR"),("원피스 카드","JP"),("원피스 카드","US")):
            self.assertTrue(any("rules" in u for u in routes.OFFICIAL_ROUTES[key]), key)

    def test_registration_services_and_reddit_are_discovery_only(self):
        for host in ("rk9.gg","www.rk9.gg","playgo.bandainamcokorea.co.kr"):
            self.assertIn(host, routes.SERVICE_DISCOVERY_HOSTS)
            self.assertFalse(routes._official_for("포켓몬 카드","US",host))
        for host in ("reddit.com","www.reddit.com"):
            self.assertIn(host, routes.COMMUNITY_DISCOVERY_HOSTS)
            self.assertFalse(routes._official_for("원피스 카드","US",host))
        self.assertEqual(auto_pipeline_runner.SOCIAL_HOST_KIND["www.rk9.gg"], "rk9_registration_service_search")
        self.assertEqual(auto_pipeline_runner.SOCIAL_HOST_KIND["playgo.bandainamcokorea.co.kr"], "playgo_service_search")
        self.assertEqual(auto_pipeline_runner.SOCIAL_HOST_KIND["www.reddit.com"], "reddit_community_search")

    def test_adaptive_rows_never_promote_service_or_community_hits(self):
        blocks = [{
            "keyword":"포켓몬",
            "results":[
                {"url":"https://www.rk9.gg/event/pokemon","title":"Pokemon TCG spectator check-in waitlist","query_region":"US","search_provider":"bing_rss"},
                {"url":"https://www.reddit.com/r/pkmntcg/comments/x","title":"Pokemon TCG banned card rumor","query_region":"US","search_provider":"bing_rss"},
            ],
        }]
        rows = auto_pipeline_runner._adaptive_event_rows(blocks)
        by_host = {auto_pipeline_runner._host(r["source"]): r for r in rows}
        self.assertEqual(by_host["www.rk9.gg"]["source_tier"], "B-service")
        self.assertFalse(by_host["www.rk9.gg"]["verified"])
        self.assertEqual(by_host["www.reddit.com"]["source_tier"], "C-community")
        self.assertFalse(by_host["www.reddit.com"]["verified"])

    def test_social_and_keyword_filters_keep_rules_access_service_headlines(self):
        kr = social._game_query_terms("포켓몬 카드","KR")
        us = social._game_query_terms("포켓몬 카드","US")
        self.assertIn("규칙", kr)
        self.assertIn("체크인", kr)
        self.assertIn("legality", us.lower())
        self.assertIn("rk9", us.lower())
        for text in (
            "금지 제한 카드 에라타 사용 규정",
            "Spectator pass waitlist check-in RK9",
            "禁止カード 制限カード レギュレーション",
        ):
            self.assertIsNotNone(routes.KEYWORD_RE.search(text), text)

if __name__ == "__main__":
    unittest.main()
