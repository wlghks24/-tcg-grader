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


class SafePhotoCleanupTests(unittest.TestCase):
    def setUp(self):
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
        self.temp.cleanup()

    def _write(self, name, data, age_days=0):
        path = self.photos / name
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

    def test_duplicate_empty_and_old_rejected_are_removed(self):
        a = self._write("a.jpg", b"d" * 2048)
        b = self._write("b.jpg", b"d" * 2048)
        empty = self._write("empty.jpg", b"")
        rejected = self._write("rejected.jpg", b"r" * 2048, 20)
        self._registry([
            {
                "image_path": rejected.relative_to(cleanup.ROOT).as_posix(),
                "image_sha256": self._sha(rejected),
                "official_result": False,
                "status": "quarantine",
                "verification_state": "completed_unverified",
                "quarantine_reasons": ["grade_mismatch"],
            }
        ])
        result = cleanup.run(apply=True)
        self.assertTrue(a.exists())
        self.assertFalse(b.exists())
        self.assertFalse(empty.exists())
        self.assertFalse(rejected.exists())
        self.assertEqual(result["summary"]["deleted_images"], 3)

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
