#!/usr/bin/env python3
"""V569: user-visible market → authoritative holdings prefill and Registry UI gates."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

class MarketCollectionBridgeV569(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"),"Node unavailable")
    def test_market_to_collection_and_expanded_game_registry(self):
        p=subprocess.run(["node","test_tcg_market_collection_bridge_v569.js"],
                         cwd=ROOT,capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stdout+"\n"+p.stderr)

    @unittest.skipUnless(shutil.which("node"),"Node unavailable")
    def test_syntax_and_previous_market_guards(self):
        for file in ("tcg_local_collection_v505.js","tcg_card_detail_v566.js",
                     "tcg_photo_result_v567.js","test_tcg_market_collection_bridge_v569.js"):
            p=subprocess.run(["node","--check",file],cwd=ROOT,
                             capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode,0,file+": "+p.stderr)

    def test_no_secondary_collection_storage_or_autosave(self):
        market=(ROOT/"tcg_card_detail_v566.js").read_text(encoding="utf-8")
        collection=(ROOT/"tcg_local_collection_v505.js").read_text(encoding="utf-8")
        self.assertNotIn("root.localStorage.setItem(STORE_KEY",market)
        self.assertIn("window.TCGLocalCollectionV505=Object.freeze",collection)
        self.assertIn("prepareMarketEntry",market)
        self.assertIn("blocked){",collection)
        self.assertIn("이전 임시 기록 백업(JSON)",market)
        self.assertNotIn("localStorage.removeItem(STORE_KEY)",market)
        self.assertNotIn('eval(',market)
        self.assertNotIn('innerHTML',market)

if __name__=="__main__":
    unittest.main()
