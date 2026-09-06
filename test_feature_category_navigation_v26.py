#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
CSS = ROOT / "feature_category_nav.css"
JS = ROOT / "feature_category_nav.js"


class FeatureCategoryNavigationV26Tests(unittest.TestCase):
    def setUp(self):
        self.html = INDEX.read_text(encoding="utf-8")
        self.css = CSS.read_text(encoding="utf-8")
        self.js = JS.read_text(encoding="utf-8")

    def test_navigation_has_seven_categories_and_eighteen_shortcuts(self):
        self.assertEqual(self.html.count('class="feature-category"'), 7)
        self.assertEqual(self.html.count('class="feature-shortcut"'), 18)
        for label in (
            "카드 등급 측정",
            "OCR · 학습 · 보정",
            "시세 · 완료거래",
            "BOX · HIT 분석",
            "출시 · 프로모 · 행사",
            "구매처 · 가까운 매장",
            "검증 · 업데이트",
        ):
            self.assertIn(label, self.html)

    def test_every_shortcut_points_to_an_existing_runtime_target(self):
        targets = re.findall(r'class="feature-shortcut" href="#([A-Za-z][A-Za-z0-9_-]*)"', self.html)
        self.assertEqual(len(targets), 18)
        ids = set(re.findall(r'\bid="([^"]+)"', self.html))
        missing = sorted(set(targets) - ids)
        self.assertEqual(missing, [], missing)
        required = {
            "simpleGradeV32", "gradeStart", "precisionHub", "v30validation",
            "market12section", "gradingEconomics", "tradingCatalogSection",
            "box12section", "v14section", "releaseBoard", "audit15",
            "updateHub", "v31testdashboard",
        }
        self.assertTrue(required.issubset(set(targets)), required - set(targets))

    def test_old_two_button_launcher_is_removed(self):
        self.assertNotIn('<section class="home-launcher"', self.html)
        self.assertNotIn('data-home-target="gradeStart"', self.html)
        self.assertNotIn('data-home-target="v14section"', self.html)

    def test_category_picker_starts_compact_and_exposes_two_step_guide(self):
        self.assertNotIn('class="feature-category" open', self.html)
        self.assertIn('id="featureCategorySelected"', self.html)
        self.assertIn('class="feature-category-steps"', self.html)
        self.assertIn("1</b> 카테고리 선택", self.html)
        self.assertIn("2</b> 기능 선택", self.html)
        self.assertIn('data-category-key="grading"', self.html)
        self.assertIn('data-category-key="market"', self.html)
        self.assertIn('data-category-key="system"', self.html)
        self.assertIn('category.addEventListener("toggle"', self.js)
        self.assertIn("categories.forEach((item)", self.js)
        self.assertIn('version: "v28-clear-home"', self.js)

    def test_clear_home_identity_precedes_category_picker(self):
        title = self.html.index("<h1>카드시세분석</h1>")
        nav = self.html.index('id="featureCategories"')
        self.assertLess(title, nav)
        self.assertIn("<title>카드시세분석 · TCG 통합 도구</title>", self.html)
        self.assertIn('content="카드시세분석"', self.html)
        manifest = __import__("json").loads((ROOT / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "카드시세분석")
        self.assertEqual(str(manifest["version"]), "109")
        self.assertIn("7개 카테고리", self.html)
        self.assertIn("큰 카테고리를 누르면 필요한 기능 목록만 펼쳐집니다.", self.html)
        self.assertIn("☰ 메뉴", self.html)
        self.assertNotIn("<h1>TCG 등급 사전검사기 v109</h1>", self.html)
        self.assertIn(".app-title-primary", self.css)
        self.assertIn("기능 화면으로 이동했습니다", self.js)

    def test_navigation_is_first_class_and_mobile_safe(self):
        nav = self.html.index('id="featureCategories"')
        release = self.html.index('id="releaseBoard"')
        self.assertLess(nav, release)
        self.assertIn('id="featureCategoryFab"', self.html)
        self.assertIn('href="#featureCategories"', self.html)
        self.assertIn("@media(max-width:430px)", self.css)
        self.assertIn(".feature-category[open]", self.css)
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", self.css)
        self.assertIn(".feature-category-steps", self.css)
        self.assertIn(".feature-category-selected", self.css)
        self.assertIn("env(safe-area-inset-bottom", self.css)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_release_promo_purchase_shortcuts_use_allowlisted_panel_activation(self):
        self.assertIn('data-feature-open-panel="releasePanel"', self.html)
        self.assertIn('data-feature-open-panel="promoPanel"', self.html)
        self.assertGreaterEqual(self.html.count('data-feature-open-panel="purchasePanel"'), 2)
        self.assertIn('new Set(["releasePanel", "promoPanel", "purchasePanel"])', self.js)
        self.assertIn('if (!VALID_TOP_PANELS.has(value)) return false;', self.js)
        self.assertNotIn("eval(", self.js)
        self.assertNotIn("innerHTML", self.js)

    def test_pwa_assets_are_versioned_once(self):
        self.assertEqual(self.html.count('feature_category_nav.css?v=204'), 1)
        self.assertEqual(self.html.count('feature_category_nav.js?v=204'), 1)


if __name__ == "__main__":
    unittest.main()
