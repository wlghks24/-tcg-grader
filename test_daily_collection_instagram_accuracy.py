#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from daily_collection_instagram_accuracy import build_report

NOW = dt.datetime(2026, 9, 5, 21, 0, tzinfo=dt.timezone.utc)


def good_routes():
    return {
        "rules": {
            "official_facts_require_official_primary": True,
            "completed_sale_requires_independent_realized_sale_sources": 2,
            "market_reference_requires_independent_sources_for_verified": 2,
            "discovery_lead_can_confirm_fact_alone": False,
            "respect_retry_after": True,
            "bypass_403_429": False,
            "preserve_provider_lineage": True,
            "dedupe_same_underlying_sale_lineage": True,
            "completed_sale_separate_from_market_reference": True,
        },
        "provider_groups": {
            game: {
                "official_primary": [f"{game}-official"],
                "completed_sale_original": ["ebay", "goldin"],
                "grading_auction_original": ["psa-apr"],
                "market_reference": ["pricecharting", "tcgplayer"],
            }
            for game in ("pokemon", "one_piece", "naruto")
        },
    }


def healthy_adaptive():
    stamp = "2026-09-05T20:00:00+00:00"
    return {
        "jobs": {
            name: {
                "last_run": stamp,
                "last_ok": True,
                "last_recovered": False,
                "consecutive_failures": 0,
            }
            for name in (
                "releases.json",
                "market_prices.json",
                "promo_events.json",
                "exchange_rates.json",
            )
        }
    }


def healthy_promo():
    return {
        "link_audit_at": "2026-09-05T20:00:00+00:00",
        "collection_errors": [],
        "coverage": {
            "expected_game_region_pairs": 9,
            "covered_game_region_pairs": 9,
            "missing_source_pairs": [],
        },
    }


class DailyAuditTest(unittest.TestCase):
    def _report(self, adaptive=None, source_stats=None, promo=None, routes=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            return build_report(
                now=NOW,
                adaptive=adaptive or healthy_adaptive(),
                source_stats=source_stats
                or {
                    "updated_at": "2026-09-05T20:00:00+00:00",
                    "sources": {"official": {"ok": 1}},
                },
                promo=promo or healthy_promo(),
                routes=routes or good_routes(),
                main_exchange=root / "main.json",
                instagram_exchange=root / "instagram.json",
            )

    def test_healthy_policy_with_missing_runtime_snapshots_is_warning_only(self):
        report = self._report()
        self.assertEqual(report["summary"]["critical_findings"], 0)
        self.assertEqual(report["summary"]["high_findings"], 0)
        self.assertEqual(report["cross_domain"]["status"], "snapshot_missing")
        self.assertEqual(report["summary"]["status"], "warning")

    def test_stale_repeated_main_failures_are_high_and_repairable(self):
        adaptive = healthy_adaptive()
        adaptive["jobs"]["promo_events.json"].update(
            {
                "last_run": "2026-08-26T10:47:08+00:00",
                "last_ok": False,
                "last_recovered": True,
                "consecutive_failures": 13,
                "dominant_error_signature": "abc",
            }
        )
        report = self._report(adaptive=adaptive)
        kinds = {x["kind"] for x in report["main_collection"]["findings"]}
        self.assertIn("stale_job", kinds)
        self.assertIn("repeated_failure", kinds)
        self.assertEqual(report["summary"]["status"], "degraded")

    def test_policy_regression_fails_closed(self):
        routes = good_routes()
        routes["rules"]["bypass_403_429"] = True
        report = self._report(routes=routes)
        self.assertGreater(report["summary"]["critical_findings"], 0)
        self.assertEqual(report["summary"]["status"], "fail_closed")
        self.assertFalse(report["safety"]["403_429_bypass_allowed"])

    def test_cross_domain_conflict_requires_reverification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main_path = root / "main.json"
            instagram_path = root / "instagram.json"
            base = {
                "information_family": "market_price",
                "canonical_key": "pokemon|001|jp",
                "value": "1000",
                "currency": "JPY",
                "language": "JP",
                "variant": "",
                "source_code": "main-a",
                "source_locator": "https://example.invalid/a",
                "checked_at_kst": "2026-09-06T05:50:00+09:00",
                "verification": "verified",
                "confidence": 0.9,
                "lineage_key": "main-lineage",
            }
            from main_crosscheck_export import export_records as export_main
            from instagram_tcg_content.crosscheck_export import export_records as export_instagram

            export_main([base], main_path)
            other = dict(base)
            other.update(
                {
                    "value": "1200",
                    "source_code": "ig-b",
                    "source_locator": "https://example.invalid/b",
                    "verification": "candidate",
                    "lineage_key": "ig-lineage",
                }
            )
            export_instagram([other], instagram_path)
            report = build_report(
                now=NOW,
                adaptive=healthy_adaptive(),
                source_stats={
                    "updated_at": "2026-09-05T20:00:00+00:00",
                    "sources": {"x": {}},
                },
                promo=healthy_promo(),
                routes=good_routes(),
                main_exchange=main_path,
                instagram_exchange=instagram_path,
            )
            self.assertEqual(report["cross_domain"]["conflict"], 1)
            self.assertEqual(report["summary"]["status"], "fail_closed")
            self.assertTrue(
                any(x["rule"] == "reverify_conflict" for x in report["repair_actions"])
            )


if __name__ == "__main__":
    unittest.main()
