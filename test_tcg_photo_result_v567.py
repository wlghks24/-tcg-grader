#!/usr/bin/env python3
"""V567 safety: photo-specific results must not fabricate grades or cross-SKU prices."""
import shutil
import subprocess
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
class PhotoReportV567(unittest.TestCase):
    def test_node_photo_contract(self):
        if shutil.which("node") is None:
            self.skipTest("node unavailable in local tablet; CI uses the Node environment")
        run=subprocess.run(["node","test_tcg_photo_result_v567.js"],cwd=ROOT,
                           capture_output=True,text=True,timeout=25)
        self.assertEqual(run.returncode,0,run.stdout+"\n"+run.stderr)
    def test_explicit_grading_market_data_boundaries(self):
        script=(ROOT/"tcg_photo_result_v567.js").read_text(encoding="utf-8")
        price=(ROOT/"tcg_card_detail_v566.js").read_text(encoding="utf-8")
        self.assertIn('evidence_type === "completed_sale"',price)
        self.assertIn("strictIdentityMatch",price)
        self.assertIn("openFromPhoto",price)
        self.assertIn("사진 기반 사전등급",script)
        self.assertIn("세대·시리즈 근거 부족",script)
        self.assertIn("영어판은 북미판과 동일하지 않습니다",script)
        self.assertIn("root.TCGPhotoResultV567",script)
        self.assertNotIn("eval(",script)
        self.assertNotIn("innerHTML",script)
        self.assertNotIn("createObjectURL(",script)
        self.assertIn('canvas.toDataURL("image/png")',script)

        self.assertNotIn("document.write(",script)
if __name__=="__main__":
    unittest.main()
