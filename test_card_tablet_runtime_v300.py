from __future__ import annotations

import unittest
from pathlib import Path

import card_grading_valuation as valuation
import grading_accuracy_v99 as accuracy
import multi_market_price_collector as multi_market
import tablet_runtime_manifest as manifest

ROOT = Path(__file__).resolve().parent


class CardTabletRuntimeV300Tests(unittest.TestCase):
    def test_tablet_manifest_contains_complete_card_analysis_and_market_chain(self) -> None:
        required = {
            "grading_accuracy_v99.py",
            "card_grading_valuation.py",
            "card_identity_recognition.py",
            "multi_market_price_collector.py",
            "grading_vision_engine.js",
            "grading_accuracy_v99.js",
            "card_identity_recognition.js",
            "grade_market_flow.js",
            "auto_market_center.js",
            "multi_market_prices.js",
            "multi_market_prices.css",
            "auto_validation_flow.js",
            "image_quality_guard.js",
            "market_catalog_expander.js",
            "box_knowledge_stats.js",
            "box_knowledge_stats.css",
            "graded_photo_dashboard.js",
            "graded_photo_dashboard.css",
            "sw.js",
        }
        self.assertTrue(required.issubset(set(manifest.ACTIVE_RUNTIME_FILES)))

    def test_server_and_browser_market_pipeline_are_wired_together(self) -> None:
        server = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("if path=='/api/multi-market-prices':", server)
        self.assertIn("from multi_market_price_collector import search_multi_market", server)
        for asset in (
            "multi_market_prices.js",
            "auto_market_center.js",
            "auto_validation_flow.js",
            "image_quality_guard.js",
            "grade_market_flow.js",
        ):
            self.assertIn(asset, index)
            self.assertIn(asset, sw)

    def test_missing_or_invalid_grade_evidence_stays_fail_closed(self) -> None:
        self.assertEqual(100.0, accuracy.combine_defect_risk(None, 0, 0))
        self.assertEqual(1.0, accuracy.estimate_raw_grade(50, 50, None, None, None, "PSA"))
        incomplete = {
            "centering_front": 50,
            "centering_back": 50,
            "corners": 10,
            "edges": 10,
            "micro_flaws": 0,
            "is_authentic": True,
        }
        result = valuation.estimate_grades(incomplete)
        self.assertFalse(result["ok"])
        self.assertEqual("FAILED", result["status"])
        self.assertIn("surface", result["reason"])

    def test_generation_probability_and_market_safety_contracts_are_present(self) -> None:
        identity = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        shell = (ROOT / "ui_app_shell_v272.js").read_text(encoding="utf-8")
        market = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("generationByYear(year,input?.region)", identity)
        self.assertIn("COPYRIGHT\\s*", identity)
        self.assertIn("window.tcgGradeProbabilities", shell)
        self.assertNotIn('grade === 9 ? "p9prob"', shell)
        self.assertIn("actual!==wanted)return -999", market)

    def test_multi_market_prices_do_not_fabricate_empty_results_or_largest_number(self) -> None:
        self.assertEqual([], multi_market.search_multi_market("", force=True)["items"])
        fx = {"KRW": 1.0, "USD": 1400.0, "JPY": 9.0}
        picked = multi_market._extract_price("MSRP $199.99 · current price $79.99", fx)
        self.assertIsNotNone(picked)
        self.assertEqual(111986, picked["price_krw"])

    def test_current_runtime_keeps_old_and_new_card_regressions_in_gate(self) -> None:
        source = (ROOT / "verify_current_runtime.py").read_text(encoding="utf-8")
        for name in (
            "test_card_core_crosscheck_v291.py",
            "test_card_core_crosscheck_v292.py",
            "test_card_core_crosscheck_v295.py",
            "test_card_core_provenance_v296.py",
            "test_card_market_edition_v297.py",
            "test_card_probability_ui_v298.py",
            "test_card_regression_gate_v299.py",
            "test_card_tablet_runtime_v300.py",
            "test_multi_market_price_collector.py",
            "test_tablet_runtime_manifest_ui_assets_v254.py",
        ):
            self.assertIn(name, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
