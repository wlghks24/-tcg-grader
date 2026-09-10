#!/usr/bin/env python3
import unittest
from datetime import datetime, timezone

from instagram_tcg_content.collection_freshness_gap_guard import audit_freshness_gap


class CollectionFreshnessGapGuardTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 10, 11, 30, tzinfo=timezone.utc)
        self.releases = {"updated_at": "2026-09-10T08:25:54+00:00"}
        self.promos = {"updated_at": "2026-09-10T08:26:28+00:00"}
        self.stale_ig = {
            "namespace": "IG_CARDINFO",
            "status": "finalized",
            "built_at": "2026-09-06T21:25:43+09:00",
            "facts": [{"canonical_key": "pokemon|legacy|jp"}],
        }

    def test_fresh_shared_collection_plus_stale_ig_is_persistence_lag(self):
        report = audit_freshness_gap(
            self.releases,
            self.promos,
            self.stale_ig,
            now=self.now,
        )
        self.assertEqual(report["status"], "IG_LOCAL_CAPTURE_PERSISTENCE_LAG")
        self.assertEqual(
            report["error_code"],
            "IG_SNAPSHOT_STALE_WHILE_SHARED_COLLECTION_FRESH",
        )
        self.assertTrue(report["ig_local_refresh_required"])
        self.assertTrue(report["shared_collection"]["fresh"])
        self.assertFalse(
            report["shared_collection"]["promotion_to_ig_verified_fact_allowed"]
        )
        self.assertEqual(
            report["verification_mode_must_remain"],
            "INSTAGRAM_LOCAL_EVIDENCE_ONLY",
        )

    def test_fresh_ig_snapshot_clears_gap(self):
        fresh = dict(self.stale_ig)
        fresh["built_at"] = "2026-09-10T19:00:00+09:00"
        report = audit_freshness_gap(
            self.releases,
            self.promos,
            fresh,
            now=self.now,
        )
        self.assertEqual(report["status"], "NO_IG_FRESHNESS_GAP")
        self.assertIsNone(report["error_code"])
        self.assertFalse(report["ig_local_refresh_required"])

    def test_naive_or_missing_ig_timestamp_fails_closed(self):
        invalid = dict(self.stale_ig)
        invalid["built_at"] = "2026-09-10T19:00:00"
        report = audit_freshness_gap(
            self.releases,
            self.promos,
            invalid,
            now=self.now,
        )
        self.assertEqual(report["status"], "IG_LOCAL_CAPTURE_PERSISTENCE_LAG")
        self.assertTrue(report["ig_local_refresh_required"])
        self.assertIsNone(report["ig_snapshot"]["age_hours"])

    def test_stale_shared_data_is_not_misreported_as_ig_only_gap(self):
        stale = {"updated_at": "2026-09-08T00:00:00+00:00"}
        report = audit_freshness_gap(stale, stale, self.stale_ig, now=self.now)
        self.assertEqual(report["status"], "UPSTREAM_AND_IG_FRESHNESS_UNRESOLVED")
        self.assertEqual(report["error_code"], "IG_AND_SHARED_COLLECTION_NOT_FRESH")
        self.assertFalse(report["shared_collection"]["fresh"])
        self.assertTrue(report["ig_local_refresh_required"])

    def test_shared_rows_never_gain_verification_authority(self):
        report = audit_freshness_gap(
            self.releases,
            self.promos,
            self.stale_ig,
            now=self.now,
        )
        self.assertFalse(report["shared_collection"]["verification_authority"])
        self.assertFalse(
            report["shared_collection"]["promotion_to_ig_verified_fact_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
