import re
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy

ROOT = Path(__file__).resolve().parent


class TabletAutonomyDashboardV400Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.js = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "tablet_autonomy_dashboard_v400.css").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        cls.manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        cls.main = (ROOT / "main").read_text(encoding="utf-8")

    def test_v400_dashboard_assets_are_mounted_cached_and_exposed(self):
        self.assertIn("tablet_autonomy_dashboard_v400.css?v=400", self.html)
        self.assertIn("tablet_autonomy_dashboard_v400.js?v=400", self.html)
        self.assertIn("tablet_autonomy_dashboard_v400.css", self.sw)
        self.assertIn("tablet_autonomy_dashboard_v400.js", self.sw)
        self.assertIn("tablet_autonomy_dashboard_v400.css", self.updater)
        self.assertIn("tablet_autonomy_dashboard_v400.js", self.updater)
        self.assertIn("tablet_autonomy_v400_report.json", self.updater)

    def test_dashboard_is_read_only_and_accessible(self):
        self.assertIn('const REPORT_URL = "./tablet_autonomy_v400_report.json"', self.js)
        self.assertIn('headers: {"Accept": "application/json"}', self.js)
        self.assertNotIn("POST", self.js)
        self.assertNotIn("PUT", self.js)
        self.assertNotIn("DELETE", self.js)
        self.assertIn("aria-live", self.js)
        self.assertIn("prefers-reduced-motion", self.css)

    def test_seven_requested_surfaces_and_adaptive_layout_are_visible(self):
        for label in (
            "UI · PWA",
            "카드 측정 · 등급",
            "카드 시세",
            "카드 발급 · 출시",
            "콜라보 · 이벤트",
            "구매처 · 재고신호",
            "태블릿 운영",
            "현재 최우선 영역",
            "AI 화면 정렬",
            "화면 1순위",
            "보완 긴급도",
            "V400 Canary",
            "Rollback",
            "보호 PR 후보",
            "필요 기능 후보",
            "신경망 검증학습",
            "성과 피드백",
            "현재 주목 기능",
            "안전 게이트",
        ):
            self.assertIn(label, self.js)



    def test_adaptive_layout_is_allowlisted_user_reversible_and_read_only(self):
        for token in (
            "CATEGORY_KEYS",
            "FEATURE_KEYS",
            "FEATURE_TARGETS",
            "tcgAdaptiveLayoutV400",
            "applyAdaptiveOrder",
            "applyAdaptiveFeatures",
            "applyAdaptiveModules",
            "restoreOriginalOrder",
            "restoreOriginalFeatures",
            "restoreAdaptiveModules",
            "allowlisted_categories",
            "feature_allowlist",
            "screen_module_plan",
            "policy_learning",
            "meta_neural",
            "verified_outcome_feedback",
            "layoutEnabled",
            "aria-pressed",
        ):
            self.assertIn(token, self.js)
        self.assertIn("원래 순서", self.js)
        self.assertIn("data-feature-key", self.html)
        self.assertNotIn("innerHTML =", self.js)
        self.assertNotIn("eval(", self.js)

    def test_adaptive_keys_exactly_match_real_tablet_dom(self):
        category_keys = re.findall(r'data-category-key="([^"]+)"', self.html)
        self.assertEqual(list(autonomy.CATEGORY_ORDER), category_keys)
        feature_keys = re.findall(r'data-feature-key="([^"]+)"', self.html)
        expected = [
            key
            for category in autonomy.CATEGORY_ORDER
            for key in autonomy.FEATURE_SHORTCUT_ORDER[category]
        ]
        self.assertEqual(expected, feature_keys)
        self.assertEqual(len(feature_keys), len(set(feature_keys)))
        self.assertIn('["grading","market","box","news","purchase","learning","tablet","code"]', self.js)

    def test_all_eighteen_shortcuts_bind_to_allowlisted_existing_screen_targets(self):
        pairs = re.findall(
            r'class="feature-shortcut" href="#([^"]+)" data-feature-key="([^"]+)"',
            self.html,
        )
        self.assertEqual(18, len(pairs))
        by_feature = {feature: target for target, feature in pairs}
        self.assertEqual(dict(autonomy.FEATURE_TARGETS), by_feature)
        ids = set(re.findall(r'\bid="([^"]+)"', self.html))
        self.assertTrue(set(by_feature.values()).issubset(ids))
        self.assertIn("dataset.aiModuleRank", self.js)
        self.assertIn("dataset.aiModulePriority", self.js)
        self.assertIn('dom_reorder !== false', self.js)
        self.assertNotIn("insertAdjacentHTML", self.js)

    def test_neural_policy_ui_is_read_only_bounded_and_does_not_track_user_behavior(self):
        for token in (
            "VERIFIED NEURAL POLICY",
            "검증성과 메타 신경망",
            "신경망 검증표본",
            "max_combined_bias",
        ):
            self.assertIn(token, self.js)
        self.assertIn("사용자 클릭·행동 추적 없이", self.js)
        self.assertNotIn("addEventListener(\"pointermove\"", self.js)
        self.assertNotIn("addEventListener(\"mousemove\"", self.js)
        self.assertNotIn("navigator.sendBeacon", self.js)

    def test_runtime_route_and_bundle_use_v400_while_preserving_v399_core(self):
        for name in (
            "tablet_autonomous_evolution_v399.py",
            "tablet_autonomous_evolution_v400.py",
            "tablet_autonomy_dashboard_v400.css",
            "tablet_autonomy_dashboard_v400.js",
        ):
            self.assertIn(name, self.manifest)
        self.assertIn(
            "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            self.main,
        )
        self.assertNotIn(
            "exec python tablet_autonomous_evolution_v399.py --domain tablet_gpt --execute-safe-learning",
            self.main,
        )

    def test_service_worker_cache_preserves_compatible_abi(self):
        self.assertIn("tcg-v276-network-first-runtime", self.sw)
        self.assertNotIn("tcg-v277-network-first-runtime", self.sw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
