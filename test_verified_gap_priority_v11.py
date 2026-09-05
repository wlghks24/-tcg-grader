#!/usr/bin/env python3
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import adaptive_collection_learner as adaptive
import provider_health_learning as health


class VerifiedGapPriorityV11Tests(unittest.TestCase):
    def _official_snapshot(self, title="일정 변경 공지", status="변경", official_verified_at=None):
        row = {
            "game": "포켓몬 카드",
            "region": "KR",
            "category": "event",
            "title": title,
            "status": status,
            "source": "https://pokemoncard.co.kr/example",
            "source_grade": "official",
            "start_date": "2026-09-10",
        }
        if official_verified_at:
            row["official_verified_at"] = official_verified_at
        return health._coverage_snapshot({}, {}, {"items": [row]})

    def test_same_verified_evidence_does_not_refresh_timestamp_forever(self):
        data = health._fresh()
        snapshot = self._official_snapshot()
        health._observe_coverage(data, snapshot)
        cell = "포켓몬 카드/KR/status_update"
        self.assertIn(cell, data["coverage_cells"])
        stat = data["coverage_cells"][cell]
        fingerprint = stat.get("verified_fingerprint")
        self.assertTrue(fingerprint)

        old = "2025-01-01T00:00:00+00:00"
        stat["last_verified"] = old
        health._observe_coverage(data, snapshot)
        self.assertEqual(data["coverage_cells"][cell]["last_verified"], old)
        self.assertEqual(data["coverage_cells"][cell]["verified_fingerprint"], fingerprint)
        self.assertNotEqual(data["coverage_cells"][cell].get("last_verified_seen"), old)

    def test_changed_verified_evidence_refreshes_timestamp(self):
        data = health._fresh()
        first = self._official_snapshot()
        health._observe_coverage(data, first)
        cell = "포켓몬 카드/KR/status_update"
        old = "2025-01-01T00:00:00+00:00"
        data["coverage_cells"][cell]["last_verified"] = old
        old_fingerprint = data["coverage_cells"][cell]["verified_fingerprint"]

        changed = self._official_snapshot(
            title="일정 변경 공지 - 장소 변경",
            status="장소 변경",
            official_verified_at="2026-09-05T00:00:00+00:00",
        )
        health._observe_coverage(data, changed)
        stat = data["coverage_cells"][cell]
        self.assertNotEqual(stat["verified_fingerprint"], old_fingerprint)
        self.assertNotEqual(stat["last_verified"], old)

    def test_old_unchanged_verified_cell_becomes_recheck_due(self):
        data = health._fresh()
        cell = "원피스 카드/KR/service_status"
        data["coverage_cells"][cell] = {
            "last_candidate_count": 1,
            "last_verified_count": 1,
            "miss_streak": 0,
            "verification_gap_streak": 0,
            "discovery_gap_streak": 0,
            "last_state": "verified",
            "last_verified": "2025-01-01T00:00:00+00:00",
            "last_verified_seen": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "verified_fingerprint": "same-evidence",
        }
        report = health._coverage_report(data)
        self.assertIn(cell, report["recheck_due_cells"])
        row = next(x for x in report["next_priority_by_game"]["원피스 카드"] if x["cell"] == cell)
        self.assertTrue(row["recheck_due"])
        self.assertEqual(row["priority_reason"], "verified-recheck-due")

    def test_candidate_only_cell_remains_verified_priority(self):
        data = health._fresh()
        cell = "나루토 카드/US/authenticity_notice"
        data["coverage_cells"][cell] = {
            "last_candidate_count": 9,
            "last_verified_count": 0,
            "miss_streak": 3,
            "verification_gap_streak": 3,
            "discovery_gap_streak": 0,
            "misses": 3,
            "last_state": "candidate-only",
        }
        focus = health.recommended_verified_focus("나루토", data)
        self.assertIsNotNone(focus)
        self.assertEqual(focus["cell"], cell)
        self.assertEqual(focus["topic"], "authenticity_notice")
        self.assertEqual(focus["priority_reason"], "verified-missing")

    def test_android_sized_query_budget_consumes_verified_gap(self):
        fake_focus = {
            "cell": "포켓몬 카드/JP/product_issue",
            "game": "포켓몬 카드",
            "region": "JP",
            "topic": "product_issue",
            "priority": 12.5,
            "priority_reason": "verified-missing",
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = adaptive.AdaptiveCollectionLearner(
                memory_path=root / "memory.json",
                backup_path=root / "backup.json",
                report_path=root / "report.json",
            )
            with mock.patch.object(health, "recommended_verified_focus", return_value=fake_focus), \
                 mock.patch.object(adaptive.collection_meta_learning, "recommended_focus", return_value=None):
                plans = learner.plan_queries("포켓몬", max_queries=5)
        families = [str(x.get("family") or "") for x in plans]
        self.assertEqual(len(plans), 5)
        self.assertIn("verified-gap:product_issue", families)
        gap = next(x for x in plans if x.get("family") == "verified-gap:product_issue")
        self.assertEqual(gap["region"], "JP")
        self.assertIn("封入", gap["query"])
        self.assertEqual(gap["verified_gap_reason"], "verified-missing")

    def test_report_exposes_per_game_verified_priorities(self):
        data = health._fresh()
        report = health._coverage_report(data)
        self.assertEqual(set(report["next_priority_by_game"]), set(health.GAMES))
        for game in health.GAMES:
            self.assertTrue(report["next_priority_by_game"][game])
            self.assertTrue(report["next_priority_by_game"][game][0]["cell"].startswith(game + "/"))


if __name__ == "__main__":
    unittest.main()
