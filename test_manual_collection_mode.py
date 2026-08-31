#!/usr/bin/env python3
from __future__ import annotations

import os
import unittest

import manual_collection_mode as mode


class ManualCollectionModeTests(unittest.TestCase):
    def test_apply_disables_automatic_official_lookup(self):
        status = mode.apply()
        self.assertTrue(status["ok"], status)
        self.assertFalse(status["automatic_official_lookup"])
        self.assertFalse(status["manual_registration_auto_official_lookup"])
        self.assertTrue(status["certification_front_back_pair_required"])
        self.assertTrue(status["grouped_by_game_only"])
        self.assertFalse(status["grader_subfolders_created"])
        self.assertTrue(status["manual_front_back_upload"])
        self.assertTrue(status["back_stored_separately"])
        self.assertEqual(os.environ.get("TCG_DISABLE_AUTO_GRADER_LOOKUP"), "1")
        runtime = mode.status()
        self.assertTrue(runtime["collector_manual_only"], runtime)
        self.assertTrue(runtime["manual_registration_manual_only"], runtime)
        self.assertTrue(runtime["collector_syncs_manual_pairs"], runtime)
        self.assertTrue(runtime["environment_no_network_gate"], runtime)
        self.assertTrue(runtime["grouped_by_game_only"], runtime)
        self.assertFalse(runtime["grader_subfolders_created"], runtime)

    def test_apply_is_idempotent(self):
        first = mode.apply()
        second = mode.apply()
        self.assertTrue(first["ok"] and second["ok"])
        runtime = mode.status()
        self.assertTrue(runtime["ok"], runtime)
        self.assertTrue(runtime["collector_syncs_manual_pairs"], runtime)
        self.assertTrue(runtime["manual_front_back_upload"], runtime)

    def test_ocr_v147_is_applied_with_manual_mode(self):
        mode.apply()
        import manual_dual_photo_registration as dual
        import ocr_accuracy_boost_v147 as ocr
        import public_ocr_accuracy_boost_v147 as public_ocr
        dual_status = dual.status()
        self.assertTrue(dual_status["ocr_accuracy_boost"], dual_status)
        self.assertTrue(dual_status["public_ocr_accuracy_boost"], dual_status)
        self.assertTrue(ocr.status()["ok"])
        self.assertTrue(public_ocr.status()["ok"])

    def test_registry_only_verifier_never_calls_live_lookup(self):
        rows = [{
            "company": "PSA", "certification_id": "12345678", "grade": 10,
            "game": "pokemon", "title": "Pikachu PSA 10",
        }]
        output, stats = mode._registry_only_official_verify_rows(rows, {}, max_live=99)
        self.assertEqual(stats["live_attempts"], 0, stats)
        self.assertEqual(stats["manual_verification_required"], 1, stats)
        self.assertTrue(output[0]["manual_official_verification_required"])
        self.assertFalse(output[0]["official_result"])

    def test_existing_verified_registry_still_works_offline(self):
        rows = [{"company": "BGS", "certification_id": "0012345678", "grade": 9.5, "game": "onepiece"}]
        output, stats = mode._registry_only_official_verify_rows(rows, {("BGS", "0012345678"): 9.5})
        self.assertEqual(stats["live_attempts"], 0, stats)
        self.assertTrue(output[0]["official_result"])
        self.assertEqual(output[0]["verification_method"], "persisted_official_registry")


if __name__ == "__main__":
    unittest.main()
