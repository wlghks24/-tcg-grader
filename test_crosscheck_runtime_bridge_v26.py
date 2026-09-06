#!/usr/bin/env python3
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from crosscheck_runtime_bridge import run_bridge, run_persisted_bridge

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
NOW = dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc)


def persisted_snapshot(
    namespace: str,
    *,
    value: str = "2026-09-16",
    status: str = "finalized",
    finalized_at: str = "2026-09-06T06:10:00+09:00",
    factual_type: str = "release",
    lineage: str = "release-lineage",
):
    return {
        "schema_version": "1.0",
        "namespace": namespace,
        "snapshot_kind": "factual",
        "run_date_kst": "2026-09-06",
        "status": status,
        "built_at": "2026-09-06T06:00:00+09:00",
        "finalized_at": finalized_at if status == "finalized" else None,
        "facts": [{
            "canonical_key": "pokemon|30th-celebration|jp",
            "fact_type": factual_type,
            "lineage_key": lineage,
            "identity": {"game": "pokemon", "product": "30th-celebration"},
            "value": value,
            "value_type": "date",
            "currency": "",
            "region": "JP",
            "language": "JP",
            "condition": "",
            "grade_company": "",
            "grade": "",
            "effective_date": value,
            "observed_at": "2026-09-06T06:00:00+09:00",
            "source_role": "official_primary",
            "source_locator": "https://example.invalid/fact",
            "verification_status": "verified",
        }],
        "validation": {
            "manifest_validated": True,
            "allowed_fields_only": True,
            "exact_factual_types_enforced": True,
            "write_readback_verified": True,
            "isolation_breach": False,
        },
        "error_code": None,
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
            result = run_bridge([BASE, left_market], [same, right_market], **self._paths(root))
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

    def test_persisted_finalized_snapshots_become_operational_runtime(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "persisted-main.json"
            instagram = root / "persisted-instagram.json"
            main.write_text(json.dumps(persisted_snapshot("MARKET_ANALYSIS", lineage="main-release")), encoding="utf-8")
            instagram.write_text(json.dumps(persisted_snapshot("IG_CARDINFO", lineage="ig-release")), encoding="utf-8")
            result = run_persisted_bridge(main, instagram, **self._paths(root), now=NOW)
            self.assertTrue(result["operational_ready"])
            self.assertEqual(result["status"], "crosschecked")
            self.assertEqual(result["agree"], 1)
            self.assertEqual(result["source_mode"], "persisted_tcg_crosscheck")
            self.assertTrue((root / "main.json").exists())
            self.assertTrue((root / "instagram.json").exists())

    def test_building_or_missing_persisted_snapshot_is_unavailable_and_clears_runtime(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "persisted-main.json"
            instagram = root / "persisted-instagram.json"
            main.write_text(json.dumps(persisted_snapshot("MARKET_ANALYSIS", status="building")), encoding="utf-8")
            paths = self._paths(root)
            paths["main_output"].write_text("stale", encoding="utf-8")
            paths["instagram_output"].write_text("stale", encoding="utf-8")
            result = run_persisted_bridge(main, instagram, **paths, now=NOW)
            self.assertEqual(result["status"], "snapshot_unavailable")
            self.assertFalse(result["operational_ready"])
            self.assertEqual(result["unavailable_reasons"]["main"], "not_finalized")
            self.assertEqual(result["unavailable_reasons"]["instagram_content"], "missing")
            self.assertFalse(paths["main_output"].exists())
            self.assertFalse(paths["instagram_output"].exists())

    def test_stale_persisted_snapshot_is_not_treated_as_current(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "persisted-main.json"
            instagram = root / "persisted-instagram.json"
            main.write_text(json.dumps(persisted_snapshot("MARKET_ANALYSIS", finalized_at="2026-09-01T06:10:00+09:00")), encoding="utf-8")
            instagram.write_text(json.dumps(persisted_snapshot("IG_CARDINFO")), encoding="utf-8")
            result = run_persisted_bridge(main, instagram, **self._paths(root), now=NOW)
            self.assertFalse(result["operational_ready"])
            self.assertEqual(result["unavailable_reasons"]["main"], "stale_snapshot")

    def test_persisted_noncanonical_type_fails_closed(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "persisted-main.json"
            instagram = root / "persisted-instagram.json"
            main.write_text(json.dumps(persisted_snapshot("MARKET_ANALYSIS", factual_type="market_price")), encoding="utf-8")
            instagram.write_text(json.dumps(persisted_snapshot("IG_CARDINFO")), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_persisted_bridge(main, instagram, **self._paths(root), now=NOW)


if __name__ == "__main__":
    unittest.main()
