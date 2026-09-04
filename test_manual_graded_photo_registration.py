#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import importlib
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


def quadrant_preview():
    row = {
        "scratchRisk": 8, "surfaceRisk": 12, "edgeRisk": 5, "cornerRisk": 4,
        "whiteningRisk": 5, "combinedRisk": 12, "confidence": 88,
        "confirmedSegments": 1, "obliqueStatus": "confirmed",
    }
    side = {"quadrants": {zone: dict(row) for zone in ("tl", "tr", "bl", "br")}}
    return {
        "version": 1, "engine": "v159-eight-zone-oblique-crosscheck", "zone_count": 8,
        "oblique_crosscheck_complete": True, "authoritative_for_training": False,
        "front": side, "back": side,
    }


class ManualGradedPhotoRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global manual
        # Runtime-policy suites deliberately patch this shared module for the
        # process lifetime. Exercise the base contract regardless of discovery order.
        manual = importlib.reload(manual)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            mock.patch.object(manual, "ROOT", root),
            mock.patch.object(manual, "REGISTRY_PATH", root / "manual.json"),
            mock.patch.object(manual, "INBOX_ROOT", root / "inbox"),
            mock.patch.object(manual, "VERIFIED_CERTIFICATIONS", root / "verified.json"),
            mock.patch.object(manual, "VERIFIED_SLAB_REFERENCES", root / "references.json"),
            mock.patch.object(manual, "_record_collection_gap"),
        ]
        for patcher in self.patches:
            patcher.start()
        manual.PROCESSING_IDS.clear()
        manual._cached_registry_payload.cache_clear()

    def tearDown(self):
        manual.PROCESSING_IDS.clear()
        manual._cached_registry_payload.cache_clear()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def payload(self, marker=b"a"):
        return {
            "company": "PSA", "game": "pokemon", "grade": 10,
            "certification_id": "12345678", "card_name": "Test Card",
            "image_data_url": png_data_url(marker=marker), "filename": "user.png",
        }

    def test_dashboard_keeps_front_back_registration_and_renders_eight_zone_checks(self):
        source = Path(__file__).with_name("graded_photo_dashboard.js").read_text(encoding="utf-8")
        for token in (
            "gpdManualPhoto", "gpdManualBackPhoto", "gpdManualFrontOblique", "gpdManualBackOblique",
            "총 8구역 정밀검사", "스크래치", "표면", "엣지", "코너", "백화",
            "oblique_crosscheck_complete", "authoritative_for_training:false",
        ):
            self.assertIn(token, source)

    def test_registration_is_quarantined_and_server_generates_path(self):
        result = manual.register(self.payload())
        row = result["registration"]
        self.assertFalse(row["official_result"])
        self.assertEqual(row["learning_eligibility"], "quarantine_only_until_official_match")
        self.assertFalse(row["training_eligible"])
        stored = json.loads(manual.REGISTRY_PATH.read_text(encoding="utf-8"))["registrations"][0]
        self.assertNotIn("user.png", stored["image_path"])
        self.assertTrue((manual.ROOT / stored["image_path"]).exists())

    def test_quick_registration_requires_only_game_and_photo(self):
        result = manual.register({
            "game": "onepiece", "image_data_url": png_data_url(marker=b"q"),
            "filename": "quick.png",
        })
        row = result["registration"]
        self.assertEqual(row["entry_mode"], "ocr_first")
        self.assertFalse(row["manual_identity_complete"])
        self.assertEqual(set(row["missing_identity_fields"]), {"company", "grade", "certification_id"})
        self.assertIsNone(row["official_reference_url"])

    def test_front_back_pair_and_oblique_evidence_are_stored_as_eight_zones(self):
        payload = self.payload()
        payload.update({
            "back_image_data_url": png_data_url(marker=b"b"),
            "front_oblique_image_data_url": png_data_url(marker=b"c"),
            "back_oblique_image_data_url": png_data_url(marker=b"d"),
            "client_quadrant_preview": quadrant_preview(),
        })
        row = manual.register(payload)["registration"]
        self.assertTrue(row["front_back_pair_complete"])
        self.assertTrue(row["oblique_crosscheck_complete"])
        self.assertEqual(row["quadrant_zone_count"], 8)
        self.assertEqual(row["quadrant_inspection_state"], "crosscheck_captured")
        self.assertFalse(row["client_preview_training_eligible"])
        stored = json.loads(manual.REGISTRY_PATH.read_text(encoding="utf-8"))["registrations"][0]
        for key in ("image_path", "back_image_path", "front_oblique_image_path", "back_oblique_image_path"):
            self.assertTrue((manual.ROOT / stored[key]).exists())
        self.assertFalse(stored["client_quadrant_preview"]["authoritative_for_training"])

    def test_oblique_crosscheck_requires_both_sides_and_a_different_angle(self):
        payload = self.payload()
        payload["back_image_data_url"] = png_data_url(marker=b"b")
        payload["front_oblique_image_data_url"] = png_data_url(marker=b"c")
        with self.assertRaisesRegex(ValueError, "앞면·뒷면"):
            manual.register(payload)
        payload["back_oblique_image_data_url"] = payload["back_image_data_url"]
        with self.assertRaisesRegex(ValueError, "다른 각도"):
            manual.register(payload)


    def test_quick_registration_ocr_autofills_then_requires_manual_official_proof(self):
        row = manual.register({
            "game": "naruto", "image_data_url": png_data_url(marker=b"n")
        })["registration"]
        evidence = {"company": "CGC", "grade": 9.5, "certification_id": "CGC123456"}
        with mock.patch.object(manual, "_ocr_image", return_value=("CGC 9.5 CGC123456", None, {}, evidence)) as ocr:
            result = manual.process_registration(row["registration_id"])
        queued = result["registration"]
        self.assertTrue(result["deferred"])
        self.assertTrue(result["manual_official_proof_required"])
        self.assertFalse(queued["official_result"])
        self.assertEqual((queued["company"], queued["claimed_grade"], queued["certification_id"]),
                         ("CGC", 9.5, "CGC123456"))
        self.assertEqual(queued["verification_state"], "manual_official_verification_required")
        self.assertFalse(queued["automatic_official_lookup_used"])
        self.assertFalse(hasattr(manual, "verify_cert"))
        self.assertFalse(hasattr(manual, "OFFICIAL_LOOKUP_GUARD"))
        ocr.assert_called_once()

    def test_incomplete_ocr_requests_manual_input_without_official_lookup(self):
        row = manual.register({
            "game": "pokemon", "image_data_url": png_data_url(marker=b"m")
        })["registration"]
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA label", None, {}, {"company": "PSA"})) as ocr:
            result = manual.process_registration(row["registration_id"])
        self.assertTrue(result["manual_input_required"])
        self.assertEqual(result["registration"]["verification_state"], "manual_input_required")
        self.assertEqual(set(result["registration"]["missing_identity_fields"]), {"grade", "certification_id"})
        self.assertFalse(result["registration"]["official_result"])
        self.assertFalse(hasattr(manual, "verify_cert"))
        ocr.assert_called_once()
    def test_same_quick_photo_can_be_completed_with_manual_identity(self):
        quick = {"game": "pokemon", "image_data_url": png_data_url(marker=b"r")}
        first = manual.register(quick)
        completed = dict(quick, company="BGS", grade=9, certification_id="BGS123456")
        second = manual.register(completed)
        self.assertFalse(second["duplicate"])
        self.assertTrue(second["resumed"])
        self.assertEqual(second["registration"]["registration_id"], first["registration"]["registration_id"])
        self.assertTrue(second["registration"]["manual_identity_complete"])

    def test_exact_duplicate_is_idempotent(self):
        first = manual.register(self.payload())
        second = manual.register(self.payload())
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["registration"]["registration_id"], second["registration"]["registration_id"])
        self.assertEqual(manual.public_registry()["summary"]["total"], 1)

    def test_registry_cache_reuses_parse_but_returns_isolated_rows(self):
        manual.register(self.payload())
        manual._cached_registry_payload.cache_clear()
        original=manual._load
        with mock.patch.object(manual,"_load",wraps=original) as loader:
            first=manual._registry()
            second=manual._registry()
            first["registrations"][0]["company"]="BGS"
            third=manual._registry()
        self.assertEqual(loader.call_count,1)
        self.assertEqual(second["registrations"][0]["company"],"PSA")
        self.assertEqual(third["registrations"][0]["company"],"PSA")

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


    def test_complete_identity_stays_pending_until_manual_official_proof(self):
        payload = self.payload()
        payload["back_image_data_url"] = png_data_url(marker=b"z")
        row = manual.register(payload)["registration"]
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "12345678"}
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA 10 CERT 12345678", None, {"pass_count": 1}, evidence)):
            result = manual.process_registration(row["registration_id"])
        queued = result["registration"]
        self.assertTrue(result["deferred"])
        self.assertTrue(result["manual_official_proof_required"])
        self.assertFalse(queued["official_result"])
        self.assertEqual(queued["learning_eligibility"], "manual_official_proof_required")
        self.assertFalse(queued["training_eligible"])
        self.assertEqual(queued["verification_state"], "manual_official_verification_required")
        self.assertFalse(manual.VERIFIED_SLAB_REFERENCES.exists())

    def test_manual_only_flow_has_no_network_cooldown_dependency(self):
        row = manual.register(self.payload())["registration"]
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "12345678"}
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA 10 CERT 12345678", None, {}, evidence)):
            result = manual.process_registration(row["registration_id"])
        self.assertTrue(result["deferred"])
        self.assertTrue(result["manual_official_proof_required"])
        self.assertIsNone(result["registration"].get("retry_after_seconds"))
        self.assertFalse(result["registration"]["official_result"])
        self.assertNotIn("official_provider_blocked", result["registration"].get("quarantine_reasons", []))

    def test_retry_reuses_complete_ocr_identity_without_network_lookup(self):
        row = manual.register(self.payload())["registration"]
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "12345678"}
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA 10 CERT 12345678", None, {"pass_count": 1}, evidence)) as ocr:
            first = manual.process_registration(row["registration_id"])
            second = manual.process_registration(row["registration_id"])
        self.assertTrue(first["manual_official_proof_required"])
        self.assertTrue(second["manual_official_proof_required"])
        self.assertFalse(second["registration"]["official_result"])
        self.assertTrue(second["registration"]["ocr_cache_hit"])
        ocr.assert_called_once()

    def test_manual_only_flow_never_creates_provider_block_state(self):
        row = manual.register(self.payload())["registration"]
        evidence = {"company": "PSA", "grade": 10.0, "certification_id": "12345678"}
        with mock.patch.object(manual, "_ocr_image", return_value=("PSA 10 CERT 12345678", None, {}, evidence)):
            result = manual.process_registration(row["registration_id"])
        queued = result["registration"]
        self.assertTrue(result["manual_official_proof_required"])
        self.assertFalse(queued["official_result"])
        self.assertIsNone(queued.get("retry_after_seconds"))
        self.assertNotIn("official_provider_blocked", queued.get("quarantine_reasons", []))
        self.assertFalse(queued["automatic_official_lookup_used"])
    def test_duplicate_processing_request_is_coalesced(self):
        row = manual.register(self.payload())["registration"]
        manual.PROCESSING_IDS.add(row["registration_id"])
        with mock.patch.object(manual, "_ocr_image") as ocr:
            result = manual.process_registration(row["registration_id"])
        self.assertTrue(result["already_processing"])
        ocr.assert_not_called()


    def test_ocr_conflict_is_preserved_for_manual_review(self):
        row = manual.register(self.payload())["registration"]
        evidence = {"company": "BGS", "grade": 9.0, "certification_id": "87654321"}
        with mock.patch.object(manual, "_ocr_image", return_value=("BGS 9 CERT 87654321", None, {}, evidence)):
            result = manual.process_registration(row["registration_id"])
        queued = result["registration"]
        self.assertFalse(queued["official_result"])
        self.assertTrue(result["manual_official_proof_required"])
        reasons=set(queued.get("quarantine_reasons", []))
        self.assertIn("ocr_company_conflict", reasons)
        self.assertIn("ocr_certification_conflict", reasons)
        self.assertIn("ocr_grade_conflict", reasons)
        self.assertIn("manual_official_proof_required", reasons)

    def test_manual_identity_without_ocr_identity_never_publishes_photo(self):
        row = manual.register(self.payload())["registration"]
        with mock.patch.object(manual, "_ocr_image", return_value=("", "tesseract_not_installed", {}, {})):
            result = manual.process_registration(row["registration_id"])
        queued = result["registration"]
        self.assertTrue(result["manual_official_proof_required"])
        self.assertFalse(queued["official_result"])
        self.assertEqual(queued["verification_state"], "manual_official_verification_required")
        self.assertFalse(manual.VERIFIED_SLAB_REFERENCES.exists())

if __name__ == "__main__":
    unittest.main()
