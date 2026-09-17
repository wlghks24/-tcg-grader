import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


class HotBoxHitRuntimeV252Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.runtime = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")
        cls.market = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        cls.watch = json.loads((ROOT / "market_watch.json").read_text(encoding="utf-8"))

    def test_box_hit_menu_and_target_are_wired(self):
        self.assertIn('data-category-label="BOX · HIT 분석"', self.index)
        self.assertIn('href="#v14section"', self.index)
        self.assertIn('id="v14section"', self.index)
        for control in (
            'id="analysisQuery"', 'id="analysisCountry"', 'id="analysisAsset"',
            'id="analysisGame"', 'id="analysisSort"', 'id="analysisSearchBtn"',
            'id="analysisClearBtn"', 'id="countryAnalysisList"',
        ):
            self.assertIn(control, self.index)
        self.assertIn('document.getElementById("analysisSearchBtn")?.addEventListener("click",renderCountryAnalysis)', self.index)
        self.assertIn('document.getElementById("analysisQuery")?.addEventListener("keydown"', self.index)

    def test_hot_panel_uses_only_local_verified_runtime_files(self):
        self.assertIn("fetch('market_prices.json?_='+Date.now()", self.runtime)
        self.assertIn("fetch('market_watch.json?_='+Date.now()", self.runtime)
        self.assertNotIn('fetch("http://', self.runtime)
        self.assertNotIn("fetch('http://", self.runtime)
        self.assertIn("panel.id='hotMarketSignals'", self.runtime)
        self.assertIn("'📦 HOT BOX'", self.runtime)
        self.assertIn("'🎴 HOT 카드'", self.runtime)
        self.assertIn('HOT 점수는 구매추천이 아니라 활동 신호입니다.', self.runtime)

    def test_hot_score_is_activity_signal_not_fake_price_change(self):
        for token in ('freshnessPoints', 'evidencePoints', 'watchPoints', 'linkPoints'):
            self.assertIn(f'function {token}', self.runtime)
        self.assertIn("row.source_date", self.runtime)
        self.assertIn("row?.transactions", self.runtime)
        self.assertIn("row.sale_status", self.runtime)
        self.assertIn("row?.link_status", self.runtime)
        self.assertIn('가격 상승률 순위가 아니라', self.runtime)

    def test_hit_filter_updates_market_signal_mode(self):
        self.assertIn("const control=$('analysisAsset')", self.runtime)
        self.assertIn("if(value==='BOX'||value==='HIT')", self.runtime)
        self.assertIn('selectedCatalogMode=value', self.runtime)
        self.assertIn("control.addEventListener('change'", self.runtime)

    def test_current_market_payload_supports_both_box_and_hit(self):
        entries = self.market.get('entries') or {}
        self.assertIsInstance(entries, dict)
        assets = {key.rsplit('|', 1)[-1] for key in entries if isinstance(key, str) and '|' in key}
        self.assertTrue({'BOX', 'HIT'} <= assets)
        self.assertTrue(any(isinstance(row, dict) and row.get('source_date') for row in entries.values()))
        items = self.watch.get('items') or []
        self.assertIsInstance(items, list)
        self.assertTrue(any(isinstance(row, dict) and row.get('asset') == 'BOX' for row in items))


if __name__ == '__main__':
    unittest.main()
