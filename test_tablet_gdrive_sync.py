#!/usr/bin/env python3
import datetime as dt
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import tablet_gdrive_sync as sync


class TabletGDriveSyncTests(unittest.TestCase):
    def build_fixture(self):
        td = Path(tempfile.mkdtemp())
        src = td / "src"
        src.mkdir()
        files = []
        for i, name in enumerate(sync.OUTPUTS):
            p = src / name
            p.write_text(json.dumps({"name": name, "i": i}), encoding="utf-8")
            files.append({"name": name, "size": p.stat().st_size, "sha256": sync.sha256(p)})
        bundle = td / "TCG_VERIFIED_20260919T000000Z_testrun01.tar.gz"
        with tarfile.open(bundle, "w:gz") as tf:
            for name in sync.OUTPUTS:
                tf.add(src / name, arcname=name)
        manifest = {
            "schema_version": sync.SCHEMA,
            "repository": sync.REPO,
            "source": "chatgpt_automation",
            "run_id": "testrun01",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "main_sha": "a" * 40,
            "bundle": {
                "name": bundle.name,
                "size": bundle.stat().st_size,
                "sha256": sync.sha256(bundle),
            },
            "files": files,
        }
        mp = td / "manifest_20260919T000000Z_testrun01.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        return td, bundle, mp, manifest

    def test_valid_manifest_and_exact_17_bundle(self):
        td, bundle, mp, manifest = self.build_fixture()
        loaded = sync.load_manifest(mp)
        stage = td / "stage"
        stage.mkdir()
        sync.extract_bundle(bundle, stage, loaded)
        self.assertEqual(set(p.name for p in stage.iterdir()), set(sync.OUTPUTS))

    def test_rejects_path_traversal(self):
        td, _, _, manifest = self.build_fixture()
        bad = td / "bad.tar.gz"
        with tarfile.open(bad, "w:gz") as tf:
            info = tarfile.TarInfo("../evil.json")
            raw = b"{}"
            info.size = len(raw)
            tf.addfile(info, io.BytesIO(raw))
        stage = td / "bad-stage"
        stage.mkdir()
        with self.assertRaises(ValueError):
            sync.extract_bundle(bad, stage, manifest)

    def test_rejects_partial_manifest(self):
        td, _, mp, manifest = self.build_fixture()
        manifest["files"] = manifest["files"][:-1]
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

    def test_rejects_wrong_source_and_repo(self):
        td, _, mp, manifest = self.build_fixture()
        manifest["source"] = "unknown"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)
        manifest["source"] = "chatgpt_automation"
        manifest["repository"] = "other/repo"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

    def test_remote_name_rejects_newline(self):
        with self.assertRaises(ValueError):
            sync.safe_remote_name("gdrive\n--config=x")
        self.assertEqual(sync.safe_remote_name("gdrive:"), "gdrive")


if __name__ == "__main__":
    unittest.main()
