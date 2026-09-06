#!/usr/bin/env python3
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from crosscheck_runtime_bridge import run_persisted_bridge

NOW = dt.datetime(2026, 9, 6, 0, 0, tzinfo=dt.timezone.utc)


def snapshot(
    namespace: str,
    *,
    status: str = "finalized",
    finalized_at: str = "2026-09-06T06:10:00+09:00",
    factual_type: str = "release",
    value: str = "2026-09-16",
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


class PersistedCrosscheckBridgeTests(unittest.TestCase):
    def _run(self, main_payload, instagram_payload=None):
        exchange = Path("crosscheck_exchange")
        exchange.mkdir(exist_ok=True)
        holder = tempfile.TemporaryDirectory(dir=exchange)
        root = Path(holder.name)
        main = root / "main-persisted.json"
        instagram = root / "instagram-persisted.json"
        main.write_text(json.dumps(main_payload, ensure_ascii=False), encoding="utf-8")
        if instagram_payload is not None:
            instagram.write_text(
                json.dumps(instagram_payload, ensure_ascii=False),
                encoding="utf-8",
            )
        result = run_persisted_bridge(
            main,
            instagram,
            main_output=root / "runtime-main.json",
            instagram_output=root / "runtime-instagram.json",
            report_output=root / "report.json",
            now=NOW,
        )
        return holder, root, result

    def test_finalized_fresh_snapshots_are_crosschecked(self):
        holder, root, result = self._run(
            snapshot("MARKET_ANALYSIS", lineage="main-release"),
            snapshot("IG_CARDINFO", lineage="ig-release"),
        )
        try:
            self.assertTrue(result["operational_ready"])
            self.assertEqual(result["status"], "crosschecked")
            self.assertEqual(result["agree"], 1)
            self.assertEqual(result["source_mode"], "persisted_tcg_crosscheck")
            self.assertTrue((root / "runtime-main.json").exists())
            self.assertTrue((root / "runtime-instagram.json").exists())
        finally:
            holder.cleanup()

    def test_building_and_missing_peer_are_unavailable(self):
        holder, root, result = self._run(
            snapshot("MARKET_ANALYSIS", status="building"),
            None,
        )
        try:
            self.assertFalse(result["operational_ready"])
            self.assertEqual(result["status"], "snapshot_unavailable")
            self.assertEqual(result["unavailable_reasons"]["main"], "not_finalized")
            self.assertEqual(result["unavailable_reasons"]["instagram_content"], "missing")
            self.assertFalse((root / "runtime-main.json").exists())
            self.assertFalse((root / "runtime-instagram.json").exists())
        finally:
            holder.cleanup()

    def test_stale_snapshot_is_not_current_evidence(self):
        holder, _, result = self._run(
            snapshot(
                "MARKET_ANALYSIS",
                finalized_at="2026-09-01T06:10:00+09:00",
            ),
            snapshot("IG_CARDINFO"),
        )
        try:
            self.assertFalse(result["operational_ready"])
            self.assertEqual(result["unavailable_reasons"]["main"], "stale_snapshot")
        finally:
            holder.cleanup()

    def test_noncanonical_type_fails_closed(self):
        with self.assertRaises(ValueError):
            holder, _, _ = self._run(
                snapshot("MARKET_ANALYSIS", factual_type="market_price"),
                snapshot("IG_CARDINFO"),
            )
            holder.cleanup()


if __name__ == "__main__":
    unittest.main()
