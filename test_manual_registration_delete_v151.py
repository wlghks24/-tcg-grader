#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import manual_registration_delete_v151 as deletion

REGISTRATION_ID = "manual-20260831123456-abcdef123456"


class ManualRegistrationDeleteV151Tests(unittest.TestCase):
    def test_unverified_registration_is_removed_and_files_cleaned(self):
        row = {
            "registration_id": REGISTRATION_ID,
            "official_result": False,
            "image_path": f"GRADE_TRAINING_INBOX/manual/{REGISTRATION_ID}.jpg",
            "back_image_path": f"GRADE_TRAINING_INBOX/manual/{REGISTRATION_ID}_back.jpg",
            "manual_official_proof_path": f"GRADE_TRAINING_INBOX/manual_official_proof/{REGISTRATION_ID}-proof.jpg",
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

    def test_symlink_to_protected_photo_is_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            inbox.mkdir(parents=True)
            protected = inbox / "protected.jpg"
            protected.write_bytes(b"verified evidence")
            alias = inbox / f"{REGISTRATION_ID}.jpg"
            alias.symlink_to(protected)
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion, "PROOF_ROOT", root / "GRADE_TRAINING_INBOX" / "manual_official_proof"):
                self.assertFalse(deletion._safe_unlink(alias.relative_to(root).as_posix()))
            self.assertEqual(protected.read_bytes(), b"verified evidence")
            self.assertTrue(alias.is_symlink())

    def test_symlinked_parent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            real = inbox / "real"
            real.mkdir(parents=True)
            protected = real / f"{REGISTRATION_ID}.jpg"
            protected.write_bytes(b"protected")
            (inbox / "alias").symlink_to(real, target_is_directory=True)
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion, "PROOF_ROOT", root / "GRADE_TRAINING_INBOX" / "manual_official_proof"):
                self.assertFalse(deletion._safe_unlink(f"GRADE_TRAINING_INBOX/manual/alias/{REGISTRATION_ID}.jpg"))
            self.assertEqual(protected.read_bytes(), b"protected")

    def test_absolute_and_parent_traversal_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            inbox.mkdir(parents=True)
            protected = inbox / f"{REGISTRATION_ID}.jpg"
            protected.write_bytes(b"protected")
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion, "PROOF_ROOT", root / "GRADE_TRAINING_INBOX" / "manual_official_proof"):
                self.assertFalse(deletion._safe_unlink(str(protected)))
                self.assertFalse(deletion._safe_unlink(f"GRADE_TRAINING_INBOX/manual/../manual/{REGISTRATION_ID}.jpg"))
            self.assertEqual(protected.read_bytes(), b"protected")

    def test_owned_regular_file_deletes_but_shared_file_is_preserved(self):
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            self.skipTest("No-follow directory descriptors unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            inbox.mkdir(parents=True)
            owned = inbox / f"{REGISTRATION_ID}.jpg"
            shared = inbox / f"{REGISTRATION_ID}_back.jpg"
            owned.write_bytes(b"owned")
            shared.write_bytes(b"shared")
            owned_rel = owned.relative_to(root).as_posix()
            shared_rel = shared.relative_to(root).as_posix()
            row = {"registration_id": REGISTRATION_ID, "official_result": False,
                   "image_path": owned_rel, "back_image_path": shared_rel}
            other = {"registration_id": "verified-other", "official_result": True,
                     "image_path": shared_rel}
            registry = {"registrations": [row, other]}
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion, "PROOF_ROOT", root / "GRADE_TRAINING_INBOX" / "manual_official_proof"), \
                 mock.patch.object(deletion.manual_photo, "_registry", return_value=registry), \
                 mock.patch.object(deletion.manual_photo, "_find_row", return_value=(0, row)), \
                 mock.patch.object(deletion.manual_photo, "_save_registry") as saved, \
                 mock.patch.object(deletion, "_remove_reference_entries", return_value=0):
                result = deletion.delete_registration(REGISTRATION_ID)
            self.assertTrue(result["deleted"])
            self.assertEqual(result["files_deleted"], 1)
            self.assertFalse(owned.exists())
            self.assertEqual(shared.read_bytes(), b"shared")
            self.assertEqual(len(registry["registrations"]), 1)
            saved.assert_called_once()

    def test_registry_save_failure_preserves_photos(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            inbox.mkdir(parents=True)
            owned = inbox / f"{REGISTRATION_ID}.jpg"
            owned.write_bytes(b"owned")
            row = {"registration_id": REGISTRATION_ID, "official_result": False,
                   "image_path": owned.relative_to(root).as_posix()}
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion.manual_photo, "_registry", return_value={"registrations": [row]}), \
                 mock.patch.object(deletion.manual_photo, "_find_row", return_value=(0, row)), \
                 mock.patch.object(deletion.manual_photo, "_save_registry", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    deletion.delete_registration(REGISTRATION_ID)
            self.assertEqual(owned.read_bytes(), b"owned")

    def test_unowned_legacy_name_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            inbox.mkdir(parents=True)
            foreign = inbox / "unrelated.jpg"
            foreign.write_bytes(b"protected")
            row = {"registration_id": REGISTRATION_ID, "official_result": False,
                   "image_path": foreign.relative_to(root).as_posix()}
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion.manual_photo, "_registry", return_value={"registrations": [row]}), \
                 mock.patch.object(deletion.manual_photo, "_find_row", return_value=(0, row)), \
                 mock.patch.object(deletion.manual_photo, "_save_registry"), \
                 mock.patch.object(deletion, "_remove_reference_entries", return_value=0):
                result = deletion.delete_registration(REGISTRATION_ID)
            self.assertEqual(result["files_deleted"], 0)
            self.assertEqual(foreign.read_bytes(), b"protected")

    def test_verified_row_alias_to_owned_path_blocks_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            inbox.mkdir(parents=True)
            owned = inbox / f"{REGISTRATION_ID}.jpg"
            owned.write_bytes(b"protected by verified alias")
            alias = inbox / "verified-alias.jpg"
            alias.symlink_to(owned)
            row = {"registration_id": REGISTRATION_ID, "official_result": False,
                   "image_path": owned.relative_to(root).as_posix()}
            verified = {"registration_id": "verified-other", "official_result": True,
                        "image_path": alias.relative_to(root).as_posix()}
            registry = {"registrations": [row, verified]}
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion.manual_photo, "_registry", return_value=registry), \
                 mock.patch.object(deletion.manual_photo, "_find_row", return_value=(0, row)), \
                 mock.patch.object(deletion.manual_photo, "_save_registry"), \
                 mock.patch.object(deletion, "_remove_reference_entries", return_value=0):
                result = deletion.delete_registration(REGISTRATION_ID)
            self.assertEqual(result["files_deleted"], 0)
            self.assertEqual(owned.read_bytes(), b"protected by verified alias")

    def test_final_component_swap_does_not_unlink_target(self):
        if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
            self.skipTest("No-follow directory descriptors unavailable")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inbox = root / "GRADE_TRAINING_INBOX" / "manual"
            inbox.mkdir(parents=True)
            owned = inbox / f"{REGISTRATION_ID}.jpg"
            owned.write_bytes(b"old")
            protected = inbox / "protected.jpg"
            protected.write_bytes(b"verified evidence")
            real_stat = os.stat
            did_swap = [False]
            def swap_after_stat(path, *args, **kwargs):
                result = real_stat(path, *args, **kwargs)
                if path == owned.name and kwargs.get("dir_fd") is not None and not did_swap[0]:
                    did_swap[0] = True
                    owned.unlink()
                    owned.symlink_to(protected)
                return result
            with mock.patch.object(deletion, "ROOT", root), \
                 mock.patch.object(deletion.manual_photo, "INBOX_ROOT", inbox), \
                 mock.patch.object(deletion, "PROOF_ROOT", root / "GRADE_TRAINING_INBOX" / "manual_official_proof"), \
                 mock.patch.object(deletion.os, "stat", side_effect=swap_after_stat):
                deletion._safe_unlink(owned.relative_to(root).as_posix())
            self.assertTrue(did_swap[0])
            self.assertEqual(protected.read_bytes(), b"verified evidence")

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
