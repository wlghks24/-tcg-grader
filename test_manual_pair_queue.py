#!/usr/bin/env python3
from __future__ import annotations

import contextlib
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
        self.assertEqual(payload["verified_local_photo_pairs"], 0)
        self.assertEqual(payload["not_checked_this_sync_count"], 1)
        self.assertEqual(payload["needs_redownload_count"], 0)
        self.assertFalse(payload["pairs"][0]["local_files_verified_this_sync"])
        self.assertEqual(payload["pairs"][0]["review_status"], "not_checked_this_sync")
        self.assertFalse(payload["pairs"][0]["raw_grade_calibration_eligible"])

    def test_game_index_distinguishes_ready_unchecked_and_retry_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [
                {"pair_id": "1" * 20, "game": "pokemon", "company": "PSA",
                 "downloaded": True, "local_files_verified_this_sync": True,
                 "review_status": "photo_files_ready"},
                {"pair_id": "2" * 20, "game": "pokemon", "company": "BGS",
                 "downloaded": True, "local_files_verified_this_sync": False,
                 "review_status": "not_checked_this_sync"},
                {"pair_id": "3" * 20, "game": "pokemon", "company": "CGC",
                 "downloaded": False, "needs_redownload": True,
                 "review_status": "needs_redownload"},
            ]
            queue._write_group_indexes(root, rows)
            item = json.loads((root / "pokemon" / "수동등록목록.json").read_text(encoding="utf-8"))
            self.assertEqual(item["count"], 3)
            self.assertEqual(item["visible_count"], 3)
            self.assertFalse(item["truncated"])
            self.assertEqual(item["verified_local_photo_pairs"], 1)
            self.assertEqual(item["needs_redownload_count"], 1)
            self.assertEqual(item["not_checked_this_sync_count"], 1)
            self.assertEqual([r["review_status"] for r in item["pairs"]],
                             ["photo_files_ready", "not_checked_this_sync", "needs_redownload"])
            self.assertTrue(item["pairs"][1]["downloaded_metadata"])
            self.assertFalse(item["pairs"][1]["local_files_verified_this_sync"])
            self.assertTrue(all(not r["raw_grade_calibration_eligible"] for r in item["pairs"]))

    def test_game_index_marks_truncation_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"pair_id": format(i, "020x"), "game": "gundam", "company": "PSA"}
                    for i in range(501)]
            queue._write_group_indexes(root, rows)
            item = json.loads((root / "gundam" / "수동등록목록.json").read_text(encoding="utf-8"))
            self.assertEqual(item["count"], 501)
            self.assertEqual(item["visible_count"], 500)
            self.assertTrue(item["truncated"])
            self.assertEqual(len(item["pairs"]), 500)
            self.assertEqual(item["not_checked_this_sync_count"], 501)

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

    def test_legacy_index_with_records_is_preserved_even_after_photo_move(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pair_id = "0123456789abcdefabcd"
            old_wait = root / "pokemon" / "PSA" / "수동등록대기" / pair_id
            old_wait.mkdir(parents=True)
            (old_wait / "pair.json").write_text('{"original":true}', encoding="utf-8")
            index = root / "pokemon" / "PSA" / "수동등록목록.json"
            index.write_text(json.dumps({"count": 1, "pairs": [{"pair_id": pair_id}]}), encoding="utf-8")
            result = queue._migrate_legacy_grader_layout(root)
            self.assertEqual(result["legacy_pairs_moved"], 1)
            self.assertEqual(result["legacy_indexes_preserved"], 1)
            self.assertTrue(index.is_file(), "nonempty inventory cannot be discarded automatically")
            self.assertTrue((root / "pokemon" / "수동등록대기" / pair_id / "pair.json").is_file())

    def test_legacy_photo_name_collision_keeps_original_files_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pair_id = "0123456789abcdefabcd"
            old_folder = root / "pokemon" / "PSA" / "수동등록대기" / pair_id
            old_folder.mkdir(parents=True)
            (old_folder / "pair.json").write_text('{"source":"old"}', encoding="utf-8")
            new_folder = root / "pokemon" / "수동등록대기" / pair_id
            new_folder.mkdir(parents=True)
            (new_folder / "pair.json").write_text('{"source":"new"}', encoding="utf-8")
            index = root / "pokemon" / "PSA" / "수동등록목록.json"
            index.write_text("{}", encoding="utf-8")
            result = queue._migrate_legacy_grader_layout(root)
            self.assertEqual(result["legacy_collisions"], 1)
            self.assertEqual(result["legacy_indexes_preserved"], 1)
            self.assertEqual(result["legacy_indexes_removed"], 0)
            self.assertTrue(index.exists())
            self.assertEqual((old_folder / "pair.json").read_text(encoding="utf-8"), '{"source":"old"}')
            self.assertEqual((new_folder / "pair.json").read_text(encoding="utf-8"), '{"source":"new"}')

    def test_legacy_index_with_unknown_or_malformed_shape_is_never_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            f = Path(directory) / "legacy.json"
            for value in ('{broken', '{"items":[]}', '{"count":1}', '{"pairs":[{"x":1}]}'):
                f.write_text(value, encoding="utf-8")
                self.assertFalse(queue._legacy_index_is_empty(f))
            for value in ('{}', '{"count":0,"pairs":[]}'):
                f.write_text(value, encoding="utf-8")
                self.assertTrue(queue._legacy_index_is_empty(f))

    def test_migration_skips_symlinked_legacy_folder_without_reading_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "pairs"
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "keep.txt").write_text("safe", encoding="utf-8")
            link = root / "pokemon" / "PSA"
            link.parent.mkdir(parents=True)
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            result = queue._migrate_legacy_grader_layout(root)
            self.assertGreaterEqual(result["legacy_symlink_paths_skipped"], 1)
            self.assertTrue(link.is_symlink())
            self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "safe")

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

    def test_forced_integrity_sweep_reruns_unchanged_candidate_source(self):
        signature = (300, 30)
        with mock.patch.object(queue, "_source_signature", return_value=signature), \
             mock.patch.object(queue, "sync_once", return_value={"summary": {"failed_pairs": 0}}) as sync:
            unchanged, skipped = queue._watch_cycle(signature)
            self.assertEqual(unchanged, signature)
            self.assertIsNone(skipped)
            sync.assert_not_called()
            forced, result = queue._watch_cycle(signature, integrity_due=True)
            self.assertEqual(forced, signature)
            self.assertEqual(result["summary"]["failed_pairs"], 0)
            sync.assert_called_once()

    def test_periodic_watch_detects_missing_cached_files_after_source_stops_changing(self):
        signature = (300, 30)
        payload = {"summary": {"failed_pairs": 0}}
        with mock.patch.object(queue, "_source_signature", return_value=signature), \
             mock.patch.object(queue, "sync_once", return_value=payload) as sync, \
             mock.patch.object(queue, "exclusive_file_lock", return_value=contextlib.nullcontext()), \
             mock.patch.object(queue.time, "monotonic", side_effect=[0.0, 100.0, 901.0]), \
             mock.patch.object(queue.time, "sleep", side_effect=[None, None, StopIteration]), \
             mock.patch("builtins.print"):
            with self.assertRaises(StopIteration):
                queue.watch(30, recheck_seconds=900)
        # Startup + 15-minute sweep; unchanged candidate signatures do not block
        # recovery from deleted files or failed image fetches.
        self.assertEqual(sync.call_count, 2)

    def test_integrity_watch_retries_failed_sweep_without_source_change(self):
        signature = (300, 30)
        payload = {"summary": {"failed_pairs": 0}}
        with mock.patch.object(queue, "_source_signature", return_value=signature), \
             mock.patch.object(queue, "sync_once", side_effect=[OSError("disk temporarily unavailable"), payload]) as sync, \
             mock.patch.object(queue, "exclusive_file_lock", return_value=contextlib.nullcontext()), \
             mock.patch.object(queue.time, "monotonic", side_effect=[0.0, 60.0, 200.0]), \
             mock.patch.object(queue.time, "sleep", side_effect=[None, None, StopIteration]), \
             mock.patch("builtins.print"):
            with self.assertRaises(StopIteration):
                queue.watch(30, recheck_seconds=900)
        # An exception never acknowledges a successful integrity sweep.
        self.assertEqual(sync.call_count, 2)

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
            metadata["front_sha256"] = queue.hashlib.sha256(
                bytes((255, 216, 255)) + b"A" * 65
            ).hexdigest()
            metadata["back_sha256"] = queue.hashlib.sha256(
                bytes((255, 216, 255)) + b"B" * 65
            ).hexdigest()
            (folder / "pair.json").write_text(json.dumps(metadata), encoding="utf-8")
            (folder / "front_candidate.jpg").write_bytes(bytes((255, 216, 255)) + b"A" * 65)
            self.assertFalse(queue._cached_pair_complete(*args), "one missing side must retry")
            (folder / "back_candidate.jpg").write_bytes(bytes((255, 216, 255)) + b"B" * 65)
            self.assertTrue(queue._cached_pair_complete(*args))
            # Pre-V600 cached images have no hashes: verify locally and backfill
            # without network redownload, preserving offline tablet usability.
            metadata.pop("front_sha256")
            metadata.pop("back_sha256")
            (folder / "pair.json").write_text(json.dumps(metadata), encoding="utf-8")
            self.assertTrue(queue._cached_pair_complete(*args))
            updated = json.loads((folder / "pair.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["front_sha256"], queue.hashlib.sha256(
                bytes((255, 216, 255)) + b"A" * 65
            ).hexdigest())
            self.assertEqual(updated["back_sha256"], queue.hashlib.sha256(
                bytes((255, 216, 255)) + b"B" * 65
            ).hexdigest())
            (folder / "back_candidate.jpg").write_bytes(bytes((255, 216, 255)) + b"A" * 65)
            self.assertFalse(queue._cached_pair_complete(*args), "duplicate front/back never valid")
            (folder / "back_candidate.jpg").write_bytes(bytes((255, 216, 255)) + b"B" * 65)
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
            with mock.patch.object(queue, "SOURCE", source), \
                 mock.patch.object(queue, "QUEUE", state), \
                 mock.patch.object(queue, "_target_root", return_value=(root, "local_inbox")), \
                 mock.patch.object(queue, "_download_and_normalize", side_effect=[front, back]) as fetch:
                result = queue.sync_once()
            self.assertEqual(fetch.call_count, 2)
            s = result["summary"]
            self.assertEqual(s["cache_repair_attempts"], 1)
            self.assertEqual(s["newly_saved_pairs"], 1)
            self.assertEqual(s["downloaded_metadata_pairs"], 1)
            self.assertEqual(s["verified_local_pairs_this_sync"], 1)
            self.assertEqual(s["not_checked_this_sync_pairs"], 0)
            self.assertTrue(result["pairs"][0]["local_files_verified_this_sync"])
            self.assertEqual(result["pairs"][0]["review_status"], "photo_files_ready")
            self.assertEqual(s["game_candidate_diagnostics"]["pokemon"]["repair_attempts"], 1)
            self.assertEqual(s["game_candidate_diagnostics"]["pokemon"]["saved"], 1)
            self.assertEqual(s["game_candidate_diagnostics"]["gundam"]["seen"], 0)
            self.assertFalse(result["pairs"][0]["raw_grade_calibration_eligible"])
            self.assertEqual(result["pairs"][0]["front_sha256"], queue.hashlib.sha256(front).hexdigest())
            self.assertEqual(result["pairs"][0]["back_sha256"], queue.hashlib.sha256(back).hexdigest())
            with mock.patch.object(queue, "SOURCE", source), \
                 mock.patch.object(queue, "QUEUE", state), \
                 mock.patch.object(queue, "_target_root", return_value=(root, "local_inbox")), \
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
            with mock.patch.object(queue, "SOURCE", source), \
                 mock.patch.object(queue, "QUEUE", state), \
                 mock.patch.object(queue, "_target_root", return_value=(base / "pairs", "local_inbox")), \
                 mock.patch.object(queue, "_download_and_normalize", side_effect=ValueError("offline")):
                result = queue.sync_once()
            s = result["summary"]
            self.assertEqual(s["cache_repair_failures"], 1)
            self.assertEqual(s["downloaded_metadata_pairs"], 0)
            self.assertEqual(s["verified_local_pairs_this_sync"], 0)
            self.assertEqual(s["redownload_needed_pairs"], 1)
            self.assertEqual(s["not_checked_this_sync_pairs"], 0)
            self.assertEqual(result["pairs"][0]["review_status"], "needs_redownload")
            self.assertFalse(result["pairs"][0]["local_files_verified_this_sync"])
            self.assertEqual(s["game_candidate_diagnostics"]["pokemon"]["failed"], 1)
            self.assertFalse(result["pairs"][0]["downloaded"])
            self.assertTrue(result["pairs"][0]["needs_redownload"])
            self.assertFalse(result["pairs"][0]["raw_grade_calibration_eligible"])

    def test_old_downloaded_record_without_matching_source_is_not_verified(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, state = base / "source.json", base / "queue.json"
            source.write_text(json.dumps({"records": []}), encoding="utf-8")
            state.write_text(json.dumps({"pairs": [{
                "pair_id": "a" * 20, "game": "pokemon", "company": "PSA",
                "certification_id": "12345678", "downloaded": True,
                "created_at": "2026-01-01T00:00:00Z",
            }]}), encoding="utf-8")
            with mock.patch.object(queue, "SOURCE", source), \
                 mock.patch.object(queue, "QUEUE", state), \
                 mock.patch.object(queue, "_target_root", return_value=(base / "pairs", "local_inbox")), \
                 mock.patch.object(queue, "_download_and_normalize",
                                   side_effect=AssertionError("no source, no network")):
                result = queue.sync_once()
            self.assertEqual(result["summary"]["verified_local_pairs_this_sync"], 0)
            self.assertEqual(result["summary"]["downloaded_metadata_pairs"], 1)
            self.assertEqual(result["summary"]["not_checked_this_sync_pairs"], 1)
            self.assertEqual(result["pairs"][0]["review_status"], "not_checked_this_sync")
            self.assertFalse(result["pairs"][0]["raw_grade_calibration_eligible"])
            index = json.loads((base / "pairs" / "pokemon" / "수동등록목록.json").read_text(encoding="utf-8"))
            self.assertEqual(index["verified_local_photo_pairs"], 0)
            self.assertEqual(index["not_checked_this_sync_count"], 1)
            self.assertTrue(index["pairs"][0]["downloaded_metadata"])
            self.assertFalse(index["pairs"][0]["local_files_verified_this_sync"])


    def test_photo_sync_download_budget_rotates_across_unchanged_source(self):
        # Large image batches must not monopolize the Lenovo tablet network.
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, state = base / "source.json", base / "queue.json"
            root = base / "photo_inbox"
            rows = [
                {
                    "game": "pokemon", "company": "PSA", "grade": 10,
                    "certification_id": f"{12345678 + i}",
                    "url": f"https://www.ebay.com/itm/{123456789012 + i}",
                    "front_image_url": f"https://example.com/front-{i}.jpg",
                    "back_image_url": f"https://example.com/back-{i}.jpg",
                }
                for i in range(3)
            ]
            source.write_text(json.dumps({"records": rows}), encoding="utf-8")

            def fake_download(url):
                return bytes((255, 216, 255)) + url.encode("utf-8") * 2

            with (
                mock.patch.object(queue, "SOURCE", source),
                mock.patch.object(queue, "QUEUE", state),
                mock.patch.object(queue, "_target_root", return_value=(root, "local_inbox")),
                mock.patch.object(queue, "MAX_DOWNLOAD_PAIRS_PER_SYNC", 1),
                mock.patch.object(queue, "_download_and_normalize", side_effect=fake_download) as downloads,
            ):
                for run in range(3):
                    before = downloads.call_count
                    result = queue.sync_once()
                    summary = result["summary"]
                    self.assertEqual(downloads.call_count - before, 2)
                    self.assertEqual(summary["network_pair_attempts"], 1)
                    self.assertEqual(summary["network_pair_attempts_deferred"], 2 - run)
                    self.assertEqual(summary["total_manual_pairs"], run + 1)
                    self.assertEqual(summary["downloaded_metadata_pairs"], run + 1)
                    self.assertEqual(result["download_cursor"], (run + 1) % 3)
                before = downloads.call_count
                final = queue.sync_once()
                self.assertEqual(downloads.call_count, before, "verified cache needs no refetch")
                self.assertEqual(final["summary"]["network_pair_attempts"], 0)
                self.assertEqual(final["summary"]["total_manual_pairs"], 3)
                self.assertFalse(any(row["raw_grade_calibration_eligible"] for row in final["pairs"]))

    def test_photo_sync_source_scan_window_rotates_without_dropping_later_games(self):
        # Rows past the scan window are visited on the next sweep, not lost.
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, state = base / "source.json", base / "queue.json"
            root = base / "photo_inbox"
            rows = [
                {
                    "game": "pokemon", "company": "PSA", "grade": 10,
                    "certification_id": f"{87654321 + i}",
                    "url": f"https://www.ebay.com/itm/{423456789012 + i}",
                    "front_image_url": f"https://example.com/pokemon-front-{i}.jpg",
                    "back_image_url": f"https://example.com/pokemon-back-{i}.jpg",
                }
                for i in range(4)
            ]
            source.write_text(json.dumps({"records": rows}), encoding="utf-8")
            def fake_download(url):
                return bytes((255, 216, 255)) + url.encode("utf-8") * 2
            with (
                mock.patch.object(queue, "SOURCE", source),
                mock.patch.object(queue, "QUEUE", state),
                mock.patch.object(queue, "_target_root", return_value=(root, "local_inbox")),
                mock.patch.object(queue, "MAX_SOURCE_RECORDS", 2),
                mock.patch.object(queue, "MAX_DOWNLOAD_PAIRS_PER_SYNC", 1),
                mock.patch.object(queue, "_download_and_normalize", side_effect=fake_download),
            ):
                observed_cursors = []
                for _ in range(4):
                    output = queue.sync_once()
                    self.assertEqual(output["summary"]["source_records_total"], 4)
                    self.assertEqual(output["summary"]["source_records_examined"], 2)
                    self.assertEqual(output["summary"]["source_records_over_limit"], 2)
                    self.assertEqual(output["summary"]["network_pair_attempts"], 1)
                    observed_cursors.append(output["scan_cursor"])
                self.assertEqual(observed_cursors, [2, 0, 2, 0])
                self.assertEqual(output["summary"]["total_manual_pairs"], 4)
                self.assertEqual({p["certification_id"] for p in output["pairs"]},
                                 {row["certification_id"] for row in rows})
                self.assertTrue(all(p["manual_registration_required"] for p in output["pairs"]))
                self.assertTrue(all(not p["raw_grade_calibration_eligible"] for p in output["pairs"]))

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
