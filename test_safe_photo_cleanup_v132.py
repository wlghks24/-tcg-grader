#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility tests: v132 filename, v133 safety behavior."""
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import safe_photo_cleanup as cleanup


class SafePhotoCleanupV132CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            name: getattr(cleanup, name)
            for name in (
                "ROOT", "REPORT_PATH", "MANUAL_REGISTRY", "VERIFIED_CERTS",
                "VERIFIED_REFS", "LIBRARY_CANDIDATES", "GRADED_PHOTO_CANDIDATES",
                "EBAY_CANDIDATES", "CRITICAL_REGISTRIES",
            )
        }
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        cleanup.ROOT = root
        cleanup.REPORT_PATH = root / "photo_cleanup_report.json"
        cleanup.MANUAL_REGISTRY = root / "manual_graded_photo_registrations.json"
        cleanup.VERIFIED_CERTS = root / "verified_certifications.json"
        cleanup.VERIFIED_REFS = root / "library_verified_slab_references.json"
        cleanup.LIBRARY_CANDIDATES = root / "library_slab_candidates.json"
        cleanup.GRADED_PHOTO_CANDIDATES = root / "graded_photo_candidates.json"
        cleanup.EBAY_CANDIDATES = root / "ebay_grader_candidates.json"
        cleanup.CRITICAL_REGISTRIES = (
            (cleanup.VERIFIED_REFS, ("certifications", "records", "items")),
            (cleanup.LIBRARY_CANDIDATES, ("records", "certifications", "items")),
            (cleanup.VERIFIED_CERTS, ("certifications", "records", "items")),
            (cleanup.GRADED_PHOTO_CANDIDATES, ("records", "items", "certifications")),
            (cleanup.EBAY_CANDIDATES, ("items", "records", "certifications")),
        )
        self.manual = root / "GRADE_TRAINING_INBOX" / "manual" / "202608"
        self.cache = root / "graded_photo_cache"
        self.manual.mkdir(parents=True)
        self.cache.mkdir(parents=True)
        cleanup.MANUAL_REGISTRY.write_text(json.dumps({"registrations": []}), encoding="utf-8")

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(cleanup, name, value)
        self.temp.cleanup()

    @staticmethod
    def _age(path: Path, days: int) -> None:
        stamp = time.time() - days * 86400
        os.utime(path, (stamp, stamp))

    def test_old_rejected_manual_photo_is_preserved(self):
        photo = self.manual / "rejected.jpg"
        photo.write_bytes(b"r" * 2048)
        self._age(photo, 120)
        digest = hashlib.sha256(photo.read_bytes()).hexdigest()
        cleanup.MANUAL_REGISTRY.write_text(json.dumps({"registrations": [{
            "image_path": photo.relative_to(cleanup.ROOT).as_posix(),
            "image_sha256": digest,
            "status": "quarantine",
            "verification_state": "completed_unverified",
        }]}), encoding="utf-8")
        result = cleanup.run(apply=True, grace_days=1, cache_days=14)
        self.assertTrue(photo.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_candidate_hash_protects_cache(self):
        photo = self.cache / "candidate.jpg"
        photo.write_bytes(b"c" * 2048)
        self._age(photo, 30)
        digest = hashlib.sha256(photo.read_bytes()).hexdigest()
        cleanup.LIBRARY_CANDIDATES.write_text(json.dumps({"records": [{
            "sha256": digest,
            "status": "quarantine",
            "official_result": False,
        }]}), encoding="utf-8")
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(photo.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_stale_unreferenced_cache_can_be_deleted(self):
        photo = self.cache / "stale.jpg"
        photo.write_bytes(b"s" * 2048)
        self._age(photo, 30)
        result = cleanup.run(apply=True, cache_days=14)
        self.assertFalse(photo.exists())
        self.assertEqual(result["summary"]["deleted_images"], 1)

    def test_corrupt_registry_disables_deletion(self):
        photo = self.cache / "stale.jpg"
        photo.write_bytes(b"s" * 2048)
        self._age(photo, 30)
        cleanup.VERIFIED_REFS.write_text("{broken", encoding="utf-8")
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(photo.exists())
        self.assertFalse(result["registry_guard"]["destructive_allowed"])
        self.assertEqual(result["summary"]["deleted_images"], 0)


if __name__ == "__main__":
    unittest.main()
