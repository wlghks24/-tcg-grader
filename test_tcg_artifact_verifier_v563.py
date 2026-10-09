#!/usr/bin/env python3
"""V563: deterministic offline verification of exact GPT package artifacts."""
from __future__ import annotations
import io
import json
from pathlib import Path
import shutil
import stat
import tempfile
import unittest
import zipfile

from execution import verify_tcg_artifact_v563 as verify
import tablet_gdrive_publish as producer
import tablet_gdrive_sync as receiver


class OfflineVerifiedArtifactV563Tests(unittest.TestCase):
    SHA = "a" * 40

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.out = Path(self.tmp.name) / "output"
        self.root.mkdir()
        for i, name in enumerate(receiver.OUTPUTS):
            (self.root / name).write_text(
                json.dumps({"fixture": name, "i": i}), encoding="utf-8"
            )
        self.bundle, self.manifest, self.meta = producer.build_package(
            self.root, self.out, run_id="fixture-v563-valid", main_sha=self.SHA,
            run_gates=False,
        )
        self.zip = Path(self.tmp.name) / "verified.zip"
        self.make_zip()

    def make_zip(self, *, manifest=None, bundle=None, names=None):
        manifest = manifest or self.manifest
        bundle = bundle or self.bundle
        names = names or (bundle.name, manifest.name)
        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as out:
            out.write(bundle, arcname=names[0])
            out.write(manifest, arcname=names[1])

    def test_valid_exact_seventeen_json_package_and_main(self):
        result = verify.verify_artifact(self.zip, self.SHA)
        self.assertEqual(result["status"], "PACKAGE_VERIFIED_OFFLINE")
        self.assertEqual(result["main_sha"], self.SHA)
        self.assertEqual(result["file_count"], 17)
        self.assertFalse(result["device_imported"])
        self.assertFalse(result["external_links_verified_live"])
        self.assertEqual(verify.main([str(self.zip), "--expected-main-sha", self.SHA]), 0)

    def test_wrong_main_and_invalid_expected_commit_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exact main"):
            verify.verify_artifact(self.zip, "b" * 40)
        with self.assertRaisesRegex(ValueError, "40 lowercase"):
            verify.verify_artifact(self.zip, "BAD_SHA")

    def test_modified_bundle_bytes_are_rejected(self):
        tampered = Path(self.tmp.name) / "tampered.tar.gz"
        shutil.copy2(self.bundle, tampered)
        with tampered.open("ab") as f:
            f.write(b"unknown extra data")
        self.make_zip(bundle=tampered, names=(self.bundle.name, self.manifest.name))
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            verify.verify_artifact(self.zip)

    def test_duplicate_missing_and_extra_zip_entries_rejected(self):
        self.zip.unlink()
        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as out:
            out.write(self.bundle)
            out.write(self.bundle)
        with self.assertRaises(ValueError):
            verify.verify_artifact(self.zip)

        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as out:
            out.write(self.bundle)
        with self.assertRaises(ValueError):
            verify.verify_artifact(self.zip)

        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as out:
            out.write(self.bundle)
            out.write(self.manifest)
            out.writestr("unexpected.json", "{}")
        with self.assertRaises(ValueError):
            verify.verify_artifact(self.zip)

    def test_zip_slip_and_symlink_cannot_be_processed(self):
        self.make_zip(names=("../" + self.bundle.name, self.manifest.name))
        with self.assertRaises(ValueError):
            verify.verify_artifact(self.zip)
        symlink = zipfile.ZipInfo(self.bundle.name)
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.zip, "w") as out:
            out.writestr(symlink, b"local-target")
            out.write(self.manifest)
        with self.assertRaises(ValueError):
            verify.verify_artifact(self.zip)

    def test_manifest_mismatch_is_rejected_by_receiver_oracle(self):
        malformed = Path(self.tmp.name) / self.manifest.name
        altered = dict(self.meta)
        altered["run_id"] = "different-run00001"
        malformed.write_text(json.dumps(altered), encoding="utf-8")
        self.make_zip(manifest=malformed)
        with self.assertRaises(ValueError):
            verify.verify_artifact(self.zip)

    def test_injected_negative_size_or_extra_outer_entries_rejected(self):
        self.make_zip()
        info = zipfile.ZipInfo("other.bin")
        self.assertFalse(verify._safe_member(zipfile.ZipInfo("../bad")))
        self.assertFalse(verify._safe_member(zipfile.ZipInfo("a/b")))
        self.assertFalse(verify._safe_member(zipfile.ZipInfo("a\\b")))
        self.assertTrue(verify._safe_member(zipfile.ZipInfo("valid.json")))


if __name__ == "__main__":
    unittest.main()
