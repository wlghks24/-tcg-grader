#!/usr/bin/env python3
import unittest

import auto_pipeline_runner
import collection_meta_learning as meta
import event_gap_learning as event_gap
import multi_channel_agent
import multi_route_event_discovery as routes
import provider_health_learning as health
import social_event_discovery as social


class SourceGapTaxonomyV7Tests(unittest.TestCase):
    def test_gap_matrix_tracks_135_cells(self):
        self.assertGreaterEqual(len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS), 135)
        self.assertEqual(len(health._expected_keys()), len(health.GAMES) * len(health.REGIONS) * len(health.TOPICS))
        for topic in ("stock", "entry", "broadcast", "deadline", "status_update"):
            self.assertIn(topic, health.TOPICS)
            self.assertIn(topic, routes.COVERAGE_TOPICS)
        self.assertGreaterEqual(event_gap.MAX_CELLS, 135)

    def test_deadline_and_status_updates_win_before_generic_entry(self):
        samples = (
            ("신청 마감 2026년 9월 6일", "deadline"),
            ("応募締切 2026年9月6日 BANDAI TCG+", "deadline"),
            ("Application deadline September 6, 2026", "deadline"),
            ("카드베이스 부산 개최 취소 및 시간 변경", "status_update"),
            ("開催中止・会場変更のお知らせ", "status_update"),
            ("Event postponed and schedule changed", "status_update"),
        )
        for text, expected in samples:
            self.assertEqual(routes._topic(text), expected, text)
            self.assertEqual(health._topic({"title": text}), expected, text)

    def test_event_gap_learning_understands_all_time_sensitive_topics(self):
        samples = (
            ({"title": "재입고 및 품절 안내"}, "stock"),
            ({"title": "사전 신청 추첨 등록"}, "entry"),
            ({"title": "라이브 방송 Twitch Drops 코드"}, "broadcast"),
            ({"title": "접수 마감 기한 안내"}, "deadline"),
            ({"title": "행사 취소 일정 변경"}, "status_update"),
        )
        for row, expected in samples:
            self.assertEqual(event_gap._topic(row), expected)

    def test_meta_learner_tracks_v6_and_v7_topics(self):
        for topic in ("stock", "entry", "broadcast", "deadline", "status_update"):
            self.assertIn(topic, meta.TOPICS)
            self.assertIn(topic, meta.SEARCH_TOPICS)
        self.assertEqual(meta.classify_topic({"title": "registration deadline closes tomorrow"}), "deadline")
        self.assertEqual(meta.classify_topic({"title": "event cancelled and rescheduled"}), "status_update")
        self.assertEqual(meta.classify_topic({"title": "Twitch Drops livestream reward"}), "broadcast")
        self.assertEqual(meta.classify_topic({"title": "lottery registration entry"}), "entry")

    def test_query_families_cover_deadline_change_and_service_names(self):
        expectations = {
            "ko": ("마감", "취소", "LINE", "TCG+"),
            "ja": ("締切", "中止", "LINE", "TCG+"),
            "en": ("deadline", "cancel", "LINE", "TCG+"),
        }
        for lang, needles in expectations.items():
            joined = " ".join(routes.QUERY_FAMILIES[lang].values())
            for needle in needles:
                self.assertIn(needle.lower(), joined.lower())
        self.assertIn("마감", multi_channel_agent.MultiChannelCollector.EVENT_OR["KR"])
        self.assertIn("変更", multi_channel_agent.MultiChannelCollector.EVENT_OR["JP"])
        self.assertIn("deadline", {x.lower() for x in multi_channel_agent.MultiChannelCollector.EVENT_OR["US"]})

    def test_social_queries_include_deadline_status_and_service_terms(self):
        kr = social._game_query_terms("포켓몬 카드", "KR")
        jp = social._game_query_terms("원피스 카드", "JP")
        us = social._game_query_terms("나루토 카드", "US")
        self.assertIn("마감", kr)
        self.assertIn("취소", kr)
        self.assertIn("締切", jp)
        self.assertIn("変更", jp)
        self.assertIn("deadline", us.lower())
        self.assertIn("cancel", us.lower())
        self.assertIn("tcg+", us.lower())

    def test_service_and_community_hosts_are_discovery_only(self):
        for host in ("lin.ee", "line.me", "bandai-tcg-plus.com", "www.bandai-tcg-plus.com"):
            self.assertIn(host, routes.SERVICE_DISCOVERY_HOSTS)
        for host in ("namu.wiki", "www.namu.wiki", "namu.moe", "www.namu.moe"):
            self.assertIn(host, routes.COMMUNITY_DISCOVERY_HOSTS)
            self.assertFalse(routes._official_for("포켓몬 카드", "KR", host))
        self.assertEqual(auto_pipeline_runner.SOCIAL_HOST_KIND["lin.ee"], "line_official_service_search")
        self.assertEqual(auto_pipeline_runner.SOCIAL_HOST_KIND["www.bandai-tcg-plus.com"], "bandai_tcg_plus_service_search")
        self.assertEqual(auto_pipeline_runner.SOCIAL_HOST_KIND["namu.wiki"], "namuwiki_community_search")

    def test_keyword_filter_keeps_deadline_status_and_service_headlines(self):
        for text in (
            "応募締切 BANDAI TCG+ 事前応募",
            "LINE 大会登録 期限",
            "행사 취소 및 시간 변경 공지",
            "Event postponed registration deadline",
        ):
            self.assertIsNotNone(routes.KEYWORD_RE.search(text), text)


if __name__ == "__main__":
    unittest.main()
