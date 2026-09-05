#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import auto_update_all
import main_crosscheck_export
import selfrefine_crosscheck_gate
import tcg_updater
import update_promo_events


def _sample(source: str) -> dict:
    return {
        "information_family": "market_price",
        "canonical_key": "pokemon|pikachu|001|jp",
        "value": "1000",
        "currency": "JPY",
        "language": "JP",
        "variant": "normal",
        "source_code": source,
        "source_locator": "https://example.invalid/item",
        "checked_at_kst": "2026-09-05T18:00:00+09:00",
        "verification": "verified",
        "confidence": 0.9,
        "lineage_key": source + "-lineage",
    }


class Operational0600RefreshV25Tests(unittest.TestCase):
    def test_ci_source_timeout_cap_is_opt_in_and_bounded(self):
        with mock.patch.dict(os.environ, {"TCG_SOURCE_TIMEOUT_CAP": "30"}, clear=False):
            self.assertEqual(tcg_updater._source_timeout({}), 30)
            self.assertLessEqual(
                tcg_updater._source_timeout(
                    {
                        "successes": 5,
                        "clean_success_streak": 5,
                        "success_ewma_seconds": 100,
                        "consecutive_failures": 2,
                    }
                ),
                30,
            )
        with mock.patch.dict(os.environ, {"TCG_SOURCE_TIMEOUT_CAP": "300"}, clear=False):
            self.assertEqual(tcg_updater._source_timeout({}), 300)

    def test_stale_failure_streak_resets_without_erasing_lifetime_learning(self):
        old_signature = "old-dominant"
        stats = {
            "jobs": {
                "promo_events.json": {
                    "runs": 13,
                    "successes": 0,
                    "failures": 0,
                    "timeouts": 0,
                    "partial_successes": 13,
                    "recovered_successes": 13,
                    "success_streak": 0,
                    "consecutive_failures": 13,
                    "last_run": "2026-08-26T10:47:08+00:00",
                    "dominant_error_signature": old_signature,
                    "error_patterns": {
                        old_signature: {
                            "count": 13,
                            "sample": "historical network error",
                            "last_seen": "2026-08-26T10:47:08+00:00",
                        }
                    },
                }
            }
        }
        auto_update_all._record_job_stat(
            stats,
            "promo_events.json",
            2.5,
            True,
            error="한국 나루토 영화 개봉 확인: URLError: timed out",
            partial=True,
        )
        row = stats["jobs"]["promo_events.json"]
        self.assertEqual(row["consecutive_failures"], 1)
        self.assertEqual(row["streak_reset_reason"], "observation_gap_over_72h")
        self.assertEqual(row["runs"], 14)
        self.assertIn(old_signature, row["error_patterns"])
        self.assertNotEqual(row["last_error_signature"], old_signature)

    def test_recent_failure_streak_remains_consecutive(self):
        recent = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        stats = {
            "jobs": {
                "promo_events.json": {
                    "runs": 2,
                    "successes": 0,
                    "failures": 0,
                    "timeouts": 0,
                    "partial_successes": 2,
                    "recovered_successes": 0,
                    "success_streak": 0,
                    "consecutive_failures": 2,
                    "last_run": recent,
                    "error_patterns": {},
                }
            }
        }
        auto_update_all._record_job_stat(
            stats,
            "promo_events.json",
            1.0,
            True,
            error="URLError: timed out",
            partial=True,
        )
        row = stats["jobs"]["promo_events.json"]
        self.assertEqual(row["consecutive_failures"], 3)
        self.assertNotIn("streak_reset_reason", row)

    def test_tracking_secondary_timeout_is_warning_not_hard_collection_error(self):
        tracker = dict(update_promo_events.KR_MOVIE_TRACKERS[2])
        with mock.patch.object(
            update_promo_events,
            "fetch",
            side_effect=["official primary ok", OSError("timed out")],
        ):
            checked, error = update_promo_events.check_existing(tracker)
        self.assertIsNone(error)
        self.assertEqual(checked["source"], "https://naruto-official.com/en/news/01_2649")
        self.assertEqual(checked["verification_status"], "secondary_temporarily_unavailable")
        self.assertIn("timed out", checked["verification_error"].lower())

    def test_tracking_secondary_configuration_error_remains_fail_closed(self):
        tracker = dict(update_promo_events.KR_MOVIE_TRACKERS[2])
        with mock.patch.object(
            update_promo_events,
            "fetch",
            side_effect=["official primary ok", ValueError("unapproved verification url")],
        ):
            _, error = update_promo_events.check_existing(tracker)
        self.assertIsNotNone(error)
        self.assertIn("보조검증", error)

    def test_retired_pokemon_routes_are_replaced(self):
        self.assertEqual(
            update_promo_events.INDEXES[2][2],
            "https://new.pokemonkorea.co.kr/card",
        )
        self.assertEqual(
            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[
                "https://pokemonkorea.co.kr/2026_battle_tournament3"
            ],
            "https://pokemonkorea.co.kr/2026_battle_tournament3/menu800",
        )

    def test_pokemon_kr_event_uses_same_company_collection_fallback(self):
        tracker = dict(update_promo_events.KR_MOVIE_TRACKERS[0])
        self.assertEqual(tracker["source"], "https://www.pokemonkorea.co.kr/")
        self.assertEqual(tracker["collection_source"], "https://new.pokemonkorea.co.kr/card")
        with mock.patch.object(
            update_promo_events,
            "fetch",
            side_effect=["official collection page ok", "secondary ok"],
        ) as mocked:
            checked, error = update_promo_events.check_existing(tracker)
        self.assertIsNone(error)
        self.assertEqual(mocked.call_args_list[0].args[0], "https://new.pokemonkorea.co.kr/card")
        self.assertEqual(checked["verification_status"], "secondary_reachable")

    def test_factual_exchange_writers_use_atomic_runtime_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main_path = root / "main.json"
            main_crosscheck_export.export_records([_sample("main")], main_path)
            self.assertEqual(json.loads(main_path.read_text(encoding="utf-8"))["domain"], "main")
            self.assertFalse(any(p.suffix == ".tmp" for p in root.iterdir()))
        instagram_source = Path("instagram_tcg_content/crosscheck_export.py").read_text(encoding="utf-8")
        self.assertIn("def _write_json_atomic(", instagram_source)
        self.assertNotIn("from safe_runtime import", instagram_source)
        self.assertNotIn("output.write_text(", instagram_source)

    def test_factual_report_writer_is_atomic(self):
        source = Path("selfrefine_crosscheck_gate.py").read_text(encoding="utf-8")
        self.assertIn("atomic_write_json(REPORT, result", source)
        self.assertNotIn("REPORT.write_text(", source)

    def test_daily_0600_workflow_refreshes_live_health_with_ci_only_cap(self):
        text = Path(".github/workflows/daily-0600-collection-instagram-accuracy.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Refresh bounded live collection state before 06:00 audit", text)
        self.assertIn("tcg_updater.update_cycle('scheduled-0600-audit')", text)
        self.assertIn("TCG_SOURCE_TIMEOUT_CAP: '30'", text)
        self.assertIn("source_collection_stats.json", text)
        self.assertIn("adaptive_collection_stats.json", text)
        self.assertIn("github.event_name == 'push'", text)
        self.assertIn("github.event_name == 'pull_request'", text)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", text)
        self.assertIn("MAX_HEALTH_AGE_SECONDS = 600", text)
        self.assertIn("MAX_FUTURE_SKEW_SECONDS = 300", text)
        self.assertIn("source_health_age_seconds", text)
        self.assertIn("adaptive_health_age_seconds", text)
        self.assertIn("critical_collection_results", text)
        self.assertIn("stale {label} health", text)
        self.assertIn("future-dated {label} health", text)
        self.assertIn("timeout-minutes: 30", text)


if __name__ == "__main__":
    unittest.main()
