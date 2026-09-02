#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from unittest import mock

import manual_official_proof as proof

REGISTRATION_ID = "manual-20260831123456-abcdef123456"


def row_template(**updates):
    row = {
        "registration_id": REGISTRATION_ID,
        "created_at": "2026-08-31T12:34:56Z",
        "updated_at": "2026-08-31T12:34:56Z",
        "game": "onepiece",
        "company": "PSA",
        "claimed_grade": 10.0,
        "certification_id": "160600294",
        "official_result": False,
        "status": "pending_official_verification",
        "verification_state": "deferred_by_cooldown",
        "quarantine_reasons": ["official_lookup_not_confirmed"],
        "manual_official_proof_registered": False,
        "ocr_company": "PSA",
        "ocr_grade": 10.0,
        "ocr_certification_id": "160600294",
    }
    row.update(updates)
    return row


class ManualOfficialProofTests(unittest.TestCase):
    def _patch_common(self, registry, evidence, text="OCR"):
        return mock.patch.multiple(
            proof.manual_photo,
            _registry=mock.Mock(return_value=registry),
            _decode_image=mock.Mock(return_value=(b"x" * 2048, ".jpg", 900, 1400)),
            _ocr_image=mock.Mock(return_value=(text, None, {}, evidence)),
        )

    def test_exact_match_is_manual_official_reference_never_raw(self):
        registry = {"registrations": [row_template()]}
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "160600294"}
        with self._patch_common(registry, evidence, "PSA #160600294 GEM MT 10"), \
             mock.patch.object(proof.manual_photo, "_save_registry") as save_registry, \
             mock.patch.object(proof, "_claim_proof_upload"), \
             mock.patch.object(proof, "atomic_write_bytes"), \
             mock.patch.object(proof, "_append_reference") as append_reference, \
             mock.patch.object(proof, "_remove_proof_file"):
            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})
            save_registry.assert_called_once()
        self.assertTrue(result["accepted"], result)
        self.assertTrue(result["policy"]["official_result"])
        self.assertFalse(result["policy"]["raw_grade_calibration"])
        self.assertFalse(result["policy"]["later_live_lookup_required"])
        saved = registry["registrations"][0]
        self.assertTrue(saved["official_result"])
        self.assertTrue(saved["training_eligible"])
        self.assertFalse(saved["raw_grade_calibration_eligible"])
        self.assertEqual(saved["verification_state"], "manual_official_verified")
        self.assertEqual(saved["manual_official_proof_match_mode"], "official_page_company_cert_grade_ocr")
        append_reference.assert_called_once()

    def test_psa_page_cert_match_can_use_exact_slab_ocr_when_grade_not_in_viewport(self):
        registry = {"registrations": [row_template()]}
        evidence = {"company": "PSA", "grade": None, "certification_id": "160600294"}
        text = "PSA PSACARD.COM/CERT/160600294 #160600294 2026 ONE PIECE MONKEY D LUFFY"
        with self._patch_common(registry, evidence, text), \
             mock.patch.object(proof.manual_photo, "_save_registry"), \
             mock.patch.object(proof, "_claim_proof_upload"), \
             mock.patch.object(proof, "atomic_write_bytes"), \
             mock.patch.object(proof, "_append_reference"), \
             mock.patch.object(proof, "_remove_proof_file"):
            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})
        self.assertTrue(result["accepted"], result)
        self.assertTrue(result["proof"]["slab_grade_fallback"], result)
        self.assertEqual(result["proof"]["match_mode"], "official_page_company_cert_plus_exact_slab_ocr_grade")

    def test_missing_grade_without_exact_slab_ocr_does_not_quarantine(self):
        registry = {"registrations": [row_template(ocr_company=None, ocr_grade=None, ocr_certification_id=None, image_path="")]}
        evidence = {"company": "PSA", "grade": None, "certification_id": "160600294"}
        text = "PSA PSACARD.COM/CERT/160600294 #160600294"
        with self._patch_common(registry, evidence, text), \
             mock.patch.object(proof.manual_photo, "_save_registry"), \
             mock.patch.object(proof, "_claim_proof_upload"), \
             mock.patch.object(proof, "atomic_write_bytes"), \
             mock.patch.object(proof, "_append_reference") as append_reference, \
             mock.patch.object(proof, "_remove_proof_file"):
            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})
        self.assertFalse(result["accepted"], result)
        saved = registry["registrations"][0]
        self.assertEqual(saved["status"], "pending_official_verification")
        self.assertEqual(saved["verification_state"], "manual_official_proof_needs_review")
        self.assertNotIn("official_proof_grade_mismatch", saved["quarantine_reasons"])
        append_reference.assert_not_called()

    def test_card_number_or_cost_does_not_create_false_grade_conflict(self):
        registry = {"registrations": [row_template()]}
        evidence = {"company": "PSA", "grade": 4.0, "certification_id": "160600294"}
        text = "PSA PSACARD.COM/CERT/160600294 #160600294 #055 4 ONE PIECE"
        with self._patch_common(registry, evidence, text), \
             mock.patch.object(proof.manual_photo, "_save_registry"), \
             mock.patch.object(proof, "_claim_proof_upload"), \
             mock.patch.object(proof, "atomic_write_bytes"), \
             mock.patch.object(proof, "_append_reference"), \
             mock.patch.object(proof, "_remove_proof_file"):
            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})
        self.assertTrue(result["accepted"], result)
        self.assertFalse(result["proof"]["conflicts"], result)
        self.assertTrue(result["proof"]["slab_grade_fallback"], result)

    def test_conflicting_new_proof_does_not_downgrade_existing_valid_reference(self):
        existing = row_template(
            status="manual_official_reference",
            verification_state="manual_official_proof_matched",
            manual_official_proof_registered=True,
            manual_official_proof_sha256="oldhash",
            manual_official_proof_path="GRADE_TRAINING_INBOX/manual_official_proof/old.jpg",
        )
        registry = {"registrations": [existing]}
        evidence = {"company": "BGS", "grade": 9.5, "certification_id": "87654321"}
        with self._patch_common(registry, evidence, "BGS BECKETT 87654321 GRADE 9.5"), \
             mock.patch.object(proof.manual_photo, "_save_registry") as save_registry, \
             mock.patch.object(proof, "_claim_proof_upload"), \
             mock.patch.object(proof, "atomic_write_bytes"), \
             mock.patch.object(proof, "_append_reference") as append_reference, \
             mock.patch.object(proof, "_remove_proof_file") as remove_proof:
            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})
            save_registry.assert_not_called()
        self.assertFalse(result["accepted"], result)
        self.assertTrue(result["registration"]["manual_official_proof_registered"])
        self.assertEqual(existing["verification_state"], "manual_official_proof_matched")
        append_reference.assert_not_called()
        remove_proof.assert_called_once()

    def test_rejected_proof_bytes_deleted_but_card_not_quarantined_by_proof_alone(self):
        registry = {"registrations": [row_template(ocr_company=None, ocr_grade=None, ocr_certification_id=None, image_path="")]}
        evidence = {"company": "BGS", "grade": 9.5, "certification_id": "87654321"}
        with self._patch_common(registry, evidence, "BGS BECKETT 87654321 GRADE 9.5"), \
             mock.patch.object(proof.manual_photo, "_save_registry") as save_registry, \
             mock.patch.object(proof, "_claim_proof_upload"), \
             mock.patch.object(proof, "atomic_write_bytes"), \
             mock.patch.object(proof, "_append_reference") as append_reference, \
             mock.patch.object(proof, "_remove_proof_file") as remove_proof:
            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})
            save_registry.assert_called_once()
        self.assertFalse(result["accepted"], result)
        saved = registry["registrations"][0]
        self.assertIsNone(saved["manual_official_proof_path"])
        self.assertFalse(saved["manual_official_proof_registered"])
        self.assertEqual(saved["status"], "pending_official_verification")
        self.assertEqual(saved["verification_state"], "manual_official_proof_conflict_needs_review")
        append_reference.assert_not_called()
        remove_proof.assert_called_once()

    def test_public_policy_exposes_hardening_contract(self):
        registry = {"registrations": []}
        with mock.patch.object(proof.manual_photo, "_registry", return_value=copy.deepcopy(registry)):
            status = proof.public_status()
        policy = status["policy"]
        self.assertTrue(policy["manual_screenshot_sets_official_result"])
        self.assertTrue(policy["manual_screenshot_requires_company_certificate_and_grade_match"])
        self.assertFalse(policy["manual_screenshot_alone_without_identity_match_sets_official_result"])
        self.assertFalse(policy["later_live_official_lookup_can_promote"])
        self.assertFalse(policy["automatic_live_lookup_used"])
        self.assertTrue(policy["verification_is_manual_only"])
        self.assertFalse(policy["manual_screenshot_trains_raw_grade_calibration"])
        self.assertFalse(policy["rejected_screenshot_bytes_retained"])
        self.assertTrue(policy["valid_proof_cannot_be_downgraded_by_later_bad_upload"])
        self.assertTrue(policy["proof_upload_rate_limited"])
        self.assertTrue(policy["manual_screenshot_missing_ocr_does_not_quarantine_card"])
        self.assertTrue(policy["manual_screenshot_grade_may_use_exact_slab_ocr_fallback"])


if __name__ == "__main__":
    unittest.main()
