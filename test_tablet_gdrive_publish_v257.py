#!/usr/bin/env python3
from __future__ import annotations

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

    def test_upload_uses_bundle_first_manifest_last_then_readback(self):
        bundle, manifest_path, manifest = self.build()
        uploads = []

        def fake_upload(remote, local, remote_root):
            uploads.append(local.name)

        def fake_copy(remote, remote_path, local_path):
            source = manifest_path if remote_path.endswith(manifest_path.name) else bundle
            shutil.copy2(source, local_path)

        with mock.patch.object(publish, "_remote_exists", return_value=False), \
             mock.patch.object(publish, "_upload_one", side_effect=fake_upload), \
             mock.patch.object(sync, "rclone_copyto", side_effect=fake_copy):
            publish.upload_package(bundle, manifest_path, manifest)

        self.assertEqual([bundle.name, manifest_path.name], uploads)

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


if __name__ == "__main__":
    unittest.main()
