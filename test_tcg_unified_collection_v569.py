#!/usr/bin/env python3
"""V569 exact collection single-writer regression without claiming device QA."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

class UnifiedCollectionBridgeV569(unittest.TestCase):
    def test_node_actual_collection_bridge(self):
        if shutil.which("node") is None:
            self.skipTest("Node not available locally; CI must run the JS gate")
        x=subprocess.run(["node","test_tcg_unified_collection_v569.js"],cwd=ROOT,
            capture_output=True,text=True,timeout=30)
        self.assertEqual(x.returncode,0,x.stdout+"\n"+x.stderr)
    def test_no_auto_grade_or_auto_price_saved(self):
        a=(ROOT/"tcg_local_collection_v505.js").read_text(encoding="utf-8")
        b=(ROOT/"tcg_card_detail_v566.js").read_text(encoding="utf-8")
        c=(ROOT/"tcg_photo_result_v567.js").read_text(encoding="utf-8")
        self.assertIn("window.TCGLocalCollectionV505=Object.freeze({prefillFromMarket})",a)
        self.assertIn('const KEY="tcg-local-collection-v505"',a)
        self.assertNotIn("localStorage.setItem(",b)
        self.assertNotIn("localStorage.setItem(",c)
        self.assertIn('paid.value="";value.value=""',a)
        self.assertIn('grade.value="미감정"',a)
        self.assertIn('game.state==="promoted"',b)
        self.assertIn("root.TCGLocalCollectionV505",b)
        self.assertIn("root.TCGLocalCollectionV505",c)

if __name__=="__main__":
    unittest.main()
