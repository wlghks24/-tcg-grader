#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest.mock import patch

import manual_graded_photo_registration as manual_photo
import manual_official_verified_integration_v154 as integration


class ManualOfficialVerifiedIntegrationV154Tests(unittest.TestCase):
    def _row(self):
        return {
            "registration_id": "manual-20260831173419-abcdef123456",
            "company": "PSA",
            "game": "onepiece",
            "claimed_grade": 10.0,
            "certification_id": "160600294",
            "image_path": "GRADE_TRAINING_INBOX/manual/202608/front.jpg",
            "image_sha256": "a" * 64,
            "back_image_path": "GRADE_TRAINING_INBOX/manual/202608/back.jpg",
            "back_image_sha256": "b" * 64,
            "front_back_pair_complete": True,
            "manual_official_proof_path": "GRADE_TRAINING_INBOX/manual_official_proof/202608/proof.jpg",
            "manual_official_proof_sha256": "c" * 64,
            "manual_official_proof_registered": True,
            "manual_official_proof_state": "matched",
            "manual_official_proof_at": "2026-08-31T17:36:00Z",
            "manual_official_proof_match_mode": "official_page_company_cert_plus_exact_slab_ocr_grade",
            "official_reference_url": "https://www.psacard.com/cert/160600294",
            "official_result": False,
            "status": "manual_official_reference",
            "verification_state": "manual_official_proof_matched",
            "learning_eligibility": "reference_only_pending_live_official_verification",
            "training_eligible": False,
            "raw_grade_calibration_eligible": False,
            "quarantine_reasons": ["manual_official_page_proof_only", "live_official_lookup_pending"],
        }

    def test_strict_matched_front_back_proof_is_promotable(self):
        ready, reason = integration._identity_gate(self._row())
        self.assertTrue(ready, reason)

    def test_missing_back_pair_is_not_promotable(self):
        row = self._row()
        row["front_back_pair_complete"] = False
        ready, reason = integration._identity_gate(row)
        self.assertFalse(ready)
        self.assertEqual(reason, "front_back_pair_incomplete")

    def test_promotion_sets_official_result_but_never_raw_calibration(self):
        row = self._row()
        registry = {"schema_version": 1, "registrations": [row]}
        saved = []

        with (
            patch.object(manual_photo, "_registry", return_value=registry),
            patch.object(manual_photo, "_save_registry", side_effect=lambda payload: saved.append(payload)),
            patch.object(manual_photo, "_publish_verified", return_value=(True, None)) as publish,
            patch.object(integration, "_stored_evidence_present", return_value=True),
            patch.object(integration, "_promote_reference_file"),
            patch.object(manual_photo, "_record_collection_gap"),
        ):
            result = integration.promote_registration(row["registration_id"])

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["promoted"], result)
        self.assertTrue(saved)
        promoted = saved[-1]["registrations"][0]
        self.assertTrue(promoted["official_result"])
        self.assertEqual(promoted["verification_state"], "verified_manual_official_page")
        self.assertEqual(promoted["official_verification_source"], "user_browser_official_page")
        self.assertEqual(promoted["learning_eligibility"], "verified_slab_reference")
        self.assertFalse(promoted["training_eligible"])
        self.assertFalse(promoted["raw_grade_calibration_eligible"])
        publish.assert_called_once()

    def test_registry_conflict_blocks_official_promotion(self):
        row = self._row()
        registry = {"schema_version": 1, "registrations": [row]}
        saved = []
        with (
            patch.object(manual_photo, "_registry", return_value=registry),
            patch.object(manual_photo, "_save_registry", side_effect=lambda payload: saved.append(payload)),
            patch.object(manual_photo, "_publish_verified", return_value=(False, "persisted_official_grade_conflict")),
            patch.object(integration, "_stored_evidence_present", return_value=True),
        ):
            result = integration.promote_registration(row["registration_id"])
        self.assertFalse(result["ok"])
        self.assertFalse(result["promoted"])
        self.assertFalse(saved[-1]["registrations"][0]["official_result"])
        self.assertEqual(saved[-1]["registrations"][0]["status"], "quarantine")


if __name__ == "__main__":
    unittest.main()
