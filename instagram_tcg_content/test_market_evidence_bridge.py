#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from instagram_tcg_content.market_evidence_bridge import (
    persist_evidence_ledger,
    verify_market_records,
)
from instagram_tcg_content.persisted_crosscheck_export import build_snapshot

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 9, 11, 9, 0, tzinfo=KST)
ROOT = Path(__file__).resolve().parent


def sale(source: str, lineage: str, amount: float, finality: str = "platform_reported_sold") -> dict:
    return {
        "fact_type": "completed_sale",
        "canonical_identity": "Pikachu 001 RAW NM",
        "game": "pokemon",
        "region": "US",
        "language": "EN",
        "item_or_lot_locator": f"https://example.com/sale/{lineage}",
        "sold_or_completed_status": "sold",
        "event_or_trade_time": "2026-09-10T10:00:00-04:00",
        "currency": "USD",
        "realized_amount": amount,
        "condition_or_grade_basis": "RAW_NM",
        "transaction_finality": finality,
        "price_basis": "item_price",
        "source_code": source,
        "source_locator": f"https://example.com/source/{lineage}",
        "unit_type": "single_card",
        "quantity_basis": "1",
        "underlying_lineage_key": lineage,
        "checked_at": "2026-09-11T08:00:00+09:00",
    }


def market(source: str, lineage: str, value: float) -> dict:
    return {
        "fact_type": "market_reference",
        "canonical_identity": "Pikachu 001 RAW NM",
        "game": "pokemon",
        "region": "US",
        "language": "EN",
        "value": value,
        "currency": "USD",
        "value_type": "market_reference",
        "condition_basis": "RAW_NM",
        "source_code": source,
        "source_locator": f"https://example.com/market/{lineage}",
        "unit_type": "single_card",
        "quantity_basis": "1",
        "underlying_lineage_key": lineage,
        "checked_at": "2026-09-11T08:00:00+09:00",
    }


class MarketEvidenceBridgeTests(unittest.TestCase):
    def test_platform_reported_sales_verify_without_becoming_settled(self):
        report = verify_market_records([
            sale("EBAY", "ebay:1", 100),
            sale("HERITAGE", "heritage:1", 110),
        ], now=NOW)
        self.assertEqual(report["verified_completed_sale_count"], 2, report)
        finalities = {row["identity"]["transaction_finality"] for row in report["verified_records"]}
        self.assertEqual(finalities, {"platform_reported_sold"})
        self.assertTrue(report["safety"]["finality_class_preserved"])

    def test_different_finality_classes_are_not_pooled(self):
        report = verify_market_records([
            sale("EBAY", "ebay:2", 100, "auction_house_realized"),
            sale("HERITAGE", "heritage:2", 101, "platform_reported_sold"),
        ], now=NOW)
        self.assertEqual(report["verified_completed_sale_count"], 0, report)
        self.assertEqual(len(report["sale_verification_results"]), 2, report)
        self.assertTrue(all(x["status"] != "verified" for x in report["sale_verification_results"]))

    def test_settlement_unknown_is_never_auto_promoted(self):
        report = verify_market_records([
            sale("EBAY", "ebay:3", 100, "settlement_unknown"),
            sale("HERITAGE", "heritage:3", 101, "settlement_unknown"),
        ], now=NOW)
        self.assertEqual(report["verified_completed_sale_count"], 0)
        self.assertEqual(len(report["rejected"]), 2)
        self.assertTrue(all("SALE_SETTLEMENT_UNKNOWN_NOT_PROMOTABLE" in x["error"] for x in report["rejected"]))

    def test_market_references_verify_as_derived_median_range(self):
        report = verify_market_records([
            market("PRICECHARTING", "pc:1", 100),
            market("TCGPLAYER_MARKET", "tcg:1", 110),
        ], now=NOW)
        self.assertEqual(report["verified_market_reference_count"], 2, report)
        refs = [r for r in report["verified_records"] if r["fact_type"] == "market_reference"]
        self.assertEqual({r["value"] for r in refs}, {"105"})
        self.assertEqual({r["identity"]["market_reference_low"] for r in refs}, {"100"})
        self.assertEqual({r["identity"]["market_reference_high"] for r in refs}, {"110"})

    def test_wide_market_reference_dispersion_fails_closed(self):
        report = verify_market_records([
            market("PRICECHARTING", "pc:2", 100),
            market("TCGPLAYER_MARKET", "tcg:2", 200),
        ], now=NOW)
        self.assertEqual(report["verified_market_reference_count"], 0, report)
        self.assertEqual(report["market_reference_verification_results"][0]["uncertainty_reason"], "MARKET_REFERENCE_DISPERSION_TOO_WIDE")

    def test_same_lineage_conflict_is_quarantined(self):
        report = verify_market_records([
            sale("EBAY", "shared:1", 100),
            sale("HERITAGE", "shared:1", 130),
        ], now=NOW)
        self.assertEqual(report["verified_completed_sale_count"], 0, report)
        self.assertEqual(len(report["rejected"]), 2)
        self.assertTrue(all(x["error"] == "EVIDENCE_LINEAGE_CONFLICT" for x in report["rejected"]))

    def test_verified_market_rows_are_accepted_by_current_snapshot_exporter(self):
        report = verify_market_records([
            market("PRICECHARTING", "pc:3", 100),
            market("TCGPLAYER_MARKET", "tcg:3", 110),
        ], now=NOW)
        snapshot = build_snapshot(report["verified_records"], now=NOW)
        self.assertEqual(snapshot["status"], "finalized", snapshot)
        self.assertEqual(len(snapshot["facts"]), 2, snapshot)
        self.assertTrue(all(x["fact_type"] == "market_reference" for x in snapshot["facts"]))

    def test_evidence_ledger_preserves_raw_transaction_basis(self):
        report = verify_market_records([
            sale("EBAY", "ebay:4", 100),
            sale("HERITAGE", "heritage:4", 110),
        ], now=NOW)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ledger.json"
            saved = persist_evidence_ledger(report, path)
            self.assertEqual(len(saved["rows"]), 2)
            finalities = {x["raw_evidence"]["transaction_finality"] for x in saved["rows"]}
            self.assertEqual(finalities, {"platform_reported_sold"})
            self.assertTrue(path.is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)


if __name__ == "__main__":
    unittest.main()
