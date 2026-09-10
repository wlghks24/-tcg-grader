import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate as gate
import update_promo_events as events
import update_releases as releases


class InformationLifecycleArchiveV209Tests(unittest.TestCase):
    def event(self, end="2026-09-05", claim=None):
        return {"name_ko": "테스트 행사", "end_date": end,
                "claim_deadline": claim or end}

    def release(self, date="2026-09-05"):
        return {"game": "Pokémon", "region": "KR", "name": "테스트 카드",
                "release_date": date, "source": "https://example.com/release"}

    def test_event_is_current_through_fifth_day_and_archived_on_sixth(self):
        item = self.event()
        self.assertEqual("recently_ended", events.lifecycle_state(item, dt.date(2026, 9, 10)))
        self.assertEqual("archive", events.lifecycle_state(item, dt.date(2026, 9, 11)))
        current, archive = events.partition_event_lifecycle([item], dt.date(2026, 9, 10))
        self.assertEqual(1, len(current))
        self.assertEqual([], archive)
        self.assertEqual("2026-09-11", current[0]["archive_on"])

    def test_later_claim_deadline_controls_event_archive(self):
        item = self.event(end="2026-09-05", claim="2026-09-20")
        self.assertEqual("current", events.lifecycle_state(item, dt.date(2026, 9, 20)))
        self.assertEqual("recently_ended", events.lifecycle_state(item, dt.date(2026, 9, 25)))
        self.assertEqual("archive", events.lifecycle_state(item, dt.date(2026, 9, 26)))

    def test_release_uses_the_same_five_day_policy(self):
        item = self.release()
        self.assertEqual("current", releases.release_lifecycle_state(item, dt.date(2026, 9, 5)))
        self.assertEqual("recently_released", releases.release_lifecycle_state(item, dt.date(2026, 9, 10)))
        self.assertEqual("archive", releases.release_lifecycle_state(item, dt.date(2026, 9, 11)))
        current, archive = releases.partition_release_lifecycle([item], dt.date(2026, 9, 11))
        self.assertEqual([], current)
        self.assertEqual("2026-09-11", archive[0]["archive_on"])

    def test_month_only_release_moves_after_month_end_plus_five_days(self):
        item = self.release(date=None)
        item["release_window"] = "2026-09"
        self.assertEqual("recently_released", releases.release_lifecycle_state(item, dt.date(2026, 10, 5)))
        self.assertEqual("archive", releases.release_lifecycle_state(item, dt.date(2026, 10, 6)))

    def test_season_only_release_archives_after_season_end_plus_five_days(self):
        item = self.release(date=None)
        item["release_window"] = "2027년 여름"
        self.assertEqual("current", releases.release_lifecycle_state(item, dt.date(2027, 8, 31)))
        self.assertEqual("recently_released", releases.release_lifecycle_state(item, dt.date(2027, 9, 5)))
        self.assertEqual("archive", releases.release_lifecycle_state(item, dt.date(2027, 9, 6)))
        current, archive = releases.partition_release_lifecycle([item], dt.date(2027, 9, 6))
        self.assertEqual([], current)
        self.assertEqual("2027-09-06", archive[0]["archive_on"])

    def test_frontend_has_separate_event_and_release_archive_categories(self):
        html = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('id="promoLifecycle"', html)
        self.assertIn('지난 행사 보관함', html)
        self.assertIn('id="releaseLifecycle"', html)
        self.assertIn('지난 카드발매 보관함', html)
        self.assertIn("INFO_ARCHIVE_GRACE_DAYS=5", html)
        self.assertIn("...(promoData.archive_items||[])", html)
        self.assertIn("...(releaseData.archive_items||[])", html)
        self.assertIn("가을", html)
        self.assertIn("new Date(y+1,2,0)", html)

    def test_every_requested_information_category_uses_event_lifecycle(self):
        base = {
            **self.event(), "game": "포켓몬 카드", "region": "KR",
            "start_date": "2026-09-01", "reward": "안내", "condition": "공식 확인",
            "source": "https://www.pokemon.com/us/pokemon-tcg", "source_grade": "official",
        }
        for category in (
            "promo", "collaboration", "movie", "event", "festival", "tournament",
            "popup", "release", "reprint", "merch", "anniversary",
        ):
            with self.subTest(category=category):
                item = {**base, "category": category}
                self.assertTrue(events.valid(item))
                self.assertEqual("recently_ended", events.lifecycle_state(item, dt.date(2026, 9, 10)))
                self.assertEqual("archive", events.lifecycle_state(item, dt.date(2026, 9, 11)))

    def test_festival_has_independent_collection_topic_and_ui_category(self):
        import multi_route_event_discovery as routes
        html = Path("index.html").read_text(encoding="utf-8")
        self.assertIn("festival", routes.COVERAGE_TOPICS)
        self.assertEqual("festival", routes._category("포켓몬 카드 축제 페스티벌 개최"))
        self.assertIn('<option value="festival">🎉 축제·페스티벌</option>', html)
        self.assertIn('<option value="reprint">🔁 재발매·재입고</option>', html)
        self.assertNotIn('||"2027-12-31"', html)

    def test_second_example_ending_september_20_archives_on_september_26(self):
        item = self.event(end="2026-09-20")
        self.assertEqual("recently_ended", events.lifecycle_state(item, dt.date(2026, 9, 25)))
        self.assertEqual("archive", events.lifecycle_state(item, dt.date(2026, 9, 26)))

    def test_collection_keywords_and_categories_cover_requested_information_types(self):
        import multi_route_event_discovery as routes
        import social_event_discovery as social

        samples = {
            "promo": "포켓몬 카드 프로모 증정 캠페인",
            "collaboration": "원피스 카드 콜라보 협업 행사",
            "movie": "나루토 극장판 영화 개봉",
            "event": "포켓몬 카드 공식 행사 개최",
            "festival": "포켓몬 카드 축제 페스티벌 개최",
            "tournament": "원피스 카드 챔피언십 대회",
            "popup": "나루토 카드 팝업스토어 개최",
            "release": "포켓몬 카드 신탄 부스터 발매",
            "reprint": "원피스 카드 재발매 재판",
            "merch": "나루토 카드 공식샵 굿즈",
            "anniversary": "포켓몬 카드 30주년 기념행사",
        }
        for expected, text in samples.items():
            with self.subTest(expected=expected):
                self.assertIsNotNone(events.EVENT_WORDS.search(text))
                self.assertEqual(expected, events.classify_information_category(text))
                self.assertEqual(expected, routes._category(text))
                self.assertEqual(expected, social._category(text))

        self.assertEqual("reprint", events.classify_information_category("원피스 카드 재입고 안내"))
        self.assertEqual("reprint", routes._category("원피스 카드 재입고 안내"))
        self.assertEqual("reprint", social._category("원피스 카드 재입고 안내"))
        self.assertEqual("movie", events.classify_information_category("슈퍼 티저 비주얼과 예고편 공개"))
        self.assertEqual("movie", routes._category("슈퍼 티저 비주얼과 예고편 공개"))
        self.assertEqual("movie", social._category("슈퍼 티저 비주얼과 예고편 공개"))

    def test_verification_gate_reports_missing_collection_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "promo_events.json").write_text(json.dumps({
                "items": [{"region": "KR", "category": "promo", "name_ko": "행사",
                           "source": "https://example.com/event", "source_grade": "official"}],
                "archive_items": [], "archive_grace_days": 5,
                "coverage": {"missing_source_pairs": ["나루토 카드:US"]},
                "social_topic_expected_cells": 100,
                "social_topic_attempted_cells": 99,
                "social_topic_successful_cells": 98,
                "social_topic_missing_cells": ["나루토 카드/US/release"],
            }, ensure_ascii=False), encoding="utf-8")
            findings = []
            metrics = gate._audit_events(root, findings)
            self.assertEqual(1, metrics["missing_event_topic_cells"])
            self.assertTrue(any(x["code"] == "MISSING_OFFICIAL_EVENT_SOURCE_CELLS" for x in findings))
            self.assertTrue(any(x["code"] == "INCOMPLETE_EVENT_TOPIC_MATRIX" for x in findings))
            self.assertTrue(any(x["code"] == "INCOMPLETE_EVENT_TOPIC_COLLECTION_ATTEMPTS" for x in findings))


if __name__ == "__main__":
    unittest.main()
