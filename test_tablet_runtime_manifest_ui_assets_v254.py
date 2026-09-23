#!/usr/bin/env python3
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
import tablet_runtime_manifest as manifest

CRITICAL_UI_ASSETS={
    "index.html","grading_vision_engine.js","grading_accuracy_v99.js","card_identity_recognition.js",
    "grade_market_flow.js","grade_market_flow.css","auto_market_center.js","auto_market_center.css",
    "multi_market_prices.js","multi_market_prices.css","auto_validation_flow.js","auto_validation_flow.css",
    "image_quality_guard.js","market_catalog_expander.js",
    "inventory_lookup.js","inventory_lookup.css","grading_costs_live.js","grading_costs_live.css",
    "box_knowledge_stats.js","box_knowledge_stats.css","graded_photo_dashboard.js","graded_photo_dashboard.css",
    "feature_category_nav.js","feature_category_nav.css","ui_app_shell_v272.js","ui_app_shell_v272.css","sw.js",
}

class TabletRuntimeManifestUiAssetsV254Tests(unittest.TestCase):
    def test_critical_ui_assets_are_fail_closed_runtime_files(self):
        self.assertTrue(CRITICAL_UI_ASSETS.issubset(set(manifest.ACTIVE_RUNTIME_FILES)))

    def test_missing_browser_asset_fails_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in manifest.ACTIVE_RUNTIME_FILES:
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text("pass\n" if path.suffix==".py" else "ok\n",encoding="utf-8")
            (root/"grade_market_flow.js").unlink()
            result=manifest.audit(root,compile_python=True)
            self.assertFalse(result["ok"])
            self.assertIn("grade_market_flow.js",result["missing"])

    def test_missing_market_or_analysis_asset_fails_manifest(self):
        for victim_name in ("multi_market_prices.js","auto_validation_flow.js","image_quality_guard.js"):
            with self.subTest(victim=victim_name), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                for name in manifest.ACTIVE_RUNTIME_FILES:
                    path=root/name
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_text("pass\n" if path.suffix==".py" else "ok\n",encoding="utf-8")
                (root/victim_name).unlink()
                result=manifest.audit(root)
                self.assertFalse(result["ok"])
                self.assertIn(victim_name,result["missing"])

    def test_symlinked_browser_asset_fails_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            target=root/"target.js"; target.write_text("ok\n",encoding="utf-8")
            for name in manifest.ACTIVE_RUNTIME_FILES:
                path=root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text("pass\n" if path.suffix==".py" else "ok\n",encoding="utf-8")
            victim=root/"inventory_lookup.js"; victim.unlink(); victim.symlink_to(target)
            result=manifest.audit(root)
            self.assertFalse(result["ok"])
            self.assertIn("inventory_lookup.js",result["symlinks"])

if __name__=="__main__": unittest.main()
