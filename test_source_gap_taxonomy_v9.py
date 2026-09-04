#!/usr/bin/env python3
import unittest
import collection_meta_learning as meta
import event_gap_learning as event_gap
import multi_channel_agent
import multi_route_event_discovery as routes
import provider_health_learning as health
import social_event_discovery as social

class SourceGapTaxonomyV9Tests(unittest.TestCase):
    def test_gap_matrix_tracks_at_least_180_cells(self):
        total = len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS)
        self.assertGreaterEqual(total, 180)
        self.assertEqual(len(health._expected_keys()), total)
        for topic in ("results", "purchase_policy", "service_status"):
            self.assertIn(topic, health.TOPICS)
            self.assertIn(topic, routes.COVERAGE_TOPICS)
            self.assertIn(topic, meta.TOPICS)
            self.assertIn(topic, meta.SEARCH_TOPICS)
        self.assertGreaterEqual(event_gap.MAX_CELLS, total)

    def test_real_official_announcement_shapes_classify(self):
        samples = (
            ("2026 Pokémon World Championships Event Results top finishers final standings", "results"),
            ("대회 결과 발표 우승자 발표 최종 순위 우승 덱", "results"),
            ("大会結果 優勝者発表 最終順位 優勝デッキ", "results"),
            ("추첨 판매 본인 인증 구매 제한 가상 대기열", "purchase_policy"),
            ("抽選販売 本人認証 購入制限 購入券", "purchase_policy"),
            ("limited to one item per person purchase ticket valid on event day", "purchase_policy"),
            ("플레이어즈 클럽 로그인 불가 서비스 장애 복구 완료", "service_status"),
            ("プレイヤーズクラブ メンテナンス 不具合 復旧", "service_status"),
            ("service outage login issue resolved", "service_status"),
        )
        for text, expected in samples:
            self.assertEqual(routes._topic(text), expected, text)
            self.assertEqual(health._topic({"title": text}), expected, text)
            self.assertEqual(event_gap._topic({"title": text}), expected, text)
            self.assertEqual(meta.classify_topic({"title": text}), expected, text)

    def test_purchase_lottery_does_not_fall_into_event_entry(self):
        text = "30th product lottery sale identity verification purchase limit"
        self.assertEqual(routes._topic(text), "purchase_policy")
        self.assertEqual(health._topic({"title": text}), "purchase_policy")
        self.assertNotEqual(meta.classify_topic({"title": text}), "entry")

    def test_query_families_and_multichannel_cover_new_topics(self):
        for lang in ("ko", "ja", "en"):
            for topic in ("results", "purchase_policy", "service_status"):
                self.assertIn(topic, routes.QUERY_FAMILIES[lang])
        self.assertIn("대회결과", multi_channel_agent.MultiChannelCollector.EVENT_OR["KR"])
        self.assertIn("メンテナンス", multi_channel_agent.MultiChannelCollector.EVENT_OR["JP"])
        self.assertIn("purchase limit", {x.lower() for x in multi_channel_agent.MultiChannelCollector.EVENT_OR["US"]})

    def test_pokemon_results_support_routes_are_directly_watched(self):
        urls = routes.OFFICIAL_ROUTES[("포켓몬 카드", "US")]
        self.assertTrue(any("championship-series-event-results" in u for u in urls))
        self.assertTrue(any("support.pokemon.com" in u for u in urls))
        self.assertTrue(routes._official_for("포켓몬 카드", "US", "support.pokemon.com"))

    def test_social_and_keyword_filters_keep_new_shapes(self):
        ko = social._game_query_terms("포켓몬 카드", "KR")
        ja = social._game_query_terms("포켓몬 카드", "JP")
        en = social._game_query_terms("나루토 카드", "US")
        self.assertIn("대회결과", ko)
        self.assertIn("メンテナンス", ja)
        self.assertIn("purchase limit", en.lower())
        for text in (
            "대회결과 우승자발표 최종순위",
            "抽選販売 購入制限 本人認証",
            "service outage login issue resolved",
        ):
            self.assertIsNotNone(routes.KEYWORD_RE.search(text), text)

    def test_priority_marks_service_and_purchase_gaps_urgent(self):
        data = health._fresh()
        for topic in ("service_status", "purchase_policy", "results"):
            key = f"포켓몬 카드/US/{topic}"
            data["coverage_cells"][key] = {
                "last_candidate_count": 0,
                "last_verified_count": 0,
                "miss_streak": 1,
                "verification_gap_streak": 0,
                "discovery_gap_streak": 1,
                "misses": 1,
            }
        report = health._coverage_report(data)
        priorities = {r["cell"]: r["priority"] for r in report["next_priority_cells"]}
        self.assertGreater(priorities["포켓몬 카드/US/service_status"], priorities["포켓몬 카드/US/results"])
        self.assertGreater(priorities["포켓몬 카드/US/purchase_policy"], priorities["포켓몬 카드/US/results"])

if __name__ == "__main__":
    unittest.main()
