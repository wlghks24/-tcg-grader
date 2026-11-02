"""V886 preview behavior checks; no production runtime or tablet installation."""
from __future__ import annotations
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PREVIEW=ROOT/"execution/tablet_market_hub_v886_preview.html"
BASELINE=ROOT/"execution/tablet_market_hub_v881.html"

class V886PreviewTest(unittest.TestCase):
    def test_preview_is_separate_and_not_deployed(self):
        before=BASELINE.read_text(encoding="utf-8")
        preview=PREVIEW.read_text(encoding="utf-8")
        self.assertIn("TCG CARD HUB V881",before)
        self.assertIn("TCG CARD HUB V886",preview)
        self.assertIn('value="CN"',preview)
        self.assertIn("TCGTabletMarketSearchV885.search",preview)
        self.assertNotIn("method:'POST'",preview)
        self.assertNotIn("innerHTML=",preview)
        self.assertEqual(preview.count("<script>"),1)
        self.assertEqual(preview.count("</script>"),1)
        self.assertIn("V886",PREVIEW.name.upper())

    @unittest.skipUnless(shutil.which("node"),"Node unavailable; real DOM simulation NOT_RUN")
    def test_local_dom_behavior_without_external_packages(self):
        result=subprocess.run(
            ["node","--test","execution/tests/tablet_market_hub_v886_preview.test.cjs"],
            cwd=ROOT,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+"\n"+result.stderr)

if __name__=="__main__":
    unittest.main()
