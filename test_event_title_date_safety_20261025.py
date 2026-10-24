"""Regression tests: title dates must never silently alter official event dates."""
import unittest

from update_promo_events import normalize_event_dates


class EventTitleDateSafetyTests(unittest.TestCase):
    def test_title_date_is_only_an_unverified_candidate(self):
        original = {
            "name_ko": "행사 2026년 8월 22일 ~ 9월 4일",
            "start_date": "2026-08-20",
            "end_date": "2026-08-30",
            "claim_deadline": "2026-08-31",
            "source_grade": "official",
        }
        result = normalize_event_dates(original)
        self.assertEqual(result["start_date"], "2026-08-20")
        self.assertEqual(result["end_date"], "2026-08-30")
        self.assertEqual(result["claim_deadline"], "2026-08-31")
        self.assertEqual(result["title_date_candidate"], {
            "start_date": "2026-08-22",
            "end_date": "2026-09-04",
            "verification": "unverified_title_only",
        })
        self.assertNotIn("title_date_candidate", original)

    def test_missing_dates_are_not_invented_from_title(self):
        result = normalize_event_dates({"name_native": "2026.8.22 - 9.4"})
        self.assertNotIn("start_date", result)
        self.assertNotIn("end_date", result)
        self.assertNotIn("claim_deadline", result)
        self.assertEqual(result["title_date_candidate"]["verification"], "unverified_title_only")

    def test_invalid_title_range_does_not_create_candidate(self):
        result = normalize_event_dates({"name_ko": "2026년 2월 30일 ~ 3월 2일"})
        self.assertNotIn("title_date_candidate", result)


if __name__ == "__main__":
    unittest.main()
