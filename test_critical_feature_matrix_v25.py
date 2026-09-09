#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import verify_critical_feature_matrix_v25 as matrix


class CriticalFeatureMatrixV25Tests(unittest.TestCase):
    def test_current_repository_covers_all_critical_features(self):
        result = matrix.verify()
        self.assertTrue(result["ok"], result)
        self.assertGreaterEqual(result["critical_feature_groups"], 9)
        self.assertGreaterEqual(result["critical_files_checked"], 30)

    def test_missing_camera_runtime_wiring_fails_closed(self):
        exhaustive = matrix.EXHAUSTIVE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp) / "exhaustive.yml"
            temp.write_text(
                exhaustive.replace("node verify_camera_runtime.js", "# removed camera runtime"),
                encoding="utf-8",
            )
            with mock.patch.object(matrix, "EXHAUSTIVE", temp):
                result = matrix.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("camera_runtime" in item for item in result["failures"]))

    def test_missing_instagram_local_source_verification_fails_closed(self):
        instagram = matrix.INSTAGRAM_SELFREFINE.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp) / "instagram.yml"
            temp.write_text(
                instagram.replace(
                    "python -m instagram_tcg_content.test_source_verification_engine",
                    "# removed Instagram-local source verification",
                ),
                encoding="utf-8",
            )
            with mock.patch.object(matrix, "INSTAGRAM_SELFREFINE", temp):
                result = matrix.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("source_verification" in item for item in result["failures"]))

    def test_reactivating_legacy_cross_domain_schedule_fails_closed(self):
        legacy = matrix.DAILY.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp) / "legacy.yml"
            temp.write_text(
                legacy.replace(
                    "  workflow_dispatch:",
                    "  schedule:\n    - cron: '0 21 * * *'\n  workflow_dispatch:",
                ),
                encoding="utf-8",
            )
            with mock.patch.object(matrix, "DAILY", temp):
                result = matrix.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("still scheduled" in item for item in result["failures"]))

    def test_reactivating_legacy_snapshot_writer_fails_closed(self):
        legacy = matrix.PERSIST_MAIN_CROSSCHECK.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp) / "persist.yml"
            temp.write_text(
                legacy.replace(
                    "permissions:\n  contents: read",
                    "permissions:\n  contents: write",
                ),
                encoding="utf-8",
            )
            with mock.patch.object(matrix, "PERSIST_MAIN_CROSSCHECK", temp):
                result = matrix.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("contents write" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
