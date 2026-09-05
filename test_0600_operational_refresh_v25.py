#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main_crosscheck_export
import selfrefine_crosscheck_gate
import tcg_updater
from instagram_tcg_content import crosscheck_export as instagram_crosscheck_export


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

    def test_factual_exchange_writers_use_atomic_runtime_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main_path = root / "main.json"
            insta_path = root / "instagram.json"
            main_crosscheck_export.export_records([_sample("main")], main_path)
            instagram_crosscheck_export.export_records([_sample("instagram")], insta_path)
            self.assertEqual(json.loads(main_path.read_text(encoding="utf-8"))["domain"], "main")
            self.assertEqual(
                json.loads(insta_path.read_text(encoding="utf-8"))["domain"],
                "instagram_content",
            )
            self.assertFalse(any(p.suffix == ".tmp" for p in root.iterdir()))

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
        self.assertIn("timeout-minutes: 30", text)


if __name__ == "__main__":
    unittest.main()
