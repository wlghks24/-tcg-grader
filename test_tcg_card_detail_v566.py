#!/usr/bin/env python3
"""V566: registry-driven price detail must preserve source and device boundaries."""
from __future__ import annotations
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class RegistryCardDetailV566(unittest.TestCase):
    def test_node_contract_and_saved_data(self):
        if shutil.which("node") is None:
            self.skipTest("node unavailable; GitHub JavaScript gate runs node separately")
        p = subprocess.run(["node", "test_tcg_card_detail_v566.js"],
                           cwd=ROOT, text=True, capture_output=True, timeout=25)
        self.assertEqual(p.returncode, 0, p.stdout + "\n" + p.stderr)

    def test_external_csp_assets_and_no_inline_data_execution(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "tcg_card_detail_v566.js").read_text(encoding="utf-8")
        css = (ROOT / "tcg_card_detail_v566.css").read_text(encoding="utf-8")
        self.assertIn('<script src="tcg_card_detail_v566.js?v=566"></script>', html)
        self.assertIn('<link rel="stylesheet" href="tcg_card_detail_v566.css?v=566">', html)
        self.assertNotIn("eval(", script)
        self.assertNotIn("innerHTML", script)
        self.assertIn('e.stopImmediatePropagation()', script)
        self.assertIn('verified === true', script)
        self.assertIn('evidence_type === "completed_sale"', script)
        self.assertIn('["core","promoted"]', script)
        self.assertIn('document.createElementNS', script)
        self.assertIn('@media(max-width:590px)', css)
        self.assertIn('body.tcg-detail-open', css)
        self.assertIn('max-width:100%', css)
        self.assertNotIn('fetch("https:', script)
        self.assertNotIn("document.write(", script)
        self.assertEqual(len(re.findall(r'<script src="tcg_card_detail_v566.js', html)), 1)

if __name__ == "__main__":
    unittest.main()
