#!/usr/bin/env python3
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from instagram_tcg_content.collection_health import (
    EXPECTED_OUTPUTS,
    MIN_COMPLETED_SALES_PER_OUTPUT,
    VERIFICATION_ENGINE,
    VERIFICATION_MODE,
    audit_collection,
)
from instagram_tcg_content.persisted_crosscheck_export import export_snapshot


class CollectionHealthTests(unittest.TestCase):
    def _routes(self):
        return {
            "provider_groups": {
                game: {
                    "official_primary": ["official"],
                    "completed_sale_original": ["sale-a", "sale-b"],
                    "grading_auction_original": [],
                    "market_reference": ["market-a", "market-b"],
                }
                for game in ("pokemon", "one_piece", "naruto")
            }
        }

    def _official_facts(self):
        return [
            {
                "canonical_key": f"{game}|release|{language.lower()}",
                "fact_type": "release",
                "lineage_key": f"{game}:{language}:release",
                "identity": {"game": game},
                "language": language,
                "source_locator": "https://example.invalid/official",
                "verification_status": "verified",
                "verification_mode": VERIFICATION_MODE,
                "verification_engine": VERIFICATION_ENGINE,
            }
            for game, language in EXPECTED_OUTPUTS
        ]

    def _facts(self):
        facts = self._official_facts()
        for game, language in EXPECTED_OUTPUTS:
            for index in range(MIN_COMPLETED_SALES_PER_OUTPUT):
                facts.append({
                    "canonical_key": f"{game}|sale-{index}|{language.lower()}",
                    "fact_type": "completed_sale",
                    "lineage_key": f"{game}:{language}:sale:{index}",
                    "identity": {"game": game},
                    "language": language,
                    "source_locator": "https://example.invalid/sale",
                    "verification_status": "verified",
                    "verification_mode": VERIFICATION_MODE,
                    "verification_engine": VERIFICATION_ENGINE,
                })
        return facts

    def _snapshot(self, facts):
        return {
            "namespace": "IG_CARDINFO",
            "status": "finalized",
            "built_at": "2026-09-09T20:30:00+09:00",
            "facts": facts,
            "validation": {"write_readback_verified": True},
            "latest_attempt": {"status": "verified_facts_written"},
        }

    def test_ready_snapshot_requires_fresh_six_output_matrix(self):
        report = audit_collection(
            self._snapshot(self._facts()),
            self._routes(),
            now=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(report["production_ready"], report)
        self.assertTrue(report["general_cardinfo_ready"], report)
        self.assertTrue(report["market_price_ready"], report)

    def test_verified_general_cardinfo_is_not_blocked_by_missing_sales(self):
        report = audit_collection(
            self._snapshot(self._official_facts()),
            self._routes(),
            now=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(report["production_ready"], report)
        self.assertTrue(report["general_cardinfo_ready"], report)
        self.assertFalse(report["market_price_ready"], report)
        self.assertEqual(report["status"], "GENERAL_READY_MARKET_NOT_READY")
        self.assertIn("COMPLETED_SALE_COVERAGE_INSUFFICIENT", report["reasons"])
        self.assertEqual(
            report["next_action"],
            "PROCEED_GENERAL_CARDINFO_WITHOUT_UNVERIFIED_MARKET_SECTIONS",
        )

    def test_stale_or_thin_snapshot_fails_closed(self):
        snapshot = {
            "namespace": "IG_CARDINFO",
            "status": "finalized",
            "built_at": "2026-09-06T20:30:00+09:00",
            "facts": self._facts()[:1],
            "validation": {"write_readback_verified": True},
            "latest_attempt": {"status": "NO_VERIFIED_FACTS"},
        }
        report = audit_collection(
            snapshot,
            self._routes(),
            now=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
        )
        self.assertFalse(report["production_ready"], report)
        self.assertFalse(report["general_cardinfo_ready"], report)
        self.assertIn("COMPLETED_SALE_COVERAGE_INSUFFICIENT", report["reasons"])
        self.assertTrue(any(x.startswith("SNAPSHOT_STALE:") for x in report["reasons"]))

    def test_persisted_snapshot_records_failed_latest_attempt_and_rejects_nonlocal_provenance(self):
        row = {
            "information_family": "official_release",
            "canonical_key": "pokemon|release|kr",
            "identity": {"game": "pokemon"},
            "value": "2026-09-16",
            "language": "KR",
            "source_code": "pokemon-official",
            "source_locator": "https://example.invalid/pokemon",
            "checked_at_kst": "2026-09-09T06:30:00+09:00",
            "verification": "verified",
            "verification_mode": VERIFICATION_MODE,
            "verification_engine": VERIFICATION_ENGINE,
            "lineage_key": "ig-release-1",
        }
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "factual_snapshot.json"
            first = export_snapshot([row], path)
            self.assertEqual(first["latest_attempt"]["status"], "verified_facts_written")

            empty = export_snapshot([{**row, "verification": "candidate"}], path)
            self.assertEqual(empty["latest_attempt"]["status"], "NO_VERIFIED_FACTS")
            reread = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(reread["latest_attempt"]["status"], "NO_VERIFIED_FACTS")
            self.assertEqual(len(reread["facts"]), 1)

            with self.assertRaisesRegex(ValueError, "Instagram-local verification mode"):
                export_snapshot([{**row, "verification_mode": "WRONG"}], path)


if __name__ == "__main__":
    unittest.main()
