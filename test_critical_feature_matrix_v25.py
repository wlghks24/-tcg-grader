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

    def test_missing_live_collection_refresh_fails_closed(self):
        daily = matrix.DAILY.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            temp = Path(tmp) / "daily.yml"
            temp.write_text(
                daily.replace(
                    "tcg_updater.update_cycle('scheduled-0600-audit')",
                    "# removed live collection refresh",
                ),
                encoding="utf-8",
            )
            with mock.patch.object(matrix, "DAILY", temp):
                result = matrix.verify()
        self.assertFalse(result["ok"])
        self.assertTrue(any("live_collection_refresh" in item for item in result["failures"]))


if __name__ == "__main__":
    unittest.main()
