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
        self.assertIn("row?.market_observed_at||row?.source_date", self.runtime)
        self.assertNotIn("freshnessPoints(row.source_date)", self.runtime)
        self.assertIn("row?.transactions", self.runtime)
        self.assertIn("row.sale_status", self.runtime)
        self.assertIn("row?.link_status", self.runtime)
        self.assertIn('가격 상승률 순위가 아니라', self.runtime)

    def test_hit_filter_updates_market_signal_mode(self):
        self.assertIn("const control=$('analysisAsset')", self.runtime)
        self.assertIn("if(value==='BOX'||value==='HIT')", self.runtime)
        self.assertIn('selectedCatalogMode=value', self.runtime)
        self.assertIn("control.addEventListener('change'", self.runtime)

    def test_box_knowledge_has_game_first_filter_and_rich_empty_state(self):
        for token in (
            "boxKbFilterBar", "boxKbGame", "boxKbFilterState",
            "게임을 먼저 고르세요", "전체 게임 보기", "전체 국가 보기",
        ):
            self.assertIn(token, self.runtime)
        self.assertIn("tcg_game_registry.json", self.runtime)
        self.assertIn("optgroup", self.runtime)

    def test_hot_and_expanded_analysis_follow_selected_game(self):
        self.assertIn("document.getElementById('analysisGame')?.value", self.runtime)
        self.assertIn("selected==='ALL'||game===selected", self.runtime)
        self.assertIn("renderExpandedAnalysisFallback", self.runtime)
        self.assertIn("COUNTRY_BOX_DATA 외 확장 수집 결과", self.runtime)
        self.assertIn("전체 자료 수집", self.runtime)

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
