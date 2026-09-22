from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class TabletAppDockV276Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.js = (ROOT / "feature_category_nav.js").read_text(encoding="utf-8")
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")

    def test_existing_navigation_and_tablet_contracts_are_preserved(self) -> None:
        self.assertIn('version: "v30-tablet-manager-hub"', self.js)
        self.assertEqual(self.html.count('class="feature-category"'), 8)
        self.assertEqual(self.html.count('class="feature-shortcut"'), 18)
        self.assertEqual(self.html.count('class="tablet-manager-action"'), 6)
        for label in ("태블릿 상태", "서버 상태", "업데이트", "자동시작", "네트워크", "오류검사"):
            self.assertIn(label, self.html)

    def test_app_dock_has_four_clear_primary_destinations(self) -> None:
        self.assertIn('uiVersion: "v276-motion-pwa-hardening"', self.js)
        for token in (
            '{ key: "menu", icon: "☰", label: "메뉴", target: "featureCategories" }',
            '{ key: "grade", icon: "🎴", label: "등급", target: "simpleGradeV32" }',
            '{ key: "market", icon: "💰", label: "시세", target: "market12section" }',
            '{ key: "tablet", icon: "📱", label: "태블릿", target: "tabletManagerHub" }',
        ):
            self.assertIn(token, self.js)
        self.assertIn('dock.setAttribute("aria-label", "주요 기능 빠른 이동")', self.js)
        self.assertIn('link.setAttribute("aria-current", "location")', self.js)
        self.assertIn('link.setAttribute("aria-controls", item.target)', self.js)
        self.assertNotIn('aria-current="page"', self.js)

    def test_dock_is_responsive_safe_area_and_reduced_motion_aware(self) -> None:
        for token in (
            "@media(max-width:1180px)",
            "env(safe-area-inset-bottom,0px)",
            "grid-template-columns:repeat(4,minmax(0,1fr))",
            "backdrop-filter:blur(18px)",
            "@media(max-width:360px)",
            "@media(prefers-color-scheme:dark)",
            "@media(prefers-reduced-motion:reduce)",
            "@media(forced-colors:active)",
            'window.matchMedia?.("(prefers-reduced-motion: reduce)")',
            'reducedMotionPreferred() ? "auto" : "smooth"',
        ):
            self.assertIn(token, self.js)

    def test_pwa_update_and_offline_cache_are_rotated_with_ui(self) -> None:
        self.assertIn("const CACHE='tcg-v292-card-core-runtime';", self.sw)
        self.assertIn("'./feature_category_nav.css'", self.sw)
        self.assertIn("'./feature_category_nav.js'", self.sw)
        self.assertIn("requestServiceWorkerRefresh();", self.js)
        self.assertIn("navigator.serviceWorker.getRegistration()", self.js)
        self.assertIn("registration?.update?.()", self.js)

    def test_dock_does_not_replace_or_hide_feature_data_logic(self) -> None:
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn("eval(", self.js)
        self.assertNotIn("new Function", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertIn("safeTarget(item.target)", self.js)
        self.assertIn("APP_DOCK_ITEMS.every", self.js)
        self.assertIn("createAppDock();", self.js)


if __name__ == "__main__":
    unittest.main()
