#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import manual_graded_photo_registration as manual


def png_data_url(width=800, height=1100, marker=b"a"):
    data = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    data += marker * max(0, 1100 - len(data))
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


class ManualGradedPhotoRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            mock.patch.object(manual, "ROOT", root),
            mock.patch.object(manual, "REGISTRY_PATH", root / "manual.json"),
            mock.patch.object(manual, "INBOX_ROOT", root / "inbox"),
            mock.patch.object(manual, "VERIFIED_CERTIFICATIONS", root / "verified.json"),
            mock.patch.object(manual, "VERIFIED_SLAB_REFERENCES", root / "references.json"),
        ]
        for patcher in self.patches:
            patcher.start()
        manual.PROCESSING_IDS.clear()

    def tearDown(self):
        manual.PROCESSING_IDS.clear()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def payload(self, marker=b"a"):
        return {
            "company": "PSA", "game": "pokemon", "grade": 10,
            "certification_id": "12345678", "card_name": "Test Card",
            "image_data_url": png_data_url(marker=marker), "filename": "user.png",
        }

    def test_registration_is_quarantined_and_server_generates_path(self):
        result = manual.register(self.payload())
        row = result["registration"]
        self.assertFalse(row["official_result"])
        self.assertEqual(row["learning_eligibility"], "quarantine_only_until_official_match")
        self.assertFalse(row["training_eligible"])
        stored = json.loads(manual.REGISTRY_PATH.read_text(encoding="utf-8"))["registrations"][0]
        self.assertNotIn("user.png", stored["image_path"])
        self.assertTrue((manual.ROOT / stored["image_path"]).exists())

    def test_exact_duplicate_is_idempotent(self):
        first = manual.register(self.payload())
        second = manual.register(self.payload())
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["registration"]["registration_id"], second["registration"]["registration_id"])
        self.assertEqual(manual.public_registry()["summary"]["total"], 1)

    def test_same_photo_with_different_claim_is_rejected(self):
        manual.register(self.payload())
        conflict = self.payload(); conflict["company"] = "BGS"
        with self.assertRaises(ValueError):
            manual.register(conflict)

    def test_bad_magic_and_invalid_grade_are_rejected(self):
        bad = self.payload(); bad["image_data_url"] = "data:image/png;base64," + base64.b64encode(b"x" * 1100).decode()
        with self.assertRaises(ValueError):
            manual.register(bad)

    def test_excessive_decompressed_pixels_are_rejected(self):
        bad = self.payload()
        bad["image_data_url"] = png_data_url(width=7000, height=6000)
        with self.assertRaisesRegex(ValueError, "3600만"):
            manual.register(bad)
        bad = self.payload(); bad["grade"] = 9.7
        with self.assertRaises(ValueError):
            manual.register(bad)

    def test_verified_official_match_publishes_reference_only(self):
        row = manual.register(self.payload())["registration"]
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA 10 CERT 12345678", None, {"pass_count": 1}, {"company": "PSA", "grade": 10.0, "certification_id": "12345678"})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "claim", return_value=(True, {"guard_reason": "allowed"})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "record_result", return_value={"blocked": False}), \
             mock.patch.object(manual, "verify_cert", return_value={"verified": True, "grade": 10.0, "official_url": "https://www.psacard.com/cert/12345678/psa", "http_status": 200}):
            result = manual.process_registration(row["registration_id"])
        verified = result["registration"]
        self.assertTrue(verified["official_result"])
        self.assertEqual(verified["learning_eligibility"], "reference_learning_only")
        self.assertFalse(verified["training_eligible"])
        references = json.loads(manual.VERIFIED_SLAB_REFERENCES.read_text(encoding="utf-8"))
        self.assertEqual(references["training_rows_written"], 0)
        self.assertEqual(references["certifications"][0]["source_sha256"], verified["image_sha256"])

    def test_cooldown_defers_without_official_network_call(self):
        row = manual.register(self.payload())["registration"]
        with mock.patch.object(manual, "_ocr_image", return_value=("", "tesseract_not_installed", {}, {})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "claim", return_value=(False, {"retry_after_seconds": 300})), \
             mock.patch.object(manual, "verify_cert") as verifier:
            result = manual.process_registration(row["registration_id"])
        verifier.assert_not_called()
        self.assertTrue(result["deferred"])
        self.assertEqual(result["registration"]["verification_state"], "deferred_by_cooldown")
        self.assertFalse(result["registration"]["training_eligible"])

    def test_retry_reuses_complete_ocr_identity(self):
        row = manual.register(self.payload())["registration"]
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "12345678"}
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA 10 CERT 12345678", None, {"pass_count": 1}, evidence)) as ocr, \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "claim", side_effect=[(False, {"retry_after_seconds": 60}), (True, {})]), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "record_result", return_value={"blocked": False}), \
             mock.patch.object(manual, "verify_cert", return_value={"verified": True, "grade": 10.0, "official_url": "https://www.psacard.com/cert/12345678/psa"}):
            first = manual.process_registration(row["registration_id"])
            second = manual.process_registration(row["registration_id"])
        self.assertTrue(first["deferred"])
        self.assertTrue(second["registration"]["official_result"])
        self.assertTrue(second["registration"]["ocr_cache_hit"])
        ocr.assert_called_once()

    def test_provider_block_after_lookup_is_deferred(self):
        row = manual.register(self.payload())["registration"]
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "12345678"}
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA 10 CERT 12345678", None, {}, evidence)), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "claim", return_value=(True, {})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "record_result", return_value={"blocked": True, "cooldown_seconds": 120}), \
             mock.patch.object(manual, "verify_cert", return_value={"verified": False, "blocked_or_challenged": True, "http_status": 429}):
            result = manual.process_registration(row["registration_id"])
        self.assertTrue(result["deferred"])
        self.assertEqual(result["registration"]["verification_state"], "deferred_by_cooldown")
        self.assertEqual(result["registration"]["retry_after_seconds"], 120)

    def test_duplicate_processing_request_is_coalesced(self):
        row = manual.register(self.payload())["registration"]
        manual.PROCESSING_IDS.add(row["registration_id"])
        with mock.patch.object(manual, "_ocr_image") as ocr:
            result = manual.process_registration(row["registration_id"])
        self.assertTrue(result["already_processing"])
        ocr.assert_not_called()

    def test_ocr_conflict_quarantines_even_when_lookup_claims_verified(self):
        row = manual.register(self.payload())["registration"]
        with mock.patch.object(manual, "_ocr_image", return_value=("BGS 9 CERT 87654321", None, {}, {"company": "BGS", "grade": 9.0, "certification_id": "87654321"})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "claim", return_value=(True, {})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "record_result", return_value={"blocked": False}), \
             mock.patch.object(manual, "verify_cert", return_value={"verified": True, "grade": 10.0, "official_url": "https://www.psacard.com/cert/12345678/psa"}):
            result = manual.process_registration(row["registration_id"])
        self.assertFalse(result["registration"]["official_result"])
        self.assertEqual(result["registration"]["status"], "quarantine")

    def test_official_lookup_without_ocr_identity_never_publishes_photo(self):
        row = manual.register(self.payload())["registration"]
        with mock.patch.object(manual, "_ocr_image", return_value=("", "tesseract_not_installed", {}, {})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "claim", return_value=(True, {})), \
             mock.patch.object(manual.OFFICIAL_LOOKUP_GUARD, "record_result", return_value={"blocked": False}), \
             mock.patch.object(manual, "verify_cert", return_value={"verified": True, "grade": 10.0, "official_url": "https://www.psacard.com/cert/12345678/psa"}):
            result = manual.process_registration(row["registration_id"])
        self.assertFalse(result["registration"]["official_result"])
        self.assertFalse(manual.VERIFIED_SLAB_REFERENCES.exists())


if __name__ == "__main__":
    unittest.main()
