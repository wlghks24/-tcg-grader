"""Regression tests: title dates must never silently alter official event dates."""
import datetime as dt
import unittest
from unittest.mock import patch

import update_promo_events as events

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


class EventDiscoveryDateEvidenceTests(unittest.TestCase):
    def setUp(self):
        class FrozenDate(dt.date):
            @classmethod
            def today(cls):
                return cls(2026, 10, 25)
        self.clock = patch.object(events.dt, "date", FrozenDate)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.index = ("KR", "포켓몬 카드", "https://pokemoncard.co.kr/event/")
        self.target = "https://pokemoncard.co.kr/event/detail/123"

    def discover(self, title, detail):
        index_html = f'<a href="{self.target}">{title}</a>'
        def fetch(url):
            return index_html if url == self.index[2] else detail
        with patch.object(events, "fetch", side_effect=fetch) as work:
            rows, errors = events.discover(self.index)
        return rows, errors, work.call_count

    def test_publication_only_title_never_becomes_an_event_day(self):
        rows, errors, count = self.discover(
            "2027년 1월 1일 공지: 포켓몬 카드 대회 안내 — 개최일 추후 발표",
            "<article>포켓몬 카드 대회 개최일은 추후 발표합니다.</article>",
        )
        self.assertEqual([], rows)
        self.assertEqual(2, count)
        self.assertTrue(any("event date evidence missing" in error for error in errors))

    def test_unqualified_lone_index_date_requires_detail_confirmation(self):
        rows, errors, count = self.discover(
            "2027-01-01 포켓몬 카드 챔피언십 안내",
            "<article>포켓몬 카드 챔피언십 공식 소식</article>",
        )
        self.assertEqual([], rows)
        self.assertEqual(2, count)
        self.assertTrue(errors)

    def test_footer_and_archive_dates_are_not_current_event_evidence(self):
        for detail in (
            "<article>포켓몬 카드 대회 공식 상세정보</article><footer>2027.01.01 ~ 01.03</footer>",
            "<main><h1>대회 공식 상세정보</h1><aside>2027.01.01 ~ 01.03</aside></main>",
            "<article><p>지난 행사 기록: 2027.01.01 ~ 01.03</p></article>",
            "<article><p>Published: January 1, 2027</p></article>",
            "<article><p>Update: 2027-01-01</p></article>",
            "<article><p>Candidate 2027-01-01</p></article>",
        ):
            with self.subTest(detail=detail):
                self.assertIsNone(events.detail_date_range(detail))

    def test_announcement_date_and_actual_schedule_are_separate(self):
        rows, errors, count = self.discover(
            "2027년 1월 1일 공지: 포켓몬 카드 챔피언십 안내",
            "<article><p>게시일: 2027-01-01</p><p>행사 기간: 2027년 2월 1일 ~ 2월 3일</p></article>"
            "<footer>2027.01.01 ~ 01.03</footer>",
        )
        self.assertEqual([], errors)
        self.assertEqual(2, count)
        self.assertEqual(1, len(rows))
        self.assertEqual(("2027-02-01", "2027-02-03"), (rows[0]["start_date"], rows[0]["end_date"]))
        self.assertEqual("official_detail_event_schedule", rows[0]["date_evidence"]["kind"])
        self.assertEqual(self.target, rows[0]["date_evidence"]["source"])
        self.assertTrue(events.valid(rows[0]))

    def test_explicit_index_event_range_still_avoids_extra_request(self):
        rows, errors, count = self.discover("포켓몬 카드 챔피언십 2027년 2월 1일 ~ 2월 3일", "No dates")
        self.assertEqual([], errors)
        self.assertEqual(1, count)
        self.assertEqual("2027-02-03", rows[0]["end_date"])
        self.assertEqual("official_index_event_schedule", rows[0]["date_evidence"]["kind"])

    def test_single_day_context_headings_and_year_rollover_remain_supported(self):
        for text, expected in (
            ("<article><p>행사 일시: 2027년 2월 1일</p></article>", ("2027-02-01", "2027-02-01")),
            ("<article><h2>행사 일시</h2><p>2027년 2월 1일</p></article>", ("2027-02-01", "2027-02-01")),
            ("<article><p>Event Date: February 1, 2027</p></article>", ("2027-02-01", "2027-02-01")),
            ("<article><p>開催日: 2027年2月1日</p></article>", ("2027-02-01", "2027-02-01")),
            ("<article><p>행사 기간: 2026년 12월 28일 ~ 1월 3일</p></article>", ("2026-12-28", "2027-01-03")),
        ):
            with self.subTest(text=text):
                self.assertEqual(expected, events.detail_date_range(text))

    def test_unannounced_or_conflicting_schedules_require_review(self):
        for text in (
            "<article><p>개최일 미정</p><p>2027.01.01 ~ 01.03</p></article>",
            "<article><p>Event Date: TBA</p><p>Date February 1, 2027</p></article>",
            "<article><p>행사 기간: 2027.01.01 ~ 01.03</p><p>행사 기간: 2027.02.01 ~ 02.03</p></article>",
        ):
            with self.subTest(text=text):
                self.assertIsNone(events.detail_date_range(text))


if __name__ == "__main__":
    unittest.main()
