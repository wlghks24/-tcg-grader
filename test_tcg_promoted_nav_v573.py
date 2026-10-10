#!/usr/bin/env python3
"""V573: exercise registry-expanded TCG navigation in deterministic local DOM."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class PromotedNavV573(unittest.TestCase):
    def test_real_dom_catalog_and_navigation_guards(self):
        if shutil.which("node") is None:
            self.skipTest("Node runtime unavailable on this device")
        task=subprocess.run(["node","test_tcg_promoted_nav_v573.js"],cwd=ROOT,
                            capture_output=True,text=True,timeout=25)
        self.assertEqual(task.returncode,0,task.stdout+"\n"+task.stderr)
    def test_old_market_flow_keeps_44px_controls_and_guard(self):
        text=(ROOT/"tcg_market_expanded_v487.js").read_text(encoding="utf-8")
        self.assertIn("min-height:48px",text)
        self.assertIn('home.querySelector(".tcg-detail-expanded-tabs")',text)
        self.assertIn("await detail.openCatalog({gameId:game.id})",text)
        detail=(ROOT/"tcg_card_detail_v566.js").read_text(encoding="utf-8")
        self.assertIn('openCatalog:(selection)=>open(selection)',detail)
        self.assertIn('calendarMonthCutoff',detail)
if __name__=="__main__":
    unittest.main()
