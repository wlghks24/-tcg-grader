#!/usr/bin/env python3
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from crosscheck_runtime_bridge import run_bridge, run_from_persisted

NOW = dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc)
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


def snapshot(namespace: str, *, status="finalized", value="2026-09-16", finalized_at="2026-09-06T06:10:00+09:00"):
    return {
        "schema_version": "1.0",
        "namespace": namespace,
        "snapshot_kind": "factual",
        "run_date_kst": "2026-09-06",
        "status": status,
        "built_at": "2026-09-06T06:00:00+09:00",
        "finalized_at": finalized_at if status == "finalized" else None,
        "facts": [] if status != "finalized" else [{
            "canonical_key": "pokemon|30th-celebration|jp",
            "fact_type": "release",
            "lineage_key": namespace.lower(),
            "identity": "pokemon|30th-celebration|jp",
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
            same = {**BASE, "source_code": "instagram-official", "source_locator": "https://example.invalid/instagram", "verification": "candidate", "lineage_key": "instagram-release-lineage"}
            left = {**BASE, "information_family": "market_reference", "canonical_key": "onepiece|op17|box|jp", "value": "24500", "currency": "JPY", "variant": "BOX", "source_code": "main-market", "lineage_key": "main-market-lineage"}
            right = {**left, "value": "25000", "source_code": "instagram-market", "source_locator": "https://example.invalid/instagram-market", "lineage_key": "instagram-market-lineage"}
            result = run_bridge([BASE, left], [same, right], **self._paths(root))
            self.assertTrue(result["operational_ready"])
            self.assertEqual(result["agree"], 1)
            self.assertEqual(result["conflict"], 1)
            self.assertEqual(result["reverification_required"], 1)

    def test_missing_side_purges_stale_runtime(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            paths = self._paths(root)
            paths["main_output"].write_text("stale", encoding="utf-8")
            paths["instagram_output"].write_text("stale", encoding="utf-8")
            result = run_bridge([BASE], [], **paths)
            self.assertFalse(result["operational_ready"])
            self.assertFalse(paths["main_output"].exists())
            self.assertFalse(paths["instagram_output"].exists())

    def test_fresh_finalized_persisted_pair_is_operational(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "p-main.json"
            instagram = root / "p-instagram.json"
            main.write_text(json.dumps(snapshot("MARKET_ANALYSIS")), encoding="utf-8")
            instagram.write_text(json.dumps(snapshot("IG_CARDINFO")), encoding="utf-8")
            result = run_from_persisted(main_snapshot=main, instagram_snapshot=instagram, now=NOW, **self._paths(root))
            self.assertTrue(result["operational_ready"])
            self.assertEqual(result["status"], "crosschecked")
            self.assertEqual(result["agree"], 1)
            self.assertEqual(result["source_mode"], "persisted_tcg_crosscheck")

    def test_building_snapshot_is_unavailable_and_purges_runtime(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "p-main.json"
            instagram = root / "p-instagram.json"
            main.write_text(json.dumps(snapshot("MARKET_ANALYSIS")), encoding="utf-8")
            instagram.write_text(json.dumps(snapshot("IG_CARDINFO", status="building")), encoding="utf-8")
            paths = self._paths(root)
            paths["main_output"].write_text("stale", encoding="utf-8")
            paths["instagram_output"].write_text("stale", encoding="utf-8")
            result = run_from_persisted(main_snapshot=main, instagram_snapshot=instagram, now=NOW, **paths)
            self.assertEqual(result["status"], "snapshot_unavailable")
            self.assertFalse(result["operational_ready"])
            self.assertEqual(result["unavailable_reasons"]["instagram_content"], "not_finalized")
            self.assertFalse(paths["main_output"].exists())
            self.assertFalse(paths["instagram_output"].exists())

    def test_stale_snapshot_is_unavailable(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "p-main.json"
            instagram = root / "p-instagram.json"
            main.write_text(json.dumps(snapshot("MARKET_ANALYSIS", finalized_at="2026-09-01T06:10:00+09:00")), encoding="utf-8")
            instagram.write_text(json.dumps(snapshot("IG_CARDINFO")), encoding="utf-8")
            result = run_from_persisted(main_snapshot=main, instagram_snapshot=instagram, now=NOW, **self._paths(root))
            self.assertFalse(result["operational_ready"])
            self.assertEqual(result["unavailable_reasons"]["main"], "stale_snapshot")

    def test_namespace_mismatch_fails_closed(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            main = root / "p-main.json"
            instagram = root / "p-instagram.json"
            main.write_text(json.dumps(snapshot("IG_CARDINFO")), encoding="utf-8")
            instagram.write_text(json.dumps(snapshot("IG_CARDINFO")), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_from_persisted(main_snapshot=main, instagram_snapshot=instagram, now=NOW, **self._paths(root))

    def test_noncanonical_factual_type_fails_closed(self):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=exchange) as td:
            root = Path(td)
            with self.assertRaises(ValueError):
                run_bridge([{**BASE, "information_family": "market_price"}], [{**BASE, "source_code": "ig", "lineage_key": "ig"}], **self._paths(root))


if __name__ == "__main__":
    unittest.main()
