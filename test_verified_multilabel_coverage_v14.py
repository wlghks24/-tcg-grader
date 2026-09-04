#!/usr/bin/env python3
import unittest

import provider_health_learning as health


class VerifiedMultilabelCoverageV14Tests(unittest.TestCase):
    def _row(self, *, verified=True, source_grade=None, title="", excerpt="", search_topic=None):
        row = {
            "game": "포켓몬 카드",
            "region": "JP",
            "title": title,
            "excerpt": excerpt,
            "source": "https://www.pokemon-card.com/info/example.html",
        }
        if verified is not None:
            row["verified"] = verified
        if source_grade is not None:
            row["source_grade"] = source_grade
        if search_topic is not None:
            row["search_topic"] = search_topic
        return row

    def test_verified_official_notice_closes_multiple_concrete_fact_gaps(self):
        row = self._row(
            verified=None,
            source_grade="official",
            title="가격 변경 및 구매 제한 안내",
            excerpt="제품 불량이 확인되어 교환 대응을 실시합니다.",
        )
        snapshot = health._coverage_snapshot({}, {}, {"items": [row]})
        for topic in ("product_issue", "official_price", "purchase_policy"):
            cell = snapshot[f"포켓몬 카드/JP/{topic}"]
            self.assertEqual(cell["candidate_count"], 1, topic)
            self.assertEqual(cell["verified_count"], 1, topic)
            self.assertEqual(cell["canonical_count"], 1, topic)

    def test_unverified_candidate_remains_primary_topic_only(self):
        row = self._row(
            verified=False,
            title="가격 변경 및 구매 제한 안내",
            excerpt="제품 불량이 확인되어 교환 대응을 실시합니다.",
        )
        snapshot = health._coverage_snapshot({"items": [row]}, {}, {})
        self.assertEqual(health._topic(row), "product_issue")
        self.assertEqual(snapshot["포켓몬 카드/JP/product_issue"]["candidate_count"], 1)
        self.assertEqual(snapshot["포켓몬 카드/JP/official_price"]["candidate_count"], 0)
        self.assertEqual(snapshot["포켓몬 카드/JP/purchase_policy"]["candidate_count"], 0)

    def test_broad_event_words_do_not_fan_out_verified_coverage(self):
        row = self._row(
            verified=True,
            title="대회 프로모 이벤트 안내",
        )
        topics = health._topics(row, verified=True)
        self.assertEqual(topics, ("tournament",))
        snapshot = health._coverage_snapshot({"items": [row]}, {}, {})
        self.assertEqual(snapshot["포켓몬 카드/JP/tournament"]["verified_count"], 1)
        self.assertEqual(snapshot["포켓몬 카드/JP/promo"]["verified_count"], 0)
        self.assertEqual(snapshot["포켓몬 카드/JP/event"]["verified_count"], 0)

    def test_explicit_primary_topic_keeps_secondary_verified_facts(self):
        row = self._row(
            verified=True,
            search_topic="event",
            title="행사 일정 변경 안내",
            excerpt="신청 마감은 9월 10일이며 참가 자격 및 체크인이 필요합니다.",
        )
        topics = health._topics(row, verified=True)
        self.assertEqual(topics[0], "event")
        self.assertIn("status_update", topics)
        self.assertIn("deadline", topics)
        self.assertIn("access", topics)

    def test_verified_social_candidate_coverage_remains_superset(self):
        row = self._row(
            verified=True,
            title="가격 변경 및 구매 제한 안내",
            excerpt="제품 불량이 확인되어 교환 대응을 실시합니다.",
        )
        candidate = health._social_topic_coverage([row], verified_only=False)
        verified = health._social_topic_coverage([row], verified_only=True)
        for key, verified_count in verified.items():
            self.assertGreaterEqual(candidate[key], verified_count, key)
        self.assertEqual(candidate["포켓몬 카드/JP/product_issue"], 1)
        self.assertEqual(candidate["포켓몬 카드/JP/official_price"], 1)
        self.assertEqual(candidate["포켓몬 카드/JP/purchase_policy"], 1)

    def test_report_documents_multilabel_safety_boundary(self):
        report = health._coverage_report(health._fresh())
        self.assertEqual(report["coverage_basis"], "verified-source-only")
        self.assertIn("unverified rows remain primary-topic-only", report["verified_fact_basis"])
        self.assertNotIn("event", report["verified_multi_label_topics"])
        self.assertNotIn("promo", report["verified_multi_label_topics"])
        self.assertIn("product_issue", report["verified_multi_label_topics"])


if __name__ == "__main__":
    unittest.main()
