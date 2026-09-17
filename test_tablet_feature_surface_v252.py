from pathlib import Path
import unittest

import inventory_lookup


ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class TabletFeatureSurfaceV252Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = read("index.html")
        cls.server = read("tcg_updater.py")
        cls.inventory_js = read("inventory_lookup.js")
        cls.grade_flow = read("grade_market_flow.js")

    def test_hot_box_and_hit_ranking_is_real_ui_logic(self):
        required = (
            'data-category-key="box"',
            'data-category-label="BOX · HIT 분석"',
            'href="#box12section"',
            'href="#v14section"',
            'id="analysisCountry"',
            'id="analysisAsset"',
            'id="analysisGame"',
            'id="analysisSort"',
            'id="analysisSearchBtn"',
            'id="analysisQuery"',
            'class="analysis-rank"',
            '인기지수 ${popularityScore(x)}',
            '⭐ BOX 선호도',
            '🎯 대표 HIT 카드',
            '💰 HIT 참고가격',
            'market_prices.json',
            'market_watch.json',
        )
        missing = [x for x in required if x not in self.index]
        self.assertFalse(missing, f"HOT/BOX/HIT UI wiring missing: {missing}")
        self.assertIn('document.getElementById("analysisSearchBtn")?.addEventListener("click",renderCountryAnalysis)', self.index)

    def test_purchase_and_inventory_button_reaches_official_lookup_route(self):
        for marker in (
            'id="purchaseGame"',
            'id="purchaseQuery"',
            'id="purchaseSearch"',
            '<script src="inventory_lookup.js"></script>',
        ):
            self.assertIn(marker, self.index)
        for marker in (
            "document.getElementById('inventoryLookupRun')?.addEventListener('click',run)",
            "fetch('/api/inventory-lookup?q='",
            "window.runOfficialInventoryLookup=run",
        ):
            self.assertIn(marker, self.inventory_js)
        self.assertIn("if path=='/api/inventory-lookup':", self.server)
        self.assertIn("'inventory_lookup.js'", self.server)
        self.assertIn("'inventory_lookup.css'", self.server)

        payload = inventory_lookup.get_inventory_options("포켓몬 BOX", "Pokemon")
        self.assertTrue(payload["ok"])
        self.assertGreaterEqual(payload["official_lookup_count"], 1)
        self.assertEqual(payload["official_lookup_count"], len(payload["items"]))
        self.assertTrue(all(x.get("verification") == "official" for x in payload["items"]))
        self.assertTrue(all("quantity" not in x and "stock_count" not in x for x in payload["items"]))

    def test_card_camera_analysis_and_precision_shortcuts_are_connected(self):
        required = (
            'data-category-key="grading"',
            'href="#simpleGradeV32"',
            'href="#gradeStart"',
            'href="#precisionHub"',
            'id="gradeCamera"',
            'id="startAutoCamera"',
            'id="manualCapture"',
            "S('startAutoCamera').onclick=start",
            "S('manualCapture').onclick=()=>capture(frameMetric(),true)",
            "센터링 편차가 등급 상한을 낮출 수 있습니다.",
            "표면 스크래치·반사 위험을 반영했습니다.",
            '<script src="card_identity_recognition.js?v=207"></script>',
        )
        missing = [x for x in required if x not in self.index]
        self.assertFalse(missing, f"card grading UI wiring missing: {missing}")

    def test_card_identity_to_raw_and_five_company_market_flow_is_connected(self):
        for company in ("PSA", "BGS", "CGC", "TAG", "BRG"):
            self.assertIn(f"'{company}'", self.grade_flow)
        required = (
            "window.tcgLastGrades",
            "quickPriceSearch')?.click()",
            "identityCardName",
            "identityCardNumber",
            "identityMarketKey",
            "RAW 현재 시세",
            "등급 측정 후 업체별 거래시세",
            "window.refreshAutoGradeMarketFlow",
        )
        missing = [x for x in required if x not in self.grade_flow]
        self.assertFalse(missing, f"grade-to-market flow missing: {missing}")
        self.assertIn('<script src="grade_market_flow.js"></script>', self.index)


if __name__ == "__main__":
    unittest.main()
