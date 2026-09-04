#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

import provider_health_learning as health


class ProviderSourceGapLearningV5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.memory = root / "collection_provider_health.json"
        self.backup = root / "collection_provider_health.json.bak"
        self.social = root / "social_event_candidates.json"
        self.supplementary = root / "supplementary_candidates.json"
        self.promo = root / "promo_events.json"
        self.social.write_text(json.dumps({"items": [], "channel_status": {}}, ensure_ascii=False), encoding="utf-8")
        self.supplementary.write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
        self.promo.write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def observe(self, provider_rows=None):
        return health.observe(
            provider_rows or [],
            memory_path=self.memory,
            backup_path=self.backup,
            social_path=self.social,
            supplementary_path=self.supplementary,
            promo_path=self.promo,
            rewrite_social_coverage=True,
        )

    def test_unverified_social_candidate_does_not_hide_verified_gap(self):
        key = "원피스 카드/KR/reprint"
        self.social.write_text(json.dumps({
            "items": [{
                "game": "원피스 카드",
                "region": "KR",
                "search_topic": "reprint",
                "title": "원피스 카드 재발매 루머",
                "source": "https://x.com/example/status/1",
                "source_kind": "x",
                "verified": False,
            }],
            "channel_status": {},
            "topic_coverage": {key: 99},
        }, ensure_ascii=False), encoding="utf-8")

        report = self.observe()
        rewritten = json.loads(self.social.read_text(encoding="utf-8"))

        self.assertEqual(rewritten["candidate_topic_coverage"][key], 1)
        self.assertEqual(rewritten["verified_topic_coverage"][key], 0)
        self.assertEqual(rewritten["topic_coverage"][key], 0)
        self.assertEqual(rewritten["topic_coverage_basis"], "verified-source-only")
        self.assertIn(key, rewritten["candidate_only_topic_cells"])
        self.assertIn(key, report["coverage_gap_learning"]["verified_missing_cells"])
        self.assertEqual(report["coverage_gap_learning"]["coverage_basis"], "verified-source-only")

    def test_canonical_official_row_resolves_matching_gap(self):
        key = "원피스 카드/KR/reprint"
        self.promo.write_text(json.dumps({
            "items": [{
                "game": "원피스 카드",
                "region": "KR",
                "category": "promo",
                "name_ko": "부스터팩 공식 재발매 안내",
                "source": "https://onepiece-cardgame.kr/topics.do",
                "source_grade": "official",
            }]
        }, ensure_ascii=False), encoding="utf-8")

        report = self.observe()
        self.assertNotIn(key, report["coverage_gap_learning"]["verified_missing_cells"])
        self.assertNotIn(key, report["coverage_gap_learning"]["candidate_only_cells"])

    def test_channel_health_learns_x_instagram_google_separately(self):
        self.social.write_text(json.dumps({
            "items": [],
            "channel_status": {
                "x": {
                    "configured": True,
                    "query_count": 1,
                    "success_query_count": 0,
                    "result_count": 0,
                    "error_count": 1,
                },
                "instagram": {
                    "configured": False,
                    "account_count": 0,
                    "result_count": 0,
                    "error_count": 0,
                },
                "google_news": {
                    "configured": True,
                    "query_count": 9,
                    "success_query_count": 9,
                    "result_count": 12,
                    "error_count": 0,
                },
            },
        }, ensure_ascii=False), encoding="utf-8")

        report = self.observe()
        by_name = {row["provider"]: row for row in report["providers"]}

        self.assertEqual(by_name["social:x"]["last_status"], "failed")
        self.assertEqual(by_name["social:x"]["error_streak"], 1)
        self.assertEqual(by_name["social:google_news"]["last_status"], "ok")
        self.assertEqual(by_name["social:google_news"]["response_rate"], 1.0)
        self.assertEqual(by_name["social:instagram"]["last_status"], "not-configured")
        self.assertEqual(by_name["social:instagram"]["unconfigured_runs"], 1)
        self.assertEqual(by_name["social:instagram"]["errors"], 0)

    def test_namuwiki_candidate_is_discovery_only_and_never_auto_verified(self):
        key = "포켓몬 카드/KR/movie"
        self.supplementary.write_text(json.dumps({
            "items": [{
                "game": "포켓몬 카드",
                "region": "KR",
                "category": "movie",
                "title": "포켓몬스터 극장판",
                "source": "https://namu.wiki/w/example",
                "source_tier": "C",
                "source_label": "나무위키 보조탐색",
                "verified": False,
                "status": "보조출처 후보",
            }]
        }, ensure_ascii=False), encoding="utf-8")

        report = self.observe()
        kinds = {row["source_kind"]: row for row in report["source_kind_learning"]}

        self.assertIn(key, report["coverage_gap_learning"]["candidate_only_cells"])
        self.assertIn("supplementary:namu.wiki", kinds)
        self.assertEqual(kinds["supplementary:namu.wiki"]["verified"], 0)
        self.assertFalse(report["safety"]["trust_learning"])
        self.assertFalse(report["safety"]["auto_verify"])
        self.assertFalse(report["safety"]["learned_text_execution"])
        self.assertFalse(report["safety"]["access_control_bypass"])


if __name__ == "__main__":
    unittest.main()
