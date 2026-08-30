#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

import safe_photo_cleanup as cleanup


class SafePhotoCleanupV132Tests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            name: getattr(cleanup, name)
            for name in (
                "ROOT", "REPORT_PATH", "MANUAL_REGISTRY", "VERIFIED_CERTS",
                "VERIFIED_REFS", "LIBRARY_CANDIDATES"
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
        self.photos = root / "GRADE_TRAINING_INBOX" / "manual" / "202608"
        self.photos.mkdir(parents=True)

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(cleanup, name, value)
        self.temp.cleanup()

    def _write(self, name, data, age_days=0, folder=None):
        base = folder or self.photos
        base.mkdir(parents=True, exist_ok=True)
        path = base / name
        path.write_bytes(data)
        if age_days:
            stamp = time.time() - age_days * 86400
            os.utime(path, (stamp, stamp))
        return path

    def _sha(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _registry(self, rows):
        cleanup.MANUAL_REGISTRY.write_text(
            json.dumps({"registrations": rows}), encoding="utf-8"
        )

    def test_verified_and_pending_survive_apply(self):
        verified = self._write("verified.jpg", b"v" * 2048, 30)
        pending = self._write("pending.jpg", b"p" * 2048, 30)
        self._registry([
            {
                "image_path": verified.relative_to(cleanup.ROOT).as_posix(),
                "image_sha256": self._sha(verified),
                "official_result": True,
                "status": "verified_reference",
            },
            {
                "image_path": pending.relative_to(cleanup.ROOT).as_posix(),
                "image_sha256": self._sha(pending),
                "official_result": False,
                "status": "pending_official_verification",
                "verification_state": "queued",
            },
        ])
        result = cleanup.run(apply=True)
        self.assertTrue(verified.exists())
        self.assertTrue(pending.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_pending_duplicate_is_never_deleted(self):
        first = self._write("a.jpg", b"same" * 512)
        pending = self._write("z_pending.jpg", b"same" * 512, 30)
        self._registry([{
            "image_path": pending.relative_to(cleanup.ROOT).as_posix(),
            "image_sha256": self._sha(pending),
            "official_result": False,
            "status": "pending_official_verification",
            "verification_state": "queued",
        }])
        result = cleanup.run(apply=True)
        self.assertTrue(first.exists())
        self.assertTrue(pending.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_rejected_duplicate_respects_grace_period(self):
        first = self._write("a.jpg", b"same" * 512)
        rejected = self._write("z_rejected.jpg", b"same" * 512, 5)
        self._registry([{
            "image_path": rejected.relative_to(cleanup.ROOT).as_posix(),
            "image_sha256": self._sha(rejected),
            "status": "quarantine",
            "verification_state": "completed_unverified",
            "quarantine_reasons": ["grade_mismatch"],
        }])
        result = cleanup.run(apply=True, grace_days=14)
        self.assertTrue(first.exists())
        self.assertTrue(rejected.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_old_explicit_rejection_can_be_deleted(self):
        rejected = self._write("rejected.jpg", b"r" * 2048, 20)
        self._registry([{
            "image_path": rejected.relative_to(cleanup.ROOT).as_posix(),
            "image_sha256": self._sha(rejected),
            "status": "quarantine",
            "verification_state": "completed_unverified",
            "quarantine_reasons": ["grade_mismatch"],
        }])
        result = cleanup.run(apply=True, grace_days=14)
        self.assertFalse(rejected.exists())
        self.assertEqual(result["summary"]["deleted_images"], 1)

    def test_corrupt_existing_registry_fails_closed(self):
        cache = cleanup.ROOT / "graded_photo_cache"
        stale = self._write("stale.jpg", b"x" * 2048, 30, cache)
        cleanup.MANUAL_REGISTRY.write_text("{broken", encoding="utf-8")
        result = cleanup.run(apply=True, cache_days=7)
        self.assertTrue(stale.exists())
        self.assertEqual(result["mode"], "apply_guarded_no_delete")
        self.assertFalse(result["registry_guard"]["destructive_allowed"])
        self.assertEqual(result["summary"]["deleted_images"], 0)
        self.assertGreaterEqual(result["summary"]["guarded_keep_images"], 1)

    def test_compound_cache_folder_is_detected(self):
        self._registry([])
        cache = cleanup.ROOT / "graded_photo_cache"
        stale = self._write("stale.jpg", b"x" * 2048, 30, cache)
        result = cleanup.run(apply=True, cache_days=7)
        self.assertFalse(stale.exists())
        self.assertEqual(result["summary"]["deleted_images"], 1)

    def test_compound_protected_folder_is_protected(self):
        self._registry([])
        folder = cleanup.ROOT / "grading_photos" / "official_validation_set"
        protected = self._write("keep.jpg", b"k" * 2048, 30, folder)
        duplicate = self._write("keep2.jpg", b"k" * 2048, 30, folder)
        result = cleanup.run(apply=True)
        self.assertTrue(protected.exists())
        self.assertTrue(duplicate.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_dry_run_never_deletes(self):
        self._registry([])
        a = self._write("a.jpg", b"x" * 2048)
        b = self._write("b.jpg", b"x" * 2048)
        result = cleanup.run(apply=False)
        self.assertTrue(a.exists())
        self.assertTrue(b.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)
        self.assertEqual(result["summary"]["delete_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
