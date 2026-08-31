#!/usr/bin/env python3
from __future__ import annotations

import json
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

    def test_pair_folder_is_game_only_without_grader_subfolder(self):
        root = Path("/tmp/tcg")
        folder = queue._pair_folder(root, "pokemon", "0123456789abcdefabcd")
        self.assertEqual(folder, root / "pokemon" / "수동등록대기" / "0123456789abcdefabcd")
        self.assertNotIn("PSA", folder.parts)

    def test_game_index_preserves_grader_as_metadata_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pairs = [{
                "pair_id": "0123456789abcdefabcd",
                "game": "pokemon",
                "company": "PSA",
                "certification_id": "12345678",
                "grade": 10,
                "card_name": "Pikachu",
                "folder": str(root / "pokemon" / "수동등록대기" / "0123456789abcdefabcd"),
            }]
            queue._write_group_indexes(root, pairs)
            index_path = root / "pokemon" / "수동등록목록.json"
            self.assertTrue(index_path.is_file())
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["storage_layout"], "game_only")
            self.assertEqual(payload["pairs"][0]["company"], "PSA")
            self.assertFalse((root / "pokemon" / "PSA").exists())

    def test_legacy_grader_folder_is_migrated_to_game_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pair_id = "0123456789abcdefabcd"
            legacy = root / "pokemon" / "PSA" / "수동등록대기" / pair_id
            legacy.mkdir(parents=True)
            (legacy / "pair.json").write_text("{}", encoding="utf-8")
            (legacy / "front_candidate.jpg").write_bytes(b"front")
            (legacy / "back_candidate.jpg").write_bytes(b"back")
            old_index = root / "pokemon" / "PSA" / "수동등록목록.json"
            old_index.write_text("{}", encoding="utf-8")

            result = queue._migrate_legacy_grader_layout(root)
            moved = root / "pokemon" / "수동등록대기" / pair_id
            self.assertEqual(result["legacy_pairs_moved"], 1)
            self.assertTrue((moved / "pair.json").is_file())
            self.assertFalse((root / "pokemon" / "PSA").exists())

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
