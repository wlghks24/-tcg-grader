#!/usr/bin/env python3
from __future__ import annotations
import unittest
from pathlib import Path

import tablet_runtime_manifest as manifest
import tcg_updater

ROOT=Path(__file__).resolve().parent

class GradingRuntimeFallbackV256Tests(unittest.TestCase):
    def test_grading_runtime_is_fail_closed_in_tablet_manifest(self):
        required={
            "grading_company_watch.py",
            "grading_costs_live.js",
            "grading_costs_live.css",
        }
        self.assertTrue(required.issubset(set(manifest.ACTIVE_RUNTIME_FILES)))

    def test_static_grading_snapshot_is_explicitly_public(self):
        self.assertIn("grading_company_updates.json",tcg_updater.PUBLIC_STATIC_FILES)
        self.assertTrue((ROOT/"grading_company_updates.json").is_file())

    def test_ui_fallback_targets_only_the_published_snapshot(self):
        source=(ROOT/"grading_costs_live.js").read_text(encoding="utf-8")
        self.assertIn("/grading_company_updates.json?t=",source)
        self.assertNotIn("../grading_company_updates.json",source)

if __name__=="__main__":
    unittest.main()
