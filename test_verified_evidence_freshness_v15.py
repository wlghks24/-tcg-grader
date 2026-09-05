#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import unittest

import provider_health_learning as health


class VerifiedEvidenceFreshnessV15Tests(unittest.TestCase):
    def _snapshot(self, row: dict) -> dict[str, dict]:
        return health._coverage_snapshot({}, {}, {"items": [row]})

    def _row(self, report: dict, cell: str) -> dict:
        rows = report["next_priority_cells"]
        match = next((row for row in rows if row["cell"] == cell), None)
        if match is not None:
            return match
        # Current (not-due) rows are not in next_priority_cells; derive from full state.
        state = report
        raise AssertionError(f"priority row missing for {cell}: {state}")

    def test_stale_official_evidence_bootstraps_original_time_not_now(self):
        data = health._fresh()
        cell = "포켓몬 카드/KR/service_status"
        snapshot = self._snapshot({
            "game": "포켓몬 카드",
            "region": "KR",
            "category": "event",
            "title": "서비스 장애 복구 완료 공지",
            "status": "복구 완료",
            "source": "https://pokemoncard.co.kr/notice/1",
            "source_grade": "official",
            "official_verified_at": "2026-01-15",
        })
        health._observe_coverage(data, snapshot)

        stat = data["coverage_cells"][cell]
        self.assertTrue(str(stat["last_verified"]).startswith("2026-01-15"))
        self.assertNotEqual(stat["last_verified"], stat["last_verified_seen"])

        report = health._coverage_report(data)
        row = next(x for x in report["next_priority_cells"] if x["cell"] == cell)
        self.assertTrue(row["recheck_due"])
        self.assertFalse(row["verification_freshness_unknown"])
        self.assertEqual(row["priority_reason"], "verified-recheck-due")

    def test_timestamp_unknown_verified_evidence_is_immediately_recheck_due(self):
        data = health._fresh()
        cell = "원피스 카드/KR/release"
        snapshot = self._snapshot({
            "game": "원피스 카드",
            "region": "KR",
            "category": "release",
            "title": "신제품 부스터 공식 발매 안내",
            "source": "https://onepiece-cardgame.kr/products.do",
            "source_grade": "official",
        })
        health._observe_coverage(data, snapshot)

        stat = data["coverage_cells"][cell]
        self.assertIsNone(stat.get("last_verified"))
        self.assertTrue(stat["verification_timestamp_unknown"])

        report = health._coverage_report(data)
        row = next(x for x in report["next_priority_cells"] if x["cell"] == cell)
        self.assertTrue(row["recheck_due"])
        self.assertTrue(row["verification_freshness_unknown"])
        self.assertEqual(row["priority_reason"], "verified-freshness-unknown")

    def test_recent_evidence_stays_current(self):
        data = health._fresh()
        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)).isoformat(timespec="seconds")
        cell = "나루토 카드/US/service_status"
        snapshot = self._snapshot({
            "game": "나루토 카드",
            "region": "US",
            "category": "event",
            "title": "service outage resolved",
            "status": "resolved",
            "source": "https://www.naruto-cardgame.com/en/news/status.php",
            "source_grade": "official",
            "official_verified_at": stamp,
        })
        health._observe_coverage(data, snapshot)

        report = health._coverage_report(data)
        self.assertNotIn(cell, report["recheck_due_cells"])
        self.assertIn(cell, [
            key for key, stat in data["coverage_cells"].items()
            if int(stat.get("last_verified_count") or 0) > 0
        ])
        self.assertFalse(data["coverage_cells"][cell]["verification_timestamp_unknown"])

    def test_replaying_same_stale_snapshot_never_refreshes_verification_time(self):
        data = health._fresh()
        cell = "포켓몬 카드/KR/status_update"
        row = {
            "game": "포켓몬 카드",
            "region": "KR",
            "category": "event",
            "title": "일정 변경 공지",
            "status": "장소 변경",
            "source": "https://pokemoncard.co.kr/event/change",
            "source_grade": "official",
            "collected_at": "2026-02-01T00:00:00+00:00",
        }
        snapshot = self._snapshot(row)
        health._observe_coverage(data, snapshot)
        first = data["coverage_cells"][cell]["last_verified"]
        first_seen = data["coverage_cells"][cell]["last_verified_seen"]

        health._observe_coverage(data, snapshot)
        second = data["coverage_cells"][cell]["last_verified"]
        second_seen = data["coverage_cells"][cell]["last_verified_seen"]

        self.assertEqual(first, second)
        self.assertTrue(str(first).startswith("2026-02-01"))
        self.assertGreaterEqual(second_seen, first_seen)

    def test_link_check_timestamp_is_not_treated_as_fact_verification(self):
        data = health._fresh()
        cell = "원피스 카드/KR/promo"
        snapshot = self._snapshot({
            "game": "원피스 카드",
            "region": "KR",
            "category": "promo",
            "title": "프로모 카드 공식 배포",
            "source": "https://onepiece-cardgame.kr/events/view.do?brdno=1",
            "source_grade": "official",
            "link_checked_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "link_status": "네트워크 지연 · 기존 링크 유지",
        })
        health._observe_coverage(data, snapshot)

        stat = data["coverage_cells"][cell]
        self.assertIsNone(stat.get("last_verified"))
        self.assertTrue(stat["verification_timestamp_unknown"])
        report = health._coverage_report(data)
        row = next(x for x in report["next_priority_cells"] if x["cell"] == cell)
        self.assertEqual(row["priority_reason"], "verified-freshness-unknown")


if __name__ == "__main__":
    unittest.main()
