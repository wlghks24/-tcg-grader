#!/usr/bin/env python3
"""Offline, deterministic V1007 real collector/wrapper identity contract tests."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import wyyyes_market_source as binding
import update_market_prices_parallel_v260 as wrapper

ROOT = Path(__file__).resolve().parents[2]


class WyyyesVerifiedIdentityV1007Tests(unittest.TestCase):
    def setUp(self):
        self.stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.quote = {
            "platform": "WYYYES",
            "title": "Mew V S8 SR 106/100 일본판 포켓몬 카드",
            "game": "Pokémon",
            "card_region": "JP",
            "card_number": "106/100",
            "price": 600000,
            "currency": "KRW",
            "price_type": "asking",
            "is_completed_sale": False,
            "source_url": "https://wyyyes.com/category/pokemon-card/6502248",
            "collected_at": self.stamp,
        }
        self.entry = {
            "game": "pokemon",
            "region": "JP",
            "card_name": "Mew V",
            "card_number": "106/100",
            "set_code": "S8",
            "printing": "SR",
            "identity_verified": True,
            "source_grade": "official_card_catalog",
            "source_url": "https://www.pokemon-card.com/card-search/details.php/card/12345",
            "reviewed_on": datetime.now(timezone.utc).date().isoformat(),
        }
        self.catalog = {
            "schema": binding.CATALOG_SCHEMA,
            "reviewed_for_auto_price_link": True,
            "entries": [self.entry],
        }

    def test_bundled_catalog_is_empty_and_auto_confirmation_held(self):
        path = ROOT / "card_identity_reference_catalog.json"
        loaded = binding.load_reviewed_catalog(path)
        self.assertIsInstance(loaded, dict)
        self.assertEqual(21, len(loaded["cards"]))
        self.assertTrue(loaded["reference_only"])
        self.assertFalse(loaded["automatic_confirmation"])
        output = binding.bind_quote(self.quote, loaded)
        self.assertNotIn("card_name", output)
        self.assertEqual("HOLD_UNVERIFIED", output["identity_binding_status"])

    def test_unique_official_exact_card_printing_can_bind(self):
        output = binding.bind_quote(self.quote, self.catalog)
        self.assertEqual("VERIFIED_EXACT", output["identity_binding_status"])
        self.assertTrue(output["identity_verified"])
        self.assertEqual("Mew V", output["card_name"])
        self.assertEqual("S8", output["identity_set_code"])
        self.assertEqual("SR", output["identity_printing"])
        self.assertEqual(self.entry["source_url"], output["identity_source_url"])
        self.assertEqual("asking", output["price_type"])
        self.assertFalse(output["is_completed_sale"])
        self.assertEqual(600000, output["price"])
        self.assertEqual("KRW", output["currency"])

    def test_renamed_printing_set_number_region_game_and_title_collisions_hold(self):
        cases = (
            {"title": "Mew VMAX S8 SR 106/100 일본판 포켓몬 카드"},
            {"title": "Mew V S9 SR 106/100 일본판 포켓몬 카드"},
            {"title": "Mew V S8 RR 106/100 일본판 포켓몬 카드"},
            {"title": "Mew V S8 SR 1106/100 일본판 포켓몬 카드"},
            {"title": "Mew V S8 SR 106/1000 일본판 포켓몬 카드"},
            {"title": "Mew V S8 SR 일본판 포켓몬 카드"},
            {"card_number": "112/100"},
            {"card_number": "106/1000"},
            {"card_region": "KR"},
            {"game": "ONE PIECE"},
            {"game": "NARUTO"},
            {"game": ""},
            {"title": ""},
        )
        for case in cases:
            with self.subTest(case=case):
                row = binding.bind_quote({**self.quote, **case}, self.catalog)
                self.assertEqual("HOLD_UNVERIFIED", row["identity_binding_status"])
                self.assertNotIn("card_name", row)

    def test_holo_does_not_treat_reverse_holo_as_normal_holo(self):
        base = {**self.entry, "printing": "Holo"}
        catalog = {**self.catalog, "entries": [base]}
        ordinary = {**self.quote, "title": "Mew V S8 Holo 106/100 일본판"}
        reversed_ = {**self.quote, "title": "Mew V S8 Reverse Holo 106/100 일본판"}
        self.assertEqual("VERIFIED_EXACT", binding.bind_quote(ordinary, catalog)["identity_binding_status"])
        self.assertEqual("HOLD_UNVERIFIED", binding.bind_quote(reversed_, catalog)["identity_binding_status"])

    def test_duplicate_approved_card_records_never_select_first(self):
        other = {**self.entry, "source_url": "https://pokemon-card.com/card-search/details.php/card/67890"}
        catalog = {**self.catalog, "entries": [self.entry, other]}
        self.assertEqual("HOLD_UNVERIFIED", binding.bind_quote(self.quote, catalog)["identity_binding_status"])

    def test_reference_only_and_forged_previous_quote_do_not_auto_bind(self):
        old = {
            **self.quote, "card_name": "Mew V",
            "identity_verified": True, "identity_binding_status": "VERIFIED_EXACT",
            "identity_source_url": self.entry["source_url"],
        }
        for source in (None, {}, {"cards": [self.entry], "reference_only": True},
                       {**self.catalog, "reviewed_for_auto_price_link": False}):
            with self.subTest(source=source):
                row = binding.bind_quote(old, source)
                self.assertEqual("HOLD_UNVERIFIED", row["identity_binding_status"])
                self.assertNotIn("identity_verified", row)
                self.assertNotIn("card_name", row)
                self.assertNotIn("identity_source_url", row)

    def test_approval_source_and_date_are_not_self_attested(self):
        wrongs = (
            {"identity_verified": False},
            {"source_grade": "reference_only"},
            {"source_url": "https://pokemon-card.com.evil.invalid/xyz"},
            {"source_url": "http://www.pokemon-card.com/card/1"},
            {"source_url": "https://www.pokemon-card.com@evil.invalid/123"},
            {"source_url": "https://www.pokemon-card.com:8443/card/1"},
            {"reviewed_on": "2099-01-01"},
            {"reviewed_on": "not-a-day"},
            {"set_code": ""},
            {"printing": ""},
        )
        for bad in wrongs:
            with self.subTest(bad=bad):
                catalog = {**self.catalog, "entries": [{**self.entry, **bad}]}
                self.assertEqual("HOLD_UNVERIFIED", binding.bind_quote(self.quote, catalog)["identity_binding_status"])

    def test_invalid_quote_price_time_origin_and_currency_hold(self):
        cases = (
            {"price": 0}, {"price": float("nan")}, {"price": float("inf")},
            {"price": 1000000000}, {"currency": "USD"},
            {"collected_at": "2020-01-01T00:00:00+00:00"},
            {"collected_at": "2050-01-01T00:00:00+00:00"},
            {"collected_at": "missing"},
            {"source_url": "https://wyyyes.com.evil.invalid/category/pokemon-card/1"},
            {"source_url": "https://wyyyes.com/not-a-card/1"},
            {"source_url": "http://wyyyes.com/category/pokemon-card/1"},
            {"platform": "FAKE"},
        )
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual("HOLD_UNVERIFIED", binding.bind_quote({**self.quote, **case}, self.catalog)["identity_binding_status"])

    def test_naruto_without_confirmed_official_card_catalog_stays_hold(self):
        row = {**self.quote, "game": "NARUTO", "title": "Mew V S8 SR 106/100 나루토 카드"}
        record = {**self.entry, "game": "naruto"}
        cat = {**self.catalog, "entries": [record]}
        self.assertEqual("HOLD_UNVERIFIED", binding.bind_quote(row, cat)["identity_binding_status"])

    def test_catalog_io_rejects_symlinks_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.json"
            self.assertIsNone(binding.load_reviewed_catalog(missing))
            huge = root / "huge.json"
            huge.write_bytes(b"x" * (binding.MAX_CATALOG_BYTES + 1))
            self.assertIsNone(binding.load_reviewed_catalog(huge))
            corrupt = root / "bad.json"
            corrupt.write_text("{invalid json", encoding="utf-8")
            self.assertIsNone(binding.load_reviewed_catalog(corrupt))
            link = root / "link.json"
            try:
                link.symlink_to(huge)
            except (OSError, NotImplementedError):
                pass
            else:
                self.assertIsNone(binding.load_reviewed_catalog(link))

    def test_wrapper_sanitizes_previous_and_fallback_rows(self):
        poisoned = {**self.quote, "card_name": "Mew V", "identity_verified": True}
        db = {"platform_quotes": {"WYYYES": [poisoned]}}
        with patch.object(wrapper.wyyyes, "collect_quotes", return_value={
            "quotes": [poisoned], "status": "ok", "quote_count": 1,
            "completed_sale_count": 0,
        }):
            result = wrapper._merge_wyyyes_quotes(db)
        self.assertEqual(1, result["identity_hold_count"])
        self.assertEqual(0, result["identity_verified_count"])
        self.assertNotIn("card_name", db["platform_quotes"]["WYYYES"][0])
        self.assertTrue(db["platform_quote_policy"]["exact_reviewed_card_identity_required"])
        self.assertFalse(db["platform_quote_policy"]["canonical_market_price_overwrite"])
        with patch.object(wrapper.wyyyes, "collect_quotes", side_effect=OSError("offline")):
            again = wrapper._merge_wyyyes_quotes(db)
        self.assertEqual("collector_error", again["status"])
        self.assertEqual(1, again["identity_hold_count"])
        self.assertNotIn("card_name", db["platform_quotes"]["WYYYES"][0])

    def test_wrapper_can_bind_only_explicitly_approved_fixture(self):
        db = {}
        with patch.object(wrapper.verified, "load_reviewed_catalog", return_value=self.catalog):
            with patch.object(wrapper.wyyyes, "collect_quotes", return_value={
                "quotes": [self.quote], "status": "ok", "quote_count": 1,
                "completed_sale_count": 0,
            }):
                result = wrapper._merge_wyyyes_quotes(db)
        self.assertEqual(1, result["identity_verified_count"])
        self.assertEqual("Mew V", db["platform_quotes"]["WYYYES"][0]["card_name"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
