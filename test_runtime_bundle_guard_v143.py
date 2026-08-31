#!/usr/bin/env python3
from __future__ import annotations

import unittest

import auto_repair_engine
import auto_update_all
import runtime_bundle_guard_v143 as guard
from multi_channel_agent import MultiChannelCollector


class RuntimeBundleGuardV143Tests(unittest.TestCase):
    def test_bundle_contracts_pass(self):
        result = guard.audit()
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["patch"], 143)
        self.assertEqual(result["missing_file_count"], 0)
        self.assertEqual(result["issue_count"], 0)

    def test_graded_photo_is_preflight_allowlisted(self):
        self.assertIn("graded_photo_candidates.json", auto_repair_engine.SAFE_JSON_FILES)
        required = auto_repair_engine.REQUIRED_JSON_FIELDS["graded_photo_candidates.json"]
        self.assertIs(required["records"], list)
        self.assertIs(required["summary"], dict)

    def test_source_parser_failure_is_not_data_value_error(self):
        result = auto_repair_engine.analyze_error(
            "ValueError: 공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함"
        )
        self.assertEqual(result["code"], "SOURCE_STRUCTURE_CHANGED", result)

    def test_value_error_is_not_retried_as_transient_network(self):
        self.assertFalse(auto_update_all._should_retry({}, False, "ValueError: malformed data"))

    def test_graded_photo_uses_learned_exact_search(self):
        self.assertTrue(callable(getattr(MultiChannelCollector, "search_exact", None)))

    def test_manual_official_fallback_is_complete_and_reference_only(self):
        result = guard.audit()
        self.assertTrue(result["contracts"]["manual_official_fallback"], result)
        self.assertIs(result["contracts"]["manual_proof_raw_calibration"], False)
        self.assertIs(result["contracts"]["manual_proof_rejected_bytes_retained"], False)
        for name in (
            "manual_graded_photo_registration.py",
            "manual_official_proof.py",
            "manual_official_verify_bridge.js",
            "graded_photo_dashboard.js",
            "IMPORT_GRADED_LEARNING_FILES.py",
            "START_GRADED_FILE_LEARNING.sh",
        ):
            self.assertIn(name, guard.REQUIRED_FILES)


if __name__ == "__main__":
    unittest.main()
