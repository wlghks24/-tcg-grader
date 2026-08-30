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


class SafePhotoCleanupV133Tests(unittest.TestCase):
    def setUp(self):
        self.originals = {
            name: getattr(cleanup, name)
            for name in (
                "ROOT", "REPORT_PATH", "MANUAL_REGISTRY", "VERIFIED_CERTS",
                "VERIFIED_REFS", "LIBRARY_CANDIDATES", "GRADED_PHOTO_CANDIDATES",
                "EBAY_CANDIDATES", "CRITICAL_REGISTRIES", "MAX_HASH_BYTES", "_sha256",
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
        self.manual.mkdir(parents=True)
        self.cache = root / "graded_photo_cache"
        self.cache.mkdir(parents=True)

    def tearDown(self):
        for name, value in self.originals.items():
            setattr(cleanup, name, value)
        self.temp.cleanup()

    def _write(self, name, data=b"x" * 2048, age_days=0, folder=None):
        base = folder or self.manual
        base.mkdir(parents=True, exist_ok=True)
        path = base / name
        path.write_bytes(data)
        if age_days:
            stamp = time.time() - age_days * 86400
            os.utime(path, (stamp, stamp))
        return path

    def _sha(self, path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _manual_registry(self, rows):
        cleanup.MANUAL_REGISTRY.write_text(
            json.dumps({"registrations": rows}), encoding="utf-8"
        )

    def test_manual_and_pending_photos_never_auto_delete(self):
        manual = self._write("manual.jpg", age_days=90)
        pending = self._write("pending.jpg", age_days=90)
        self._manual_registry([{
            "image_path": pending.relative_to(cleanup.ROOT).as_posix(),
            "image_sha256": self._sha(pending),
            "status": "pending_official_verification",
            "verification_state": "queued",
        }])
        result = cleanup.run(apply=True)
        self.assertTrue(manual.exists())
        self.assertTrue(pending.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_old_manual_rejected_photo_is_still_preserved(self):
        rejected = self._write("rejected.jpg", age_days=120)
        self._manual_registry([{
            "image_path": rejected.relative_to(cleanup.ROOT).as_posix(),
            "image_sha256": self._sha(rejected),
            "status": "quarantine",
            "verification_state": "completed_unverified",
            "quarantine_reasons": ["grade_mismatch"],
        }])
        result = cleanup.run(apply=True, grace_days=1)
        self.assertTrue(rejected.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_generic_grading_photo_duplicate_is_not_disposable(self):
        self._manual_registry([])
        folder = cleanup.ROOT / "grading_photos"
        a = self._write("a.jpg", b"d" * 2048, 90, folder)
        b = self._write("b.jpg", b"d" * 2048, 90, folder)
        result = cleanup.run(apply=True, cache_days=7)
        self.assertTrue(a.exists())
        self.assertTrue(b.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_stale_unreferenced_cache_can_be_deleted(self):
        self._manual_registry([])
        stale = self._write("stale.jpg", b"s" * 2048, 30, self.cache)
        result = cleanup.run(apply=True, cache_days=14)
        self.assertFalse(stale.exists())
        self.assertEqual(result["summary"]["deleted_images"], 1)

    def test_fresh_cache_is_never_deleted(self):
        self._manual_registry([])
        fresh = self._write("fresh.jpg", b"f" * 2048, 2, self.cache)
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(fresh.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_candidate_registry_hash_protects_stale_cache(self):
        self._manual_registry([])
        image = self._write("candidate.jpg", b"c" * 2048, 30, self.cache)
        cleanup.LIBRARY_CANDIDATES.write_text(json.dumps({
            "records": [{
                "source_name": "other-name.jpg",
                "sha256": self._sha(image),
                "official_result": False,
                "status": "quarantine",
            }]
        }), encoding="utf-8")
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(image.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_candidate_basename_protects_stale_cache(self):
        self._manual_registry([])
        image = self._write("1000239685.png", b"c" * 2048, 30, self.cache)
        cleanup.LIBRARY_CANDIDATES.write_text(json.dumps({
            "records": [{
                "source_name": "1000239685.png",
                "official_result": False,
                "status": "quarantine",
            }]
        }), encoding="utf-8")
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(image.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_corrupt_existing_registry_fails_closed(self):
        self._manual_registry([])
        stale = self._write("stale.jpg", b"s" * 2048, 30, self.cache)
        cleanup.VERIFIED_REFS.write_text("{broken", encoding="utf-8")
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(stale.exists())
        self.assertEqual(result["mode"], "apply_guarded_no_delete")
        self.assertFalse(result["registry_guard"]["destructive_allowed"])
        self.assertGreaterEqual(result["summary"]["guarded_keep_images"], 1)

    def test_invalid_registry_row_fails_closed(self):
        self._manual_registry([])
        stale = self._write("stale.jpg", b"s" * 2048, 30, self.cache)
        cleanup.GRADED_PHOTO_CANDIDATES.write_text(
            json.dumps({"records": ["not-an-object"]}), encoding="utf-8"
        )
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(stale.exists())
        self.assertFalse(result["registry_guard"]["destructive_allowed"])

    def test_hash_failure_keeps_old_cache(self):
        self._manual_registry([])
        old_limit = cleanup.MAX_HASH_BYTES
        cleanup.MAX_HASH_BYTES = 100
        try:
            stale = self._write("large.jpg", b"L" * 2048, 30, self.cache)
            result = cleanup.run(apply=True, cache_days=14)
            self.assertTrue(stale.exists())
            self.assertEqual(result["summary"]["deleted_images"], 0)
            self.assertGreaterEqual(result["summary"]["hash_guarded_images"], 1)
        finally:
            cleanup.MAX_HASH_BYTES = old_limit

    def test_compound_protected_folder_is_protected(self):
        self._manual_registry([])
        folder = cleanup.ROOT / "grading_photos" / "official_validation_set"
        image = self._write("keep.jpg", b"k" * 2048, 90, folder)
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(image.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_changed_cache_before_delete_is_kept(self):
        self._manual_registry([])
        stale = self._write("stale.jpg", b"s" * 2048, 30, self.cache)
        original_hash = cleanup._sha256

        def mutating_hash(path):
            digest = original_hash(path)
            with path.open("ab") as fh:
                fh.write(b"changed")
            return digest

        cleanup._sha256 = mutating_hash
        try:
            result = cleanup.run(apply=True, cache_days=14)
        finally:
            cleanup._sha256 = original_hash
        self.assertTrue(stale.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)
        self.assertGreaterEqual(result["summary"]["guarded_keep_images"], 1)

    def test_symlink_directory_is_not_scanned(self):
        self._manual_registry([])
        outside = cleanup.ROOT / "outside"
        outside.mkdir()
        target = self._write("outside.jpg", b"o" * 2048, 90, outside)
        link = self.cache / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        result = cleanup.run(apply=True, cache_days=14)
        self.assertTrue(target.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)

    def test_dry_run_never_deletes_stale_cache(self):
        self._manual_registry([])
        stale = self._write("stale.jpg", b"s" * 2048, 30, self.cache)
        result = cleanup.run(apply=False, cache_days=14)
        self.assertTrue(stale.exists())
        self.assertEqual(result["summary"]["deleted_images"], 0)
        self.assertEqual(result["summary"]["delete_candidates"], 1)


if __name__ == "__main__":
    unittest.main()
