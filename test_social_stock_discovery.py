import datetime as dt
import unittest

import social_stock_discovery as s


class SocialStockDiscoveryTests(unittest.TestCase):
    def test_quantity_at_least_is_claim_only(self):
        qty, relation = s.parse_quantity_claim("이마트 해운대 20개 이상 재고 있어요")
        self.assertEqual(qty, 20)
        self.assertEqual(relation, "at_least")

    def test_stop_is_not_forced_to_sold_out(self):
        status, label = s.classify_status("건대 스톱났습니다")
        self.assertEqual(status, "operation_stop_report")
        self.assertIn("운영중단", label)

    def test_stock_and_sold_out_parse(self):
        self.assertEqual(s.classify_status("오늘 재입고 재고 있습니다")[0], "in_stock_report")
        self.assertEqual(s.classify_status("현재 품절입니다")[0], "out_of_stock_report")

    def test_social_candidate_never_becomes_official_realtime(self):
        source = {
            "username": "ttosatda", "profile_url": "https://www.instagram.com/ttosatda/",
            "platform": "instagram", "game": "Pokemon", "region": "KR",
            "default_location": "이마트 해운대점", "default_product": "포켓몬 카드 BOX (제품명 미확정)",
            "ttl_hours": 24,
        }
        raw = {
            "title": "ttosatda 이마트 해운대 20개 이상 재고 있어요",
            "summary": "포켓몬 카드 BOX 입고",
            "url": "https://www.instagram.com/ttosatda/",
            "provider": "test",
        }
        row = s._candidate_from_result(raw, source)
        self.assertIsNotNone(row)
        self.assertFalse(row["official_stock"])
        self.assertFalse(row["realtime_stock"])
        self.assertEqual(row["verification_status"], "social_unverified")
        self.assertEqual(row["quantity_claim_min"], 20)

    def test_age_decay_marks_old_social_report_stale(self):
        now = dt.datetime(2026, 8, 29, 12, tzinfo=dt.timezone.utc)
        row = {"observed_at": "2026-08-27T00:00:00+00:00", "ttl_hours": 24, "score": 70}
        score, stale = s.age_adjusted_score(row, now)
        self.assertTrue(stale)
        self.assertLess(score, 70)

    def test_learning_priority_cannot_change_trust(self):
        source = {"username": "community", "trusted": False}
        learning = {"sources": {"community": {"runs": 100, "accepted": 100, "errors": 0}}}
        s._source_priority(source, learning)
        self.assertFalse(source["trusted"])


if __name__ == "__main__":
    unittest.main()
