#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from daily_collection_instagram_accuracy import _exit_code, build_report
from shared_self_learning.engine import normalize_crosscheck_record

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


def healthy_source_stats():
    stamp = "2026-09-05T20:00:00+00:00"
    sources = {}
    index = 0
    for game in ("pokemon", "one_piece", "naruto"):
        for region in ("KR", "JP", "US"):
            index += 1
            sources[f"official-{index}"] = {
                "official_scope": True,
                "game": game,
                "region": region,
                "channel": "news_event",
                "url": f"https://example.invalid/{game}/{region}",
                "last_run": stamp,
                "last_result": "success",
                "consecutive_failures": 0,
            }
    return {"updated_at": stamp, "sources": sources}


class DailyAuditTest(unittest.TestCase):
    def _report(self, adaptive=None, source_stats=None, promo=None, routes=None):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            return build_report(
                now=NOW,
                adaptive=adaptive or healthy_adaptive(),
                source_stats=source_stats or healthy_source_stats(),
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
                "dominant_error_signature": "historical-dominant",
                "last_error_signature": "current-timeout",
            }
        )
        report = self._report(adaptive=adaptive)
        kinds = {x["kind"] for x in report["main_collection"]["findings"]}
        self.assertIn("stale_job", kinds)
        self.assertIn("repeated_failure", kinds)
        repeated = next(
            x for x in report["main_collection"]["findings"]
            if x["kind"] == "repeated_failure"
        )
        self.assertEqual(repeated["current_error_signature"], "current-timeout")
        self.assertEqual(repeated["dominant_error_signature"], "historical-dominant")
        self.assertEqual(report["summary"]["status"], "degraded")
        self.assertEqual(_exit_code(report, strict_policy=True), 0)
        self.assertEqual(_exit_code(report, fail_on_degraded=True), 1)

    def test_official_source_coverage_gap_is_degraded_and_repairable(self):
        stats = healthy_source_stats()
        for row in stats["sources"].values():
            if row.get("game") == "naruto" and row.get("region") == "US":
                row["last_result"] = "restricted"
                row["last_http_status"] = 403
        report = self._report(source_stats=stats)
        coverage = report["main_collection"]["official_source_coverage"]
        self.assertFalse(coverage["ok"])
        self.assertIn("naruto/US", coverage["degraded_cells"])
        self.assertTrue(
            any(x["kind"] == "official_source_coverage_gap" for x in report["main_collection"]["findings"])
        )
        self.assertTrue(
            any(x["rule"] == "restore_official_source_coverage" for x in report["repair_actions"])
        )
        self.assertEqual(report["summary"]["status"], "degraded")

    def test_policy_regression_fails_closed(self):
        routes = good_routes()
        routes["rules"]["bypass_403_429"] = True
        report = self._report(routes=routes)
        self.assertGreater(report["summary"]["critical_findings"], 0)
        self.assertEqual(report["summary"]["status"], "fail_closed")
        self.assertFalse(report["safety"]["403_429_bypass_allowed"])

    def test_cross_domain_conflict_requires_reverification(self):
        exchange_root = Path("crosscheck_exchange")
        exchange_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange_root) as td:
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
            main_row = normalize_crosscheck_record("main", base)
            main_path.write_text(
                json.dumps({"domain": "main", "records": [main_row]}, ensure_ascii=False),
                encoding="utf-8",
            )
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
            instagram_row = normalize_crosscheck_record("instagram_content", other)
            instagram_path.write_text(
                json.dumps(
                    {"domain": "instagram_content", "records": [instagram_row]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            report = build_report(
                now=NOW,
                adaptive=healthy_adaptive(),
                source_stats=healthy_source_stats(),
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
            self.assertEqual(_exit_code(report, strict_policy=True), 1)

    def test_malformed_numeric_health_fields_do_not_crash_audit(self):
        adaptive = healthy_adaptive()
        adaptive["jobs"]["releases.json"]["consecutive_failures"] = "not-an-int"
        promo = healthy_promo()
        promo["coverage"]["covered_game_region_pairs"] = {"bad": "shape"}
        report = self._report(adaptive=adaptive, promo=promo)
        kinds = {x["kind"] for x in report["main_collection"]["findings"]}
        self.assertIn("coverage_gap", kinds)
        self.assertEqual(report["summary"]["status"], "degraded")

    def test_malformed_crosscheck_snapshot_fails_closed_with_repair_action(self):
        exchange_root = Path("crosscheck_exchange")
        exchange_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange_root) as td:
            root = Path(td)
            main_path = root / "main.json"
            instagram_path = root / "instagram.json"
            main_path.write_text("{not-json", encoding="utf-8")
            instagram_path.write_text(
                json.dumps({"domain": "instagram_content", "records": []}),
                encoding="utf-8",
            )
            report = build_report(
                now=NOW,
                adaptive=healthy_adaptive(),
                source_stats=healthy_source_stats(),
                promo=healthy_promo(),
                routes=good_routes(),
                main_exchange=main_path,
                instagram_exchange=instagram_path,
            )
            self.assertEqual(report["summary"]["status"], "fail_closed")
            self.assertTrue(report["summary"]["crosscheck_validation_error"])
            self.assertEqual(report["cross_domain"]["status"], "validation_error")
            self.assertTrue(
                any(x["rule"] == "repair_invalid_snapshot" for x in report["repair_actions"])
            )
            self.assertEqual(_exit_code(report, strict_policy=True), 1)


if __name__ == "__main__":
    unittest.main()
