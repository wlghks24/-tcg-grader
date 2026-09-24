#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class PsaProbabilityMarketFlowV252Tests(unittest.TestCase):
    def test_psa_8_9_10_probability_distribution_is_retained(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("window.tcgGradeProbabilities={8:p8,9:p9only,10:p10,below}", page)
        self.assertIn('$("p10prob").textContent=p10.toFixed(0)+"%"', page)
        self.assertIn('$("p9prob").textContent=p9.toFixed(0)+"%"', page)
        self.assertIn('id="p10prob"', page)
        self.assertIn('id="p9prob"', page)

    def test_grade_market_flow_uses_verified_price_engine(self):
        flow = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("const COMPANIES=['PSA','BGS','CGC','TAG','BRG']", flow)
        self.assertIn("window.tcgLastGrades||{}", flow)
        self.assertIn("typeof renderEconomics!=='function'", flow)
        self.assertIn("return 0", flow)
        self.assertIn("renderEconomics()", flow)
        self.assertIn("expectedSale", flow)
        self.assertIn("function calculateGradingEconomics(input)", page)
        self.assertIn("function normalizeGradePrices(value)", page)

    def test_market_prices_are_evidence_labeled_not_fabricated_grade_prices(self):
        data = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data.get("entries"), dict)
        self.assertTrue(data["entries"])
        for row in data["entries"].values():
            self.assertTrue(str(row.get("display", "")).strip())
            self.assertTrue(str(row.get("kind", "")).strip())
            self.assertTrue(str(row.get("market", "")).strip())
            self.assertTrue(str(row.get("source", "")).startswith("https://"))
        serialized = json.dumps(data, ensure_ascii=False).lower()
        for obsolete in ("psa8_krw", "psa9_krw", "psa10_krw", "aph10_krw"):
            self.assertNotIn(obsolete, serialized)

    def test_market_flow_assets_are_public_and_loaded(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        worker = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn('<script src="grade_market_flow.js"></script>', page)
        self.assertIn("'grade_market_flow.js'", updater)
        self.assertIn("'market_prices.json'", updater)
        self.assertIn("'./grade_market_flow.js'", worker)


if __name__ == "__main__":
    unittest.main()
