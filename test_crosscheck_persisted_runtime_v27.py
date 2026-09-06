#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from crosscheck_persisted_runtime import (
    REQUIRED_VALIDATION,
    run_persisted_crosscheck,
)
from main_crosscheck_export import (
    persist_verified_snapshot as persist_main_snapshot,
)
from instagram_tcg_content.crosscheck_export import (
    persist_verified_snapshot as persist_instagram_snapshot,
)


def row(domain: str, value: str = "2026-09-16") -> dict:
    return {
        "information_family": "release",
        "canonical_key": "pokemon|release|jp|sample",
        "value": value,
        "currency": "",
        "language": "JP",
        "variant": "sample",
        "source_code": f"{domain}-official",
        "source_locator": f"https://example.invalid/{domain}",
        "checked_at_kst": "2026-09-06T06:30:00+09:00",
        "verification": "verified",
        "confidence": 0.99,
        "lineage_key": f"{domain}-lineage",
    }


class PersistedCrosscheckRuntimeTests(unittest.TestCase):
    def test_exporters_persist_real_verified_snapshots_then_crosscheck(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main_snapshot = root / "main.json"
            instagram_snapshot = root / "instagram.json"
            main_runtime = root / "runtime-main.json"
            instagram_runtime = root / "runtime-instagram.json"
            report = root / "report.json"

            main_payload = persist_main_snapshot([row("main")], main_snapshot)
            ig_payload = persist_instagram_snapshot([row("instagram")], instagram_snapshot)

            self.assertEqual(main_payload["namespace"], "MARKET_ANALYSIS")
            self.assertEqual(ig_payload["namespace"], "IG_CARDINFO")
            self.assertEqual(main_payload["status"], "finalized")
            self.assertEqual(ig_payload["status"], "finalized")
            self.assertEqual(main_payload["validation"], REQUIRED_VALIDATION)
            self.assertEqual(ig_payload["validation"], REQUIRED_VALIDATION)

            result = run_persisted_crosscheck(
                main_snapshot=main_snapshot,
                instagram_snapshot=instagram_snapshot,
                main_runtime=main_runtime,
                instagram_runtime=instagram_runtime,
                report=report,
            )
            self.assertTrue(result["operational_ready"])
            self.assertEqual(result["agree"], 1)
            self.assertEqual(result["conflict"], 0)
            self.assertTrue(main_runtime.is_file())
            self.assertTrue(instagram_runtime.is_file())

    def test_conflict_requires_reverification(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main_snapshot = root / "main.json"
            instagram_snapshot = root / "instagram.json"
            persist_main_snapshot([row("main")], main_snapshot)
            persist_instagram_snapshot([row("instagram", "2026-09-17")], instagram_snapshot)
            result = run_persisted_crosscheck(
                main_snapshot=main_snapshot,
                instagram_snapshot=instagram_snapshot,
                main_runtime=root / "runtime-main.json",
                instagram_runtime=root / "runtime-instagram.json",
                report=root / "report.json",
            )
            self.assertEqual(result["conflict"], 1)
            self.assertEqual(result["reverification_required"], 1)

    def test_missing_snapshot_clears_stale_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main_snapshot = root / "main.json"
            persist_main_snapshot([row("main")], main_snapshot)
            main_runtime = root / "runtime-main.json"
            instagram_runtime = root / "runtime-instagram.json"
            main_runtime.write_text("stale", encoding="utf-8")
            instagram_runtime.write_text("stale", encoding="utf-8")
            result = run_persisted_crosscheck(
                main_snapshot=main_snapshot,
                instagram_snapshot=root / "missing-instagram.json",
                main_runtime=main_runtime,
                instagram_runtime=instagram_runtime,
                report=root / "report.json",
            )
            self.assertEqual(result["status"], "snapshot_missing")
            self.assertFalse(result["operational_ready"])
            self.assertFalse(main_runtime.exists())
            self.assertFalse(instagram_runtime.exists())

    def test_legacy_noncanonical_type_is_rejected(self):
        bad = row("main")
        bad["information_family"] = "market_price"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                persist_main_snapshot([bad], Path(td) / "bad.json")

        bad = row("instagram")
        bad["information_family"] = "promo_event"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                persist_instagram_snapshot([bad], Path(td) / "bad.json")


if __name__ == "__main__":
    unittest.main()
