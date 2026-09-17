#!/usr/bin/env python3
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
import tablet_runtime_manifest as manifest

CRITICAL_UI_ASSETS={
    "index.html","grading_vision_engine.js","grade_market_flow.js",
    "inventory_lookup.js","inventory_lookup.css","box_knowledge_stats.js",
    "feature_category_nav.js","feature_category_nav.css","sw.js",
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
