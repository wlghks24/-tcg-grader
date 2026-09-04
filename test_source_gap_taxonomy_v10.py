#!/usr/bin/env python3
import unittest

import collection_meta_learning as meta
import event_gap_learning as event_gap
import multi_channel_agent
import multi_route_event_discovery as routes
import provider_health_learning as health
import social_event_discovery as social


class SourceGapTaxonomyV10Tests(unittest.TestCase):
    def test_gap_matrix_tracks_at_least_207_cells(self):
        total = len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS)
        self.assertGreaterEqual(total, 207)
        self.assertEqual(len(health._expected_keys()), total)
        for topic in ("official_price", "product_issue", "authenticity_notice"):
            self.assertIn(topic, health.TOPICS)
            self.assertIn(topic, routes.COVERAGE_TOPICS)
            self.assertIn(topic, meta.TOPICS)
            self.assertIn(topic, meta.SEARCH_TOPICS)
        self.assertGreaterEqual(event_gap.MAX_CELLS, total)

    def test_real_official_notice_shapes_classify(self):
        samples = (
            ("일부 상품 가격 개정 및 희망 소비자 가격 변경 안내", "official_price"),
            ("一部商品価格改定のお知らせ 希望小売価格を改定", "official_price"),
            ("MSRP price increase update for new products", "official_price"),
            ("봉입 내용 오류 및 교환 대응 안내", "product_issue"),
            ("封入内容の誤りに関するお詫びと交換対応について", "product_issue"),
            ("manufacturing error incorrect contents product replacement", "product_issue"),
            ("위조품 가품 레플리카 구매 주의", "authenticity_notice"),
            ("偽造品に関する注意事項 模倣品 レプリカ", "authenticity_notice"),
            ("Did I purchase fake or counterfeit cards replica knockoff", "authenticity_notice"),
        )
        for text, expected in samples:
            self.assertEqual(routes._topic(text), expected, text)
            self.assertEqual(health._topic({"title": text}), expected, text)
            self.assertEqual(event_gap._topic({"title": text}), expected, text)
            self.assertEqual(meta.classify_topic({"title": text}), expected, text)

    def test_static_msrp_does_not_become_price_change(self):
        text = "NARUTO CARD GAME Official Playmat MSRP $35 plus tax limited quantities"
        self.assertNotEqual(routes._topic(text), "official_price")
        self.assertNotEqual(health._topic({"title": text}), "official_price")
        self.assertNotEqual(meta.classify_topic({"title": text}), "official_price")

    def test_product_issue_and_service_status_stay_separate(self):
        product = "カード商品の表面加工の誤り 交換対応"
        service = "プレイヤーズクラブ ログイン不具合 メンテナンス 復旧"
        for classifier in (
            lambda x: routes._topic(x),
            lambda x: health._topic({"title": x}),
            lambda x: event_gap._topic({"title": x}),
            lambda x: meta.classify_topic({"title": x}),
        ):
            self.assertEqual(classifier(product), "product_issue")
            self.assertEqual(classifier(service), "service_status")

    def test_official_price_wins_before_generic_market_price(self):
        text = "price revision announcement MSRP increase"
        self.assertEqual(meta.classify_topic({"title": text}), "official_price")
        self.assertEqual(meta.classify_topic({"title": "market price sold listing"}), "market")

    def test_query_families_and_multichannel_cover_new_topics(self):
        for lang in ("ko", "ja", "en"):
            for topic in ("official_price", "product_issue", "authenticity_notice"):
                self.assertIn(topic, routes.QUERY_FAMILIES[lang])
        self.assertIn("가격개정", multi_channel_agent.MultiChannelCollector.EVENT_OR["KR"])
        self.assertIn("偽造品", multi_channel_agent.MultiChannelCollector.EVENT_OR["JP"])
        self.assertIn("manufacturing error", {x.lower() for x in multi_channel_agent.MultiChannelCollector.EVENT_OR["US"]})
        self.assertIn("counterfeit", {x.lower() for x in multi_channel_agent.MultiChannelCollector.EVENT_OR["US"]})

    def test_pokemon_support_tcg_category_is_directly_watched(self):
        urls = routes.OFFICIAL_ROUTES[("포켓몬 카드", "US")]
        self.assertTrue(any("support.pokemon.com/hc/en-us/categories/" in u for u in urls))
        self.assertTrue(routes._official_for("포켓몬 카드", "US", "support.pokemon.com"))

    def test_social_and_keyword_filters_keep_new_shapes(self):
        ko = social._game_query_terms("포켓몬 카드", "KR")
        ja = social._game_query_terms("포켓몬 카드", "JP")
        en = social._game_query_terms("원피스 카드", "US")
        self.assertIn("가격개정", ko)
        self.assertIn("偽造品", ja)
        self.assertIn("manufacturing error", en.lower())
        self.assertIn("counterfeit", en.lower())
        for text in (
            "가격개정 희망소비자가격 변경",
            "封入内容の誤り 交換対応",
            "counterfeit fake cards scam warning",
        ):
            self.assertIsNotNone(routes.KEYWORD_RE.search(text), text)

    def test_priority_marks_authenticity_and_product_issues_urgent(self):
        data = health._fresh()
        for topic in ("authenticity_notice", "product_issue", "official_price"):
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
        self.assertGreater(priorities["포켓몬 카드/US/authenticity_notice"], priorities["포켓몬 카드/US/official_price"])
        self.assertGreater(priorities["포켓몬 카드/US/product_issue"], priorities["포켓몬 카드/US/official_price"])


if __name__ == "__main__":
    unittest.main()
