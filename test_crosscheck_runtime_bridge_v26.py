#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

from crosscheck_runtime_bridge import run_bridge, run_from_persisted

BASE = {
    "information_family": "release",
    "canonical_key": "pokemon|30th-celebration|jp",
    "value": "2026-09-16",
    "currency": "",
    "language": "JP",
    "variant": "",
    "source_code": "main-official",
    "source_locator": "https://example.invalid/main",
    "checked_at_kst": "2026-09-06T06:00:00+09:00",
    "verification": "verified",
    "confidence": 0.99,
    "lineage_key": "main-release-lineage",
}


class CrosscheckRuntimeBridgeTests(unittest.TestCase):
    def _paths(self, root: Path):
        return {
            "main_output": root / "main.json",
            "instagram_output": root / "instagram.json",
            "report_output": root / "report.json",
        }

    def test_end_to_end_agree_and_conflict(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            same = {
                **BASE,
                "source_code": "instagram-official",
                "source_locator": "https://example.invalid/instagram",
                "verification": "candidate",
                "lineage_key": "instagram-release-lineage",
            }
            left_market = {
                **BASE,
                "information_family": "market_reference",
                "canonical_key": "onepiece|op17|box|jp",
                "value": "24500",
                "currency": "JPY",
                "variant": "BOX",
                "source_code": "main-market",
                "lineage_key": "main-market-lineage",
            }
            right_market = {
                **left_market,
                "value": "25000",
                "source_code": "instagram-market",
                "source_locator": "https://example.invalid/instagram-market",
                "lineage_key": "instagram-market-lineage",
            }
            result = run_bridge(
                [BASE, left_market],
                [same, right_market],
                **self._paths(root),
            )
            self.assertTrue(result["engine_available"])
            self.assertTrue(result["operational_ready"])
            self.assertEqual(result["agree"], 1)
            self.assertEqual(result["conflict"], 1)
            self.assertEqual(result["reverification_required"], 1)

    def test_missing_side_does_not_create_fake_snapshot(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            paths = self._paths(root)
            result = run_bridge([BASE], [], **paths)
            self.assertEqual(result["status"], "snapshot_missing")
            self.assertTrue(result["engine_available"])
            self.assertFalse(result["operational_ready"])
            self.assertFalse(paths["main_output"].exists())
            self.assertFalse(paths["instagram_output"].exists())

    def test_persisted_snapshots_feed_runtime_and_purge_stale_outputs(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main_snapshot = root / "persisted-main.json"
            instagram_snapshot = root / "persisted-instagram.json"
            main_snapshot.write_text(
                '{"namespace":"MARKET_ANALYSIS","snapshot_kind":"factual","status":"finalized","facts":[{"fact_type":"release","canonical_key":"pokemon|30th-celebration|jp","lineage_key":"pmain","value":"2026-09-16","language":"JP","source_role":"official_primary","source_locator":"https://example.invalid/main-persisted","observed_at":"2026-09-06T06:00:00+09:00","verification_status":"verified"}]}',
                encoding="utf-8",
            )
            instagram_snapshot.write_text(
                '{"namespace":"IG_CARDINFO","snapshot_kind":"factual","status":"finalized","facts":[{"fact_type":"release","canonical_key":"pokemon|30th-celebration|jp","lineage_key":"pinstagram","value":"2026-09-16","language":"JP","source_role":"official_primary","source_locator":"https://example.invalid/instagram-persisted","observed_at":"2026-09-06T06:30:00+09:00","verification_status":"verified"}]}',
                encoding="utf-8",
            )
            paths = self._paths(root)
            result = run_from_persisted(
                main_snapshot=main_snapshot,
                instagram_snapshot=instagram_snapshot,
                **paths,
            )
            self.assertTrue(result["operational_ready"])
            self.assertEqual(result["agree"], 1)
            self.assertEqual(result["persisted_main_status"], "finalized")
            self.assertEqual(result["persisted_instagram_status"], "finalized")

            instagram_snapshot.write_text(
                '{"namespace":"IG_CARDINFO","snapshot_kind":"factual","status":"building","facts":[]}',
                encoding="utf-8",
            )
            paths["main_output"].write_text("{}", encoding="utf-8")
            paths["instagram_output"].write_text("{}", encoding="utf-8")
            result = run_from_persisted(
                main_snapshot=main_snapshot,
                instagram_snapshot=instagram_snapshot,
                **paths,
            )
            self.assertFalse(result["operational_ready"])
            self.assertEqual(result["status"], "snapshot_missing")
            self.assertFalse(paths["main_output"].exists())
            self.assertFalse(paths["instagram_output"].exists())

    def test_persisted_namespace_mismatch_fails_closed(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main_snapshot = root / "persisted-main.json"
            instagram_snapshot = root / "persisted-instagram.json"
            main_snapshot.write_text(
                '{"namespace":"IG_CARDINFO","snapshot_kind":"factual","status":"finalized","facts":[{"fact_type":"release","canonical_key":"x","lineage_key":"x","value":"x","source_role":"official","source_locator":"https://example.invalid/x","observed_at":"2026-09-06T06:00:00+09:00","verification_status":"verified"}]}',
                encoding="utf-8",
            )
            instagram_snapshot.write_text(
                '{"namespace":"IG_CARDINFO","snapshot_kind":"factual","status":"building","facts":[]}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                run_from_persisted(
                    main_snapshot=main_snapshot,
                    instagram_snapshot=instagram_snapshot,
                    **self._paths(root),
                )

    def test_noncanonical_factual_type_fails_closed(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            with self.assertRaises(ValueError):
                run_bridge(
                    [{**BASE, "information_family": "market_price"}],
                    [{**BASE, "source_code": "instagram-source", "lineage_key": "ig"}],
                    **self._paths(root),
                )


if __name__ == "__main__":
    unittest.main()
