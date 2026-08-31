#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from unittest import mock

import legacy_ocr_registry_cleanup_v149 as cleanup


def row_template(**updates):
    row = {
        "registration_id": "manual-20260831123456-abcdef123456",
        "company": "PSA",
        "game": "pokemon",
        "claimed_grade": 10.0,
        "certification_id": "12345678",
        "ocr_certification_id": "12345678",
        "official_result": False,
        "manual_official_proof_registered": False,
        "verification_state": "manual_official_verification_required",
        "status": "pending_manual_official_verification",
        "manual_identity_complete": True,
        "missing_identity_fields": [],
        "training_eligible": False,
        "raw_grade_calibration_eligible": False,
        "quarantine_reasons": [],
    }
    row.update(updates)
    return row


class LegacyOcrRegistryCleanupV149Tests(unittest.TestCase):
    def _run(self, row):
        registry = {"registrations": [copy.deepcopy(row)]}
        with mock.patch.object(cleanup.manual_photo, "_registry", return_value=registry), \
             mock.patch.object(cleanup.manual_photo, "_save_registry") as save:
            result = cleanup.clean_registry()
        return result, registry["registrations"][0], save

    def test_invalid_word_fragment_is_cleared_and_requires_manual_input(self):
        result, saved, save = self._run(row_template(certification_id="IFICATE", ocr_certification_id="IFICATE"))
        self.assertEqual(result["invalid_certifications_cleared"], 1)
        self.assertEqual(saved["certification_id"], "")
        self.assertIsNone(saved["ocr_certification_id"])
        self.assertFalse(saved["manual_identity_complete"])
        self.assertIn("certification_id", saved["missing_identity_fields"])
        self.assertEqual(saved["verification_state"], "manual_input_required")
        self.assertFalse(saved["official_result"])
        self.assertFalse(saved["training_eligible"])
        save.assert_called_once()

    def test_common_ocr_digit_confusions_are_normalized(self):
        result, saved, save = self._run(row_template(certification_id="12O4S678", ocr_certification_id="12O4S678"))
        self.assertEqual(result["certifications_normalized"], 1)
        self.assertEqual(saved["certification_id"], "12045678")
        self.assertEqual(saved["ocr_certification_id"], "12045678")
        save.assert_called_once()

    def test_live_official_verified_row_is_never_changed(self):
        result, saved, save = self._run(row_template(certification_id="IFICATE", official_result=True))
        self.assertEqual(result["trusted_rows_skipped"], 1)
        self.assertEqual(saved["certification_id"], "IFICATE")
        save.assert_not_called()

    def test_manual_official_proof_row_is_never_changed(self):
        result, saved, save = self._run(row_template(
            certification_id="IFICATE",
            manual_official_proof_registered=True,
            verification_state="manual_official_proof_matched",
        ))
        self.assertEqual(result["trusted_rows_skipped"], 1)
        self.assertEqual(saved["certification_id"], "IFICATE")
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
