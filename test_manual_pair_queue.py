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

    def test_registered_promoted_games_are_review_only(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "games.json"
            registry.write_text(json.dumps({"schema_version": 1, "games": [
                {"id": "gundam", "state": "promoted",
                 "capabilities": {"market": True, "grading": False}},
                {"id": "watch-game", "state": "watch",
                 "capabilities": {"market": True, "grading": False}},
                {"id": "unsafe/../game", "state": "promoted",
                 "capabilities": {"market": True, "grading": False}},
                {"id": "graded-game", "state": "promoted",
                 "capabilities": {"market": True, "grading": True}},
            ]}), encoding="utf-8")
            self.assertEqual(queue._reviewable_games(registry), set(queue.GAMES) | {"gundam"})
            self.assertEqual(queue._reviewable_games(registry.with_name("no-file.json")), set(queue.GAMES))
            registry.write_text("{bad", encoding="utf-8")
            self.assertEqual(queue._reviewable_games(registry), set(queue.GAMES))

        self.assertIn("gundam", queue.REVIEW_GAMES)
        self.assertNotIn("flesh-and-blood", queue.REVIEW_GAMES)
        with self.assertRaises(ValueError):
            queue._pair_folder(Path("/tmp/tcg"), "flesh-and-blood", "0123456789abcdefabcd")
        self.assertEqual(queue._pair_folder(Path("/tmp/tcg"), "gundam", "0123456789abcdefabcd"),
                         Path("/tmp/tcg/gundam/수동등록대기/0123456789abcdefabcd"))
        self.assertIn('"raw_grade_calibration_eligible": False',
                      Path(queue.__file__).read_text(encoding="utf-8"))

    def test_promoted_folders_are_lazy_and_never_auto_register(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue._write_group_indexes(root, [{
                "pair_id": "0123456789abcdefabcd",
                "game": "gundam", "company": "PSA", "certification_id": "12345678",
                "grade": 10, "card_name": "Gundam"
            }])
            index = root / "gundam" / "수동등록목록.json"
            self.assertTrue(index.is_file())
            self.assertFalse((root / "lorcana").exists())
            payload = json.loads(index.read_text(encoding="utf-8"))
            self.assertEqual(payload["count"], 1)
            self.assertTrue(payload["manual_registration_required"])
            self.assertFalse(payload["automatic_registration"])
            self.assertFalse(payload["automatic_official_lookup"])

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

    def test_watch_cycle_retries_same_signature_after_sync_failure(self):
        previous = (100, 10)
        changed = (200, 20)
        with mock.patch.object(queue, "_source_signature", return_value=changed), \
             mock.patch.object(queue, "sync_once", side_effect=RuntimeError("temporary write failure")) as sync:
            with self.assertRaises(RuntimeError):
                queue._watch_cycle(previous)
        sync.assert_called_once()
        # The caller never receives a new acknowledged signature on failure,
        # so the same changed source remains retryable on the next interval.
        self.assertEqual(previous, (100, 10))

    def test_watch_cycle_skips_unchanged_source_and_acks_success_only(self):
        signature = (300, 30)
        with mock.patch.object(queue, "_source_signature", return_value=signature), \
             mock.patch.object(queue, "sync_once") as sync:
            acknowledged, result = queue._watch_cycle(signature)
        self.assertEqual(acknowledged, signature)
        self.assertIsNone(result)
        sync.assert_not_called()

        payload = {"summary": {"saved": 1}}
        with mock.patch.object(queue, "_source_signature", return_value=signature), \
             mock.patch.object(queue, "sync_once", return_value=payload) as sync:
            acknowledged, result = queue._watch_cycle((200, 20))
        self.assertEqual(acknowledged, signature)
        self.assertEqual(result, payload)
        sync.assert_called_once()

    def test_cache_requires_actual_front_back_jpegs_and_matching_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pair_id = "0123456789abcdefabcd"
            folder = queue._pair_folder(root, "pokemon", pair_id)
            folder.mkdir(parents=True)
            front, back = ("https://example.com/front.jpg", "https://example.com/back.jpg")
            cached = {"downloaded": True}
            args = (root, "pokemon", pair_id, "PSA", "12345678", front, back, 10, cached)
            self.assertFalse(queue._cached_pair_complete(*args), "metadata alone never proves files")
            metadata = {
                "pair_id": pair_id, "game": "pokemon", "company": "PSA",
                "certification_id": "12345678", "grade": 10,
                "front_image_url": front, "back_image_url": back,
                "downloaded": True, "raw_grade_calibration_eligible": False,
            }
            (folder / "pair.json").write_text(json.dumps(metadata), encoding="utf-8")
            (folder / "front_candidate.jpg").write_bytes(bytes((255, 216, 255)) + b"A" * 65)
            self.assertFalse(queue._cached_pair_complete(*args), "one missing side must retry")
            (folder / "back_candidate.jpg").write_bytes(bytes((255, 216, 255)) + b"B" * 65)
            self.assertTrue(queue._cached_pair_complete(*args))
            self.assertFalse(queue._cached_pair_complete(
                root, "pokemon", pair_id, "PSA", "99999999", front, back, 10, cached
            ), "certification mismatch prevents stale reuse")
            self.assertFalse(queue._cached_pair_complete(
                root, "pokemon", pair_id, "PSA", "12345678", front, back, 9, cached
            ), "grade revision prevents stale metadata")
            (folder / "front_candidate.jpg").write_bytes(b"not a JPEG" * 10)
            self.assertFalse(queue._cached_pair_complete(*args), "damaged bytes do not count")

    def test_sync_recovers_missing_cached_pair_and_keeps_per_game_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "pairs"
            source = base / "candidates.json"
            state = base / "queue.json"
            sample = {
                "game": "pokemon", "company": "PSA", "grade": 10,
                "certification_id": "12345678", "url": "https://www.ebay.com/itm/123456789012",
                "front_image_url": "https://example.com/front.jpg",
                "back_image_url": "https://example.com/back.jpg",
            }
            source.write_text(json.dumps({"records": [sample]}), encoding="utf-8")
            pair_id = queue._pair_key(
                sample, sample["front_image_url"], sample["back_image_url"], "PSA", "12345678"
            )
            prior = {"pair_id": pair_id, "game": "pokemon", "company": "PSA",
                     "downloaded": True, "created_at": "2026-01-01T00:00:00Z"}
            state.write_text(json.dumps({"pairs": [prior]}), encoding="utf-8")
            front = bytes((255, 216, 255)) + b"A" * 60
            back = bytes((255, 216, 255)) + b"B" * 60
            with mock.patch.object(queue, "SOURCE", source), \\
                 mock.patch.object(queue, "QUEUE", state), \\
                 mock.patch.object(queue, "_target_root", return_value=(root, "local_inbox")), \\
                 mock.patch.object(queue, "_download_and_normalize", side_effect=[front, back]) as fetch:
                result = queue.sync_once()
            self.assertEqual(fetch.call_count, 2)
            s = result["summary"]
            self.assertEqual(s["cache_repair_attempts"], 1)
            self.assertEqual(s["newly_saved_pairs"], 1)
            self.assertEqual(s["intact_downloaded_pairs"], 1)
            self.assertEqual(s["game_candidate_diagnostics"]["pokemon"]["repair_attempts"], 1)
            self.assertEqual(s["game_candidate_diagnostics"]["pokemon"]["saved"], 1)
            self.assertEqual(s["game_candidate_diagnostics"]["gundam"]["seen"], 0)
            self.assertFalse(result["pairs"][0]["raw_grade_calibration_eligible"])
            with mock.patch.object(queue, "SOURCE", source), \\
                 mock.patch.object(queue, "QUEUE", state), \\
                 mock.patch.object(queue, "_target_root", return_value=(root, "local_inbox")), \\
                 mock.patch.object(queue, "_download_and_normalize", side_effect=AssertionError("unwanted fetch")):
                again = queue.sync_once()
            self.assertEqual(again["summary"]["existing_pairs_skipped"], 1)
            self.assertEqual(again["summary"]["cache_repair_attempts"], 0)

    def test_failed_repair_downgrades_stale_downloaded_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, state = base / "source.json", base / "queue.json"
            sample = {
                "game": "pokemon", "company": "PSA", "grade": 10,
                "certification_id": "12345678", "url": "https://www.ebay.com/itm/123456789012",
                "front_image_url": "https://example.com/front.jpg",
                "back_image_url": "https://example.com/back.jpg",
            }
            pair_id = queue._pair_key(sample, sample["front_image_url"], sample["back_image_url"],
                                      "PSA", "12345678")
            source.write_text(json.dumps({"records": [sample]}), encoding="utf-8")
            state.write_text(json.dumps({"pairs": [{
                "pair_id": pair_id, "game": "pokemon", "company": "PSA", "downloaded": True,
                "created_at": "2026-01-01T00:00:00Z",
            }]}), encoding="utf-8")
            with mock.patch.object(queue, "SOURCE", source), \\
                 mock.patch.object(queue, "QUEUE", state), \\
                 mock.patch.object(queue, "_target_root", return_value=(base / "pairs", "local_inbox")), \\
                 mock.patch.object(queue, "_download_and_normalize", side_effect=ValueError("offline")):
                result = queue.sync_once()
            s = result["summary"]
            self.assertEqual(s["cache_repair_failures"], 1)
            self.assertEqual(s["intact_downloaded_pairs"], 0)
            self.assertEqual(s["redownload_needed_pairs"], 1)
            self.assertEqual(s["game_candidate_diagnostics"]["pokemon"]["failed"], 1)
            self.assertFalse(result["pairs"][0]["downloaded"])
            self.assertTrue(result["pairs"][0]["needs_redownload"])
            self.assertFalse(result["pairs"][0]["raw_grade_calibration_eligible"])

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
