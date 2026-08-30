#!/usr/bin/env python3
import unittest
from unittest.mock import patch

import multi_route_event_discovery as routes
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
        with patch.object(social, "MAX_ITEMS", 10):
            merged = social.merge_candidates(rows)
        topics = {social._coverage_topic(row) for row in merged}
        self.assertTrue(set(routes.COVERAGE_TOPICS).issubset(topics))

    def test_brand_authority_is_not_shared_across_games(self):
        url = "https://www.naruto-cardgame.com/en/news/example.php"
        self.assertTrue(social._official_brand_host("나루토 카드", "US", url))
        self.assertFalse(social._official_brand_host("포켓몬 카드", "US", url))


if __name__ == "__main__":
    unittest.main()
