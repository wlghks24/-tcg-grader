#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility smoke tests for the current v133 cleanup policy."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import safe_photo_cleanup as cleanup


class SafePhotoCleanupTests(unittest.TestCase):
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

    def test_manual_photo_is_never_auto_deleted(self):
        photo = self.manual / "manual.jpg"
        photo.write_bytes(b"m" * 2048)
        self._age(photo, 90)
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(photo.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_old_unreferenced_cache_can_be_deleted(self):
        photo = self.cache / "stale.jpg"
        photo.write_bytes(b"c" * 2048)
        self._age(photo, 30)
        result = cleanup.run(apply=True, cache_days=14)
        self.assertFalse(photo.exists())
        self.assertEqual(result["summary"]["deleted_images"], 1)

    def test_dry_run_never_deletes(self):
        photo = self.cache / "stale.jpg"
        photo.write_bytes(b"d" * 2048)
        self._age(photo, 30)
        result = cleanup.run(apply=False, cache_days=14)
        self.assertTrue(photo.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)
        self.assertEqual(result["summary"]["delete_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
