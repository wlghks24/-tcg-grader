#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class TabletCriticalFeatureRoutesV252Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        cls.inventory = (ROOT / "inventory_lookup.js").read_text(encoding="utf-8")
        cls.inventory_py = (ROOT / "inventory_lookup.py").read_text(encoding="utf-8")
        cls.market = (ROOT / "auto_market_center.js").read_text(encoding="utf-8")
        cls.grade_market = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        cls.box_stats = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")

    def test_home_exposes_critical_tablet_features(self):
        for label in (
            'data-category-label="카드 등급 측정"',
            'data-category-label="시세 · 완료거래"',
            'data-category-label="BOX · HIT 분석"',
            'data-category-label="구매처 · 가까운 매장"',
        ):
            self.assertIn(label, self.html)
        for target in (
            'id="simpleGradeV32"',
            'id="gradeStart"',
            'id="market12section"',
            'id="tradingCatalogSection"',
            'id="box12section"',
            'id="purchasePanel"',
            'id="purchaseLive"',
        ):
            self.assertIn(target, self.html)
        self.assertIn('현재 거래중 카드·BOX', self.html)
        self.assertIn('출시가 · 인기 · 대표 HIT', self.html)

    def test_card_and_box_market_buttons_have_live_handlers(self):
        self.assertIn('id="search12"', self.html)
        self.assertIn('document.getElementById("search12")?.addEventListener("click",v12SearchPrices);', self.html)
        self.assertIn("setValue('asset12','HIT')", self.market)
        self.assertIn("requestAnimationFrame(()=>$('search12')?.click());", self.market)
        self.assertIn("fetch('market_prices.json?_='+Date.now(),{cache:'no-store'})", self.box_stats)
        self.assertIn("data-box-tab=\"TRADING\"", self.box_stats)
        self.assertIn("window.refreshBoxKnowledgeStats=refresh", self.box_stats)

    def test_inventory_button_reaches_real_server_route(self):
        for target in ('id="purchaseQuery"', 'id="purchaseGame"', 'id="purchaseLive"'):
            self.assertIn(target, self.html)
        self.assertIn("document.getElementById('inventoryLookupRun')?.addEventListener('click',run);", self.inventory)
        self.assertIn("fetch('/api/inventory-lookup?q='+encodeURIComponent(q)+'&game='+encodeURIComponent(game)", self.inventory)
        self.assertIn("if path=='/api/inventory-lookup':", self.updater)
        self.assertIn('from inventory_lookup import get_inventory_options', self.updater)
        self.assertIn('return self.json(get_inventory_options(q,game))', self.updater)
        self.assertIn('"capability": "realtime_stock"', self.inventory_py)
        self.assertIn('재고 수량을 임의 생성하지 않습니다', self.inventory_py)

    def test_card_analysis_flows_into_identity_market_and_five_graders(self):
        self.assertIn('card_identity_recognition.js', self.html)
        self.assertIn('grade_market_flow.js', self.html)
        self.assertIn("const COMPANIES=['PSA','BGS','CGC','TAG','BRG'];", self.grade_market)
        self.assertIn("const name=(el('identityCardName')?.value||'').trim();", self.grade_market)
        self.assertIn("if(el('quickCardQuery')){el('quickCardQuery').value=q; el('quickPriceSearch')?.click();}", self.grade_market)
        self.assertIn("const grades=window.tcgLastGrades||{}", self.grade_market)
        self.assertIn('앞·뒷면 분석 완료 후 자동 표시됩니다.', self.grade_market)

    def test_critical_assets_are_served_and_cached_on_tablet(self):
        for name in (
            'inventory_lookup.js',
            'grade_market_flow.js',
            'auto_market_center.js',
            'box_knowledge_stats.js',
        ):
            self.assertIn(name, self.html)
            self.assertIn(f"'{name}'", self.updater)
            self.assertIn(f"'./{name}'", self.sw)


if __name__ == '__main__':
    unittest.main()
