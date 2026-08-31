#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import graded_photo_manual_pair_queue as queue


class ManualPairQueueTests(unittest.TestCase):
    def test_identity_requires_supported_grader_and_certification(self):
        self.assertEqual(queue._identity({"company": "PSA", "certification_id": "12345678"}), ("PSA", "12345678"))
        self.assertEqual(queue._identity({"company": "PSA", "certification_id": ""}), ("", ""))
        self.assertEqual(queue._identity({"company": "OTHER", "certification_id": "12345678"}), ("", ""))

    def test_single_photo_is_rejected(self):
        row = {"game": "pokemon", "image_urls": ["https://example.com/a.jpg"]}
        self.assertIsNone(queue._pair_from_row(row))

    def test_two_unlabelled_photos_without_front_back_evidence_are_rejected(self):
        row = {"game": "pokemon", "title": "PSA 10 card", "image_urls": [
            "https://example.com/a.jpg", "https://example.com/b.jpg",
        ]}
        self.assertIsNone(queue._pair_from_row(row))

    def test_explicit_front_back_urls_are_accepted(self):
        row = {
            "game": "onepiece",
            "front_image_url": "https://example.com/front.jpg",
            "back_image_url": "https://example.com/back.jpg",
        }
        pair = queue._pair_from_row(row)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[2], "explicit_fields")

    def test_listing_declaring_front_back_with_gallery_is_accepted(self):
        row = {
            "game": "naruto",
            "title": "BGS slab front and back photos",
            "image_urls": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        }
        pair = queue._pair_from_row(row)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[2], "listing_declares_front_back")

    def test_pair_key_changes_with_certification(self):
        row = {"game": "pokemon", "url": "https://example.com/listing"}
        one = queue._pair_key(row, "https://example.com/front.jpg", "https://example.com/back.jpg", "PSA", "12345678")
        two = queue._pair_key(row, "https://example.com/front.jpg", "https://example.com/back.jpg", "PSA", "87654321")
        self.assertNotEqual(one, two)

    def test_android_root_uses_canonical_storage_not_sdcard_symlink(self):
        self.assertEqual(str(queue.ANDROID_ROOT), "/storage/emulated/0/Download/TCG등급학습")
        self.assertNotIn("/sdcard", str(queue.ANDROID_ROOT))

    def test_target_root_preflights_with_atomic_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            android = base / "Download" / "TCG등급학습"
            android.parent.mkdir(parents=True)
            local = base / "local"
            original = queue.atomic_write_json
            calls = []

            def tracked(path, payload, **kwargs):
                calls.append(Path(path))
                return original(path, payload, **kwargs)

            with mock.patch.object(queue, "ANDROID_ROOT", android), \
                 mock.patch.object(queue, "LOCAL_ROOT", local), \
                 mock.patch.object(queue, "atomic_write_json", side_effect=tracked):
                root, mode = queue._target_root()

            self.assertEqual(root, android)
            self.assertEqual(mode, "android_download")
            self.assertTrue(any(path.name == ".tcg_pair_atomic_write_test.json" for path in calls))


if __name__ == "__main__":
    unittest.main()
