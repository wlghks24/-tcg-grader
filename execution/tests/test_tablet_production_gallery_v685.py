import tempfile
import unittest
from pathlib import Path
from execution.tablet_production_gallery_v685 import asset_target, ASSETS

class GalleryAssetTests(unittest.TestCase):
    def test_missing_assets_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            for path in ASSETS:
                self.assertIsNone(asset_target(root,path))
    def test_unlisted_path_denied(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(asset_target(root,"/.env"))
            self.assertIsNone(asset_target(root,"/docs/tablet/v679/../../secret"))
    def test_allowlisted_regular_file(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"docs/tablet/v679/tablet_unified_dashboard_v679.html"
            p.parent.mkdir(parents=True)
            p.write_text("safe",encoding="utf-8")
            self.assertEqual(asset_target(root,"/docs/tablet/v679/tablet_unified_dashboard_v679.html"),p)
    def test_symlink_denied(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            real=base/"real";real.mkdir()
            (real/"tablet_unified_dashboard_v679.html").write_text("safe")
            parent=base/"docs/tablet/v679";parent.parent.mkdir(parents=True)
            parent.symlink_to(real,target_is_directory=True)
            self.assertIsNone(asset_target(root,"/docs/tablet/v679/tablet_unified_dashboard_v679.html"))

if __name__=="__main__":
    unittest.main()
