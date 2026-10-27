#!/usr/bin/env python3
import unittest
from unittest.mock import patch

import multi_route_event_discovery as routes
import update_promo_events as promo
import social_event_discovery as social


class SocialEventTopicCoverageTests(unittest.TestCase):
    def test_rare_topics_survive_global_candidate_cap(self):
        rows = []
        for index, topic in enumerate(routes.COVERAGE_TOPICS):
            rows.append({
                "game": "포켓몬 카드", "region": "KR", "category": "promo",
                "topic": topic, "title": f"포켓몬 {topic} 카드 행사 {index}",
                "source": f"https://example.com/rare/{index}",
                "source_kind": "test", "confidence": 0.46,
            })
        for index in range(30):
            rows.append({
                "game": "포켓몬 카드", "region": "KR", "category": "promo",
                "topic": "release", "title": f"포켓몬 출시 카드 행사 대량 {index}",
                "source": f"https://example.com/common/{index}",
                "source_kind": "test", "confidence": 0.99,
            })
        with patch.object(social, "MAX_ITEMS", len(routes.COVERAGE_TOPICS)):
            merged = social.merge_candidates(rows)
        topics = {social._coverage_topic(row) for row in merged}
        self.assertTrue(set(routes.COVERAGE_TOPICS).issubset(topics))

        # A configured cap smaller than the topic matrix is now only a soft cap.
        # Completeness wins: one populated lead per topic cell must not be evicted.
        with patch.object(social, "MAX_ITEMS", 10):
            capped = social.merge_candidates(rows)
        capped_topics = {social._coverage_topic(row) for row in capped}
        self.assertGreaterEqual(len(capped), len(routes.COVERAGE_TOPICS))
        self.assertTrue(set(routes.COVERAGE_TOPICS).issubset(capped_topics))
        self.assertGreaterEqual(social.candidate_limit(), social.TOPIC_MATRIX_MIN_ITEMS)

    def test_brand_authority_is_not_shared_across_games(self):
        url = "https://www.naruto-cardgame.com/en/news/example.php"
        self.assertTrue(social._official_brand_host("나루토 카드", "US", url))
        self.assertFalse(social._official_brand_host("포켓몬 카드", "US", url))


    def test_registry_global_event_can_be_rendered_without_region_keyerror(self):
        """Global official roots must remain discoverable without inventing locality."""
        global_indexes = [row for row in promo.INDEXES if row[0] == "GLOBAL"]
        self.assertTrue(global_indexes, "expanded verified registry requires GLOBAL")
        html = (
            '<a href="/events/global-2026">'
            '2026-10-10 Trading Card Tournament 2026-10-11'
            '</a>'
        )
        with patch.object(promo, "fetch", return_value=html), \
             patch.object(promo, "date_range", return_value=("2026-10-10", "2026-10-11")):
            rows, errors = promo.discover(global_indexes[0])
        self.assertEqual([], errors)
        self.assertEqual(1, len(rows))
        self.assertEqual("GLOBAL", rows[0]["region"])
        self.assertIn("글로벌 공식 행사", rows[0]["name_ko"])
        self.assertIn("개최지역 확인 필요", rows[0]["location"])
        self.assertTrue(promo.valid(rows[0]))


    def test_scraped_css_rule_is_never_an_event(self):
        css = ".css-1od4a9n{width:24px;height:24px;filter:drop-shadow(0 0 2px #333)}"
        self.assertTrue(social._css_noise(css))
        row = {
            "game": "나루토 카드", "region": "JP", "category": "event",
            "topic": "event", "source": "https://naruto-official.com/news",
            "source_kind": "official_web", "title": css,
            "excerpt": "대회 공식 일정 공지", "confidence": 0.94, "verified": True,
        }
        self.assertEqual([], social.merge_candidates([row]))

    def test_benign_css_word_is_not_rejected(self):
        self.assertFalse(social._css_noise("카드 행사에서 CSS 디자인 적용 사례"))
        self.assertTrue(social._css_noise(":root { --brand: #fff; }"))
        self.assertTrue(social._css_noise("<style>.css-abc{display:none}</style>"))

    def test_css_excerpt_is_removed_but_legitimate_event_retained(self):
        row = {
            "game": "나루토 카드", "region": "JP", "category": "event",
            "topic": "event", "source": "https://naruto-official.com/news",
            "source_kind": "official_web", "title": "나루토 카드 공식 행사",
            "excerpt": ".css-a1b2{font-size:20px}",
            "confidence": 0.94, "verified": True,
        }
        items = social.merge_candidates([row])
        self.assertEqual(1, len(items))
        self.assertEqual("", items[0]["excerpt"])

    def test_bad_verified_historical_candidate_is_quarantined(self):
        css = ".css-1od4a9n{width:24px}"
        previous = {
            "items": [
                {"game": "나루토 카드", "region": "JP", "title": css, "verified": True},
                {"game": "나루토 카드", "region": "JP", "title": "나루토 공식 이벤트", "verified": True},
            ]
        }
        clean = social._previous_rows(previous)
        self.assertEqual(1, len(clean))
        self.assertEqual("나루토 공식 이벤트", clean[0]["title"])


if __name__ == "__main__":
    unittest.main()
