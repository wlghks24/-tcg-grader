#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import manual_registration_delete_v151 as deletion

REGISTRATION_ID = "manual-20260831123456-abcdef123456"


class ManualRegistrationDeleteV151Tests(unittest.TestCase):
    def test_unverified_registration_is_removed_and_files_cleaned(self):
        row = {
            "registration_id": REGISTRATION_ID,
            "official_result": False,
            "image_path": "GRADE_TRAINING_INBOX/manual/front.jpg",
            "back_image_path": "GRADE_TRAINING_INBOX/manual/back.jpg",
            "manual_official_proof_path": "GRADE_TRAINING_INBOX/manual_official_proof/proof.jpg",
        }
        registry = {"registrations": [row, {"registration_id": "manual-20260831123457-abcdef123457"}]}
        with mock.patch.object(deletion.manual_photo, "_registry", return_value=registry), \
             mock.patch.object(deletion.manual_photo, "_find_row", return_value=(0, row)), \
             mock.patch.object(deletion.manual_photo, "_save_registry") as save_registry, \
             mock.patch.object(deletion, "_safe_unlink", return_value=True) as unlink, \
             mock.patch.object(deletion, "_remove_reference_entries", return_value=1):
            result = deletion.delete_registration(REGISTRATION_ID)
        self.assertTrue(result["deleted"])
        self.assertEqual(result["files_deleted"], 3)
        self.assertEqual(result["references_deleted"], 1)
        self.assertEqual(len(registry["registrations"]), 1)
        self.assertNotEqual(registry["registrations"][0]["registration_id"], REGISTRATION_ID)
        save_registry.assert_called_once()
        self.assertEqual(unlink.call_count, 3)

    def test_live_official_verified_registration_cannot_be_deleted(self):
        row = {"registration_id": REGISTRATION_ID, "official_result": True}
        registry = {"registrations": [row]}
        with mock.patch.object(deletion.manual_photo, "_registry", return_value=registry), \
             mock.patch.object(deletion.manual_photo, "_find_row", return_value=(0, row)), \
             mock.patch.object(deletion.manual_photo, "_save_registry") as save_registry:
            with self.assertRaises(ValueError):
                deletion.delete_registration(REGISTRATION_ID)
        save_registry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
