from __future__ import annotations

import unittest

import multi_route_event_discovery as routes
import social_event_discovery as social


class SocialTopicCapacityV213Tests(unittest.TestCase):
    def test_candidate_limit_can_preserve_one_lead_per_topic_cell(self):
        self.assertGreaterEqual(social.candidate_limit(), social.TOPIC_MATRIX_MIN_ITEMS)
        self.assertEqual(
            social.TOPIC_MATRIX_MIN_ITEMS,
            len(social.GAMES) * len(social.REGION_LANG) * len(routes.COVERAGE_TOPICS),
        )

    def test_full_topic_matrix_is_not_truncated_by_old_100_item_cap(self):
        rows = []
        counter = 0
        for game in social.GAMES:
            for region in social.REGION_LANG:
                for topic in routes.COVERAGE_TOPICS:
                    counter += 1
                    rows.append({
                        "game": game,
                        "region": region,
                        "category": "promo",
                        "topic": topic,
                        "title": f"{game} {region} {topic} lead {counter}",
                        "source": f"https://example.com/{counter}",
                        "source_kind": "test",
                        "confidence": 0.5,
                    })
        merged = social.merge_candidates(rows)
        coverage = social.topic_coverage(merged)
        self.assertEqual(social.TOPIC_MATRIX_MIN_ITEMS, len(rows))
        self.assertGreaterEqual(len(merged), social.TOPIC_MATRIX_MIN_ITEMS)
        self.assertTrue(all(value >= 1 for value in coverage.values()))


if __name__ == "__main__":
    unittest.main()
