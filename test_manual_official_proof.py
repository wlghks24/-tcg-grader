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
        "game": "pokemon",
        "company": "PSA",
        "claimed_grade": 10.0,
        "certification_id": "12345678",
        "official_result": False,
        "status": "pending_official_verification",
        "verification_state": "deferred_by_cooldown",
        "quarantine_reasons": ["official_lookup_not_confirmed"],
        "manual_official_proof_registered": False,
    }
    row.update(updates)
    return row


class ManualOfficialProofTests(unittest.TestCase):
    def _patch_common(self, registry, evidence):
        return mock.patch.multiple(
            proof.manual_photo,
            _registry=mock.Mock(return_value=registry),
            _decode_image=mock.Mock(return_value=(b"x" * 2048, ".jpg", 900, 1400)),
            _ocr_image=mock.Mock(return_value=("OCR", None, {}, evidence)),
        )

    def test_exact_match_is_reference_only_never_official_or_raw(self):
        registry = {"registrations": [row_template()]}
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "12345678"}
        with self._patch_common(registry, evidence), \
             mock.patch.object(proof.manual_photo, "_save_registry") as save_registry, \
             mock.patch.object(proof, "_claim_proof_upload"), \
             mock.patch.object(proof, "atomic_write_bytes"), \
             mock.patch.object(proof, "_append_reference") as append_reference, \
             mock.patch.object(proof, "_remove_proof_file"):
            result = proof.submit({"registration_id": REGISTRATION_ID, "proof_image_data_url": "ignored"})
            save_registry.assert_called_once()
        self.assertTrue(result["accepted"], result)
        self.assertFalse(result["policy"]["official_result"])
        self.assertFalse(result["policy"]["raw_grade_calibration"])
        saved = registry["registrations"][0]
        self.assertFalse(saved["official_result"])
        self.assertFalse(saved["training_eligible"])
        self.assertFalse(saved["raw_grade_calibration_eligible"])
        self.assertEqual(saved["verification_state"], "manual_official_proof_matched")
        append_reference.assert_called_once()

    def test_conflicting_new_proof_does_not_downgrade_existing_valid_reference(self):
        existing = row_template(
            status="manual_official_reference",
            verification_state="manual_official_proof_matched",
            manual_official_proof_registered=True,
            manual_official_proof_sha256="oldhash",
            manual_official_proof_path="GRADE_TRAINING_INBOX/manual_official_proof/old.jpg",
        )
        registry = {"registrations": [existing]}
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "87654321"}
        with self._patch_common(registry, evidence), \
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

    def test_rejected_proof_bytes_are_deleted_and_not_persisted_as_path(self):
        registry = {"registrations": [row_template()]}
        evidence = {"company": "BGS", "grade": 9.5, "certification_id": "87654321"}
        with self._patch_common(registry, evidence), \
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
        self.assertEqual(saved["verification_state"], "manual_official_proof_conflict")
        append_reference.assert_not_called()
        remove_proof.assert_called_once()

    def test_public_policy_exposes_hardening_contract(self):
        registry = {"registrations": []}
        with mock.patch.object(proof.manual_photo, "_registry", return_value=copy.deepcopy(registry)):
            status = proof.public_status()
        policy = status["policy"]
        self.assertFalse(policy["manual_screenshot_sets_official_result"])
        self.assertFalse(policy["manual_screenshot_trains_raw_grade_calibration"])
        self.assertFalse(policy["rejected_screenshot_bytes_retained"])
        self.assertTrue(policy["valid_proof_cannot_be_downgraded_by_later_bad_upload"])
        self.assertTrue(policy["proof_upload_rate_limited"])


if __name__ == "__main__":
    unittest.main()
