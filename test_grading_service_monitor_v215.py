import datetime as dt
import unittest

import grading_service_monitor as g


class GradingServiceMonitorV215Tests(unittest.TestCase):
    def test_all_five_graders_and_expected_markets_are_present(self):
        self.assertEqual({v["provider"] for v in g.PROFILES.values()}, {"PSA", "BGS", "CGC", "TAG", "BRG"})
        self.assertIn("PSA_JP", g.PROFILES)
        self.assertIn("PSA_US", g.PROFILES)
        self.assertIn("BRG_KR", g.PROFILES)

    def test_all_authoritative_sources_are_official_https(self):
        for cfg in g.PROFILES.values():
            self.assertTrue(cfg["service_source"].startswith("https://"))
            self.assertTrue(cfg["notice_source"].startswith("https://"))
            self.assertIn(cfg["service_source"].split("/")[2], g.ALLOWED_HOSTS)
            self.assertIn(cfg["notice_source"].split("/")[2], g.ALLOWED_HOSTS)

    def test_social_or_user_candidate_can_never_overwrite(self):
        self.assertFalse(g.candidate_can_overwrite(g.RECHECK_TRIGGERS[0]))
        self.assertTrue(g.candidate_can_overwrite({"source_type": "official", "verification_status": "verified"}))

    def test_parser_detects_fee_and_turnaround(self):
        cfg = g.PROFILES["BRG_KR"]
        rows = g._parse_services("Regular 19,800원 /장 당 영업일 기준 20일 소요", cfg)
        row = next(x for x in rows if x["id"] == "regular")
        self.assertEqual(row["fee"], 19800)
        self.assertEqual(row["turnaround_business_days"], 20)

    def test_psa_jp_parser_accepts_new_standard_shape_without_social_promotion(self):
        cfg = g.PROFILES["PSA_JP"]
        rows = g._parse_services("スタンダード 料金 ¥9,980 100営業日 申告価格 ¥150,000", cfg)
        row = next(x for x in rows if x["id"] == "standard")
        self.assertEqual(row["fee"], 9980)
        self.assertEqual(row["turnaround_business_days"], 100)
        self.assertEqual(row["max_value"], 150000)
        self.assertFalse(g.RECHECK_TRIGGERS[0]["authoritative_overwrite_allowed"])

    def test_diff_tracks_price_turnaround_availability_and_rename(self):
        before = [{"id": "x", "name": "Regular", "fee": 10, "turnaround_business_days": 20, "availability": "open"}]
        after = [{"id": "x", "name": "Priority", "fee": 12, "turnaround_business_days": 30, "availability": "paused"}]
        kinds = {x["change_type"] for x in g._service_changes("T", before, after, "now", "https://official.example")}
        self.assertEqual(kinds, {"price_change", "turnaround_change", "availability_change", "service_rename"})

    def test_last_known_good_survives_parse_gap(self):
        previous = [{"id": "x", "name": "X", "fee": 99}]
        merged = g._merge_service_rows(previous, [], [])
        self.assertEqual(merged[0]["fee"], 99)

    def test_change_history_deduplicates_repeated_same_change(self):
        row = {"profile": "PSA_JP", "service_id": "express", "change_type": "price_change", "field": "fee", "before": 1, "after": 2, "source": "https://www.psacard.com/x"}
        self.assertEqual(len(g._dedupe_changes([row, dict(row)])), 1)

    def test_event_lifecycle_uses_same_five_day_archive_policy(self):
        self.assertEqual(g.lifecycle_state("2026-09-05", dt.date(2026, 9, 10)), "recently_ended")
        self.assertEqual(g.lifecycle_state("2026-09-05", dt.date(2026, 9, 11)), "archive")

    def test_psa_global_standard_verified_baseline_is_present(self):
        standard = next(x for x in g.PROFILES["PSA_US"]["baseline"] if x["id"] == "standard")
        self.assertEqual(standard["fee"], 84.99)
        self.assertEqual(standard["max_value"], 1400)
        self.assertEqual(standard["turnaround_business_days_min"], 100)
        self.assertEqual(standard["turnaround_business_days_max"], 110)


if __name__ == "__main__":
    unittest.main()
