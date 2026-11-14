#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

import release_parser_learning as learning


class ReleaseParserLearningTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.path = self.root / "release_parser_learning.json"
        self.allowed = ("html_chain_v1", "official_result_api_v1")

    def test_unicode_source_label_is_safe_and_persisted(self):
        ok = learning.record_attempt(
            self.path,
            "Pokémon JP",
            "official_result_api_v1",
            allowed_strategies=self.allowed,
            success=True,
            row_count=20,
            outcome="recovered",
            fingerprint="0123456789abcdef",
        )
        self.assertTrue(ok)
        summary = learning.public_summary(self.path, {"Pokémon JP": self.allowed})
        self.assertEqual(
            summary["sources"]["Pokémon JP"]["preferred_strategy"],
            "official_result_api_v1",
        )

    def test_unknown_disk_strategy_cannot_execute_or_be_preferred(self):
        learning.record_attempt(
            self.path,
            "Pokémon JP",
            "official_result_api_v1",
            allowed_strategies=self.allowed,
            success=True,
            row_count=5,
            outcome="success",
        )
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["sources"]["Pokémon JP"]["last_successful_strategy"] = "unknown_disk_code"
        raw["sources"]["Pokémon JP"]["strategies"]["unknown_disk_code"] = {
            "successes": 999999,
            "failures": 0,
            "last_row_count": 99999,
        }
        self.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        order = learning.strategy_order(
            self.path,
            "Pokémon JP",
            self.allowed,
            self.allowed,
        )
        self.assertEqual(order, list(self.allowed))
        self.assertNotIn("unknown_disk_code", order)

    def test_failure_then_success_resets_consecutive_failures(self):
        self.assertTrue(
            learning.record_attempt(
                self.path,
                "Pokémon JP",
                "html_chain_v1",
                allowed_strategies=self.allowed,
                success=False,
                row_count=0,
                outcome="zero_verified_rows",
            )
        )
        self.assertTrue(
            learning.record_attempt(
                self.path,
                "Pokémon JP",
                "official_result_api_v1",
                allowed_strategies=self.allowed,
                success=True,
                row_count=12,
                outcome="recovered",
            )
        )
        summary = learning.public_summary(self.path, {"Pokémon JP": self.allowed})
        source = summary["sources"]["Pokémon JP"]
        self.assertEqual(source["consecutive_failures"], 0)
        self.assertEqual(source["preferred_strategy"], "official_result_api_v1")

    def test_unapproved_strategy_is_rejected(self):
        ok = learning.record_attempt(
            self.path,
            "Pokémon JP",
            "shell_command_from_disk",
            allowed_strategies=self.allowed,
            success=True,
            row_count=999,
            outcome="success",
        )
        self.assertFalse(ok)
        self.assertFalse(self.path.exists())


    def test_malformed_counter_fields_are_bounded_without_losing_preference(self):
        raw = {"version": 1, "sources": {"Pokémon JP": {
            "last_successful_strategy": "official_result_api_v1",
            "last_row_count": "not-a-number",
            "consecutive_failures": True,
            "strategies": {"official_result_api_v1": {
                "successes": [], "failures": "NaN", "last_row_count": 999999999,
            }},
        }}}
        self.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        source = learning.load_memory(self.path)["sources"]["Pokémon JP"]
        self.assertEqual(source["last_row_count"], 0)
        self.assertEqual(source["consecutive_failures"], 0)
        stats = source["strategies"]["official_result_api_v1"]
        self.assertEqual((stats["successes"], stats["failures"], stats["last_row_count"]), (0, 0, 100000))
        self.assertEqual(learning.strategy_order(self.path, "Pokémon JP", self.allowed, self.allowed)[0],
                         "official_result_api_v1")
        self.assertEqual(learning.public_summary(self.path, {"Pokémon JP": self.allowed})
                         ["sources"]["Pokémon JP"]["last_row_count"], 0)

    def test_counter_types_and_unknown_strategy_fail_closed(self):
        for bad in (False, 1.5, {}, "9" * 100, "1e9", "-2", None):
            with self.subTest(value=repr(bad)[:40]):
                raw = {"version": 1, "sources": {"Pokémon JP": {
                    "last_successful_strategy": "not_allowlisted",
                    "last_row_count": bad, "consecutive_failures": "2",
                    "strategies": {"html_chain_v1": {"successes": bad}},
                }}}
                self.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
                source = learning.load_memory(self.path)["sources"]["Pokémon JP"]
                self.assertEqual(source["last_row_count"], 0)
                self.assertEqual(source["consecutive_failures"], 2)
                self.assertEqual(source["strategies"]["html_chain_v1"]["successes"], 0)
                self.assertEqual(learning.strategy_order(self.path, "Pokémon JP", self.allowed, self.allowed),
                                 list(self.allowed))


if __name__ == "__main__":
    unittest.main()
