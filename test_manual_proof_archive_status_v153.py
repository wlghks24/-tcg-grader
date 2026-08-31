#!/usr/bin/env python3
from __future__ import annotations

import unittest

import manual_dual_photo_registration as dual
import manual_graded_photo_registration as manual_photo
import verified_slab_training_archive_v152 as archive


class ManualProofArchiveStatusV153Tests(unittest.TestCase):
    def setUp(self):
        dual.apply()

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
            "official_result": False,
            "status": "manual_official_reference",
            "verification_state": "manual_official_proof_matched",
            "manual_official_proof_state": "matched",
            "manual_official_proof_registered": True,
            "manual_official_proof_match_mode": "official_page_company_cert_plus_exact_slab_ocr_grade",
        }

    def test_recent_public_row_exposes_manual_proof_completion(self):
        public = manual_photo._public_row(self._row())
        self.assertTrue(public["manual_official_proof_registered"], public)
        self.assertEqual(public["manual_official_proof_state"], "matched")
        self.assertEqual(public["verification_state"], "manual_official_proof_matched")
        self.assertTrue(public["front_back_pair_complete"])

    def test_matched_manual_proof_is_archive_eligible(self):
        row = self._row()
        self.assertEqual(archive._verification_kind(row), "manual_official_reference")
        self.assertEqual(archive._identity(row), ("PSA", "160600294", 10.0, "onepiece"))
        self.assertTrue(archive._eligible(row))


if __name__ == "__main__":
    unittest.main()
