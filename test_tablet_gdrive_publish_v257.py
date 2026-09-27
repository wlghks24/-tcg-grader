#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import tablet_gdrive_publish as publish
import tablet_gdrive_sync as sync


class TabletGDrivePublishV257Tests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name) / "repo"
        self.out = Path(self.td.name) / "out"
        self.root.mkdir()
        for index, name in enumerate(sync.OUTPUTS):
            (self.root / name).write_text(
                json.dumps({"name": name, "index": index}, ensure_ascii=False),
                encoding="utf-8",
            )

    def build(self):
        return publish.build_package(
            self.root,
            self.out,
            run_id="testrun01",
            main_sha="a" * 40,
            run_gates=False,
        )

    def test_build_is_receiver_compatible_and_exactly_17_jsons(self):
        bundle, manifest_path, manifest = self.build()
        loaded = sync.load_manifest(manifest_path)
        self.assertEqual("chatgpt_automation", loaded["source"])
        self.assertEqual(17, len(loaded["files"]))
        self.assertEqual(set(sync.OUTPUTS), {row["name"] for row in loaded["files"]})
        self.assertEqual(sync.sha256(bundle), manifest["bundle"]["sha256"])
        stage = Path(self.td.name) / "stage"
        stage.mkdir()
        sync.extract_bundle(bundle, stage, loaded)
        self.assertEqual(set(sync.OUTPUTS), {path.name for path in stage.iterdir()})

    def test_symlink_source_is_rejected(self):
        target = self.root / sync.OUTPUTS[0]
        external = Path(self.td.name) / "external.json"
        external.write_text("{}", encoding="utf-8")
        target.unlink()
        try:
            target.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("symlink creation unavailable")
        with self.assertRaises(ValueError):
            publish.validate_source_files(self.root)

    def test_remote_root_rejects_traversal_backslash_and_newline(self):
        self.assertEqual("TCG_Grader_Sync", publish.safe_remote_root("TCG_Grader_Sync"))
        for value in ("../TCG_Grader_Sync", "TCG_Grader_Sync/../x", "TCG\\x", "TCG\nX"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    publish.safe_remote_root(value)

    def test_upload_uses_bundle_first_manifest_last_then_readback_and_retention(self):
        bundle, manifest_path, manifest = self.build()
        uploads = []

        def fake_upload(remote, local, remote_root):
            uploads.append(local.name)

        def fake_copy(remote, remote_path, local_path):
            source = manifest_path if remote_path.endswith(manifest_path.name) else bundle
            shutil.copy2(source, local_path)

        retention = {"status": "DRIVE_RETENTION_OK", "deleted_package_objects": 0, "deleted_receipts": 0}
        with mock.patch.object(publish, "_remote_exists", return_value=False), \
             mock.patch.object(publish, "_upload_one", side_effect=fake_upload), \
             mock.patch.object(sync, "rclone_copyto", side_effect=fake_copy), \
             mock.patch.object(publish, "prune_remote_drive", return_value=retention) as prune:
            result = publish.upload_package(bundle, manifest_path, manifest)

        self.assertEqual([bundle.name, manifest_path.name], uploads)
        self.assertEqual(retention, result)
        prune.assert_called_once_with(sync.DEFAULT_REMOTE, sync.DEFAULT_REMOTE_ROOT)

    def test_retention_warning_does_not_invalidate_verified_upload(self):
        bundle, manifest_path, manifest = self.build()

        def fake_copy(remote, remote_path, local_path):
            source = manifest_path if remote_path.endswith(manifest_path.name) else bundle
            shutil.copy2(source, local_path)

        with mock.patch.object(publish, "_remote_exists", return_value=False), \
             mock.patch.object(publish, "_upload_one"), \
             mock.patch.object(sync, "rclone_copyto", side_effect=fake_copy), \
             mock.patch.object(publish, "prune_remote_drive", side_effect=OSError("quota cleanup unavailable")):
            result = publish.upload_package(bundle, manifest_path, manifest)
        self.assertEqual("DRIVE_RETENTION_WARNING", result["status"])
        self.assertIn("OSError", result["error_type"])

    def test_existing_remote_object_blocks_before_any_upload(self):
        bundle, manifest_path, manifest = self.build()
        with mock.patch.object(publish, "_remote_exists", return_value=True), \
             mock.patch.object(publish, "_upload_one") as upload:
            with self.assertRaises(FileExistsError):
                publish.upload_package(bundle, manifest_path, manifest)
        upload.assert_not_called()

    def test_manifest_tamper_is_rejected_before_upload(self):
        bundle, manifest_path, manifest = self.build()
        changed = dict(manifest)
        changed["run_id"] = "different-run"
        with mock.patch.object(publish, "_upload_one") as upload:
            with self.assertRaises(ValueError):
                publish.upload_package(bundle, manifest_path, changed)
        upload.assert_not_called()

    def test_remote_retention_deletes_only_known_old_tcg_objects(self):
        now = dt.datetime(2026, 9, 27, 12, 0, tzinfo=dt.timezone.utc)
        to_tablet = []
        stamps = [
            "20260926T000000Z",
            "20260925T000000Z",
            "20260924T000000Z",
            "20260923T000000Z",
            "20260801T000000Z",
        ]
        for index, stamp in enumerate(stamps):
            run_id = f"gpt-{stamp}-run{index:02d}"
            to_tablet.extend([
                {"Path": f"manifest_{stamp}_{run_id}.json", "ModTime": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T00:00:00Z", "IsDir": False},
                {"Path": f"TCG_VERIFIED_{stamp}_{run_id}.tar.gz", "ModTime": f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}T00:00:00Z", "IsDir": False},
            ])
        to_tablet.append({"Path": "family_photo.jpg", "ModTime": "2020-01-01T00:00:00Z", "IsDir": False})

        receipts = []
        for index in range(18):
            old = index >= 17
            stamp = "2020-01-01T00:00:00Z" if old else "2026-09-26T00:00:00Z"
            receipts.append({
                "Path": f"TABLET_SYNC_RECEIPT_gpt-20260926T000000Z-run{index:02d}.json",
                "ModTime": stamp,
                "IsDir": False,
            })
        receipts.append({"Path": "notes.txt", "ModTime": "2020-01-01T00:00:00Z", "IsDir": False})

        deleted = []

        def fake_run(args, **kwargs):
            if args[:2] == ["rclone", "lsjson"]:
                if args[2].endswith("/to_tablet"):
                    return json.dumps(to_tablet)
                if args[2].endswith("/receipts"):
                    return json.dumps(receipts)
            if args[:2] == ["rclone", "deletefile"]:
                deleted.append(args[2])
                return ""
            raise AssertionError(args)

        with mock.patch.object(publish, "run", side_effect=fake_run), \
             mock.patch.object(publish, "REMOTE_RECEIPT_MIN_KEEP", 1):
            result = publish.prune_remote_drive("gdrive", "TCG_Grader_Sync", now=now)

        old_key = "20260801T000000Z_gpt-20260801T000000Z-run04"
        self.assertTrue(any(old_key in path and path.endswith(".json") for path in deleted))
        self.assertTrue(any(old_key in path and path.endswith(".tar.gz") for path in deleted))
        self.assertTrue(any("TABLET_SYNC_RECEIPT_" in path for path in deleted))
        self.assertFalse(any("family_photo.jpg" in path or "notes.txt" in path for path in deleted))
        self.assertEqual(2, result["deleted_package_objects"])
        self.assertGreaterEqual(result["deleted_receipts"], 1)

    def test_remote_delete_helper_refuses_unknown_files_and_subdirs(self):
        with mock.patch.object(publish, "run") as run:
            with self.assertRaises(ValueError):
                publish._delete_remote_retention_file(
                    "gdrive", "TCG_Grader_Sync", "to_tablet", "family_photo.jpg"
                )
            with self.assertRaises(ValueError):
                publish._delete_remote_retention_file(
                    "gdrive", "TCG_Grader_Sync", "personal", "manifest_20260927T000000Z_gpt-20260927T000000Z-run00.json"
                )
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
