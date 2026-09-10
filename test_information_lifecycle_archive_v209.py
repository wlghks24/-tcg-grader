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

    def test_frontend_has_separate_event_and_release_archive_categories(self):
        html = Path("index.html").read_text(encoding="utf-8")
        self.assertIn('id="promoLifecycle"', html)
        self.assertIn('지난 행사 보관함', html)
        self.assertIn('id="releaseLifecycle"', html)
        self.assertIn('지난 카드발매 보관함', html)
        self.assertIn("INFO_ARCHIVE_GRACE_DAYS=5", html)
        self.assertIn("...(promoData.archive_items||[])", html)
        self.assertIn("...(releaseData.archive_items||[])", html)

    def test_verification_gate_reports_missing_collection_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "promo_events.json").write_text(json.dumps({
                "items": [{"region": "KR", "category": "promo", "name_ko": "행사",
                           "source": "https://example.com/event", "source_grade": "official"}],
                "archive_items": [], "archive_grace_days": 5,
                "coverage": {"missing_source_pairs": ["나루토 카드:US"]},
                "social_topic_expected_cells": 100,
                "social_topic_missing_cells": ["나루토 카드/US/release"],
            }, ensure_ascii=False), encoding="utf-8")
            findings = []
            metrics = gate._audit_events(root, findings)
            self.assertEqual(1, metrics["missing_event_topic_cells"])
            self.assertTrue(any(x["code"] == "MISSING_OFFICIAL_EVENT_SOURCE_CELLS" for x in findings))
            self.assertTrue(any(x["code"] == "INCOMPLETE_EVENT_TOPIC_MATRIX" for x in findings))


if __name__ == "__main__":
    unittest.main()
