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
        self.assertIn("tcg_game_registry.json", self.sw)
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
            "메타 신경망",
            "화면전용 신경망",
            "모델 승격/롤백",
            "성과 피드백",
            "현재 주목 기능",
            "안전 게이트",
            "영상 참고 · AI 적응형 태블릿 홈",
            "시장 흐름 홈",
            "그레이딩 촬영 품질",
            "구매처 지도·지역",
            "HOT 카드·BOX",
            "내 카드 요약",
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
            "DEDICATED SCREEN NEURAL",
            "17입력→12 hidden→18기능",
            "화면전용 신경망",
            "17→12→18",
            "Champion/Challenger",
            "홀드아웃",
            "드리프트",
            "백업 롤백",
            "max_combined_bias",
        ):
            self.assertIn(token, self.js)
        self.assertIn("사용자 클릭·행동 추적 없이", self.js)
        self.assertNotIn("addEventListener(\"pointermove\"", self.js)
        self.assertNotIn("addEventListener(\"mousemove\"", self.js)
        self.assertNotIn("navigator.sendBeacon", self.js)

    def test_video_reference_experience_uses_verified_existing_signals_and_is_reversible(self):
        for token in (
            "EXPERIENCE_KEYS",
            "tcgVideoExperienceV403",
            "validExperiencePlan",
            "applyExperienceOrder",
            "restoreExperienceOrder",
            "video_experience_plan",
            "purchaseVideoAreaTools",
            "video-purchase-split",
            "MutationObserver",
            "cameraStatus",
            "glare",
            "market_watch.json",
            "market_prices.json",
            "releases.json",
            "promo_events.json",
            "PURCHASE_REGION_KEY",
            "tcgPurchaseRecentRegionV404",
            "REGION_SUBREGIONS",
            "purchaseVideoSubregion",
            "videoCaptureReadiness",
            "economicsValue",
            "module_confidence",
            "module_state",
            "video-hot-confidence",
            "purchaseUseLocation",
            "MARKET_LENS_GAMES",
            "MARKET_LENS_REGIONS",
            "GAME_REGISTRY_URL",
            "gameRegistryData",
            "applyGameRegistryToControls",
            "promotedRegistryGames",
            "registryOpportunityScore",
            "registryOpportunityTier",
            "registryMarketRank",
            "GUNDAM CARD GAME",
            "UNION ARENA",
            "DRAGON BALL SUPER: FUSION WORLD",
            "Disney Lorcana",
            "Star Wars: Unlimited",
            "Riftbound: League of Legends",
            "declaredGames",
            "allowedGames",
            "GAME_REGISTRY_URL",
            "MARKET_LENS_CANDIDATE_LIMIT",
            "marketLensState",
            "marketLensControls",
            "stable_focus_game",
            "stable_focus_region",
            "sessionMarketLensGame",
            "sessionMarketLensRegion",
            "자료 신선도",
            "오래된 데이터셋",
            "market_lens",
            "marketContext",
            "market_context",
            "trade_attention",
            "price_direction_used",
        ):
            self.assertIn(token, self.js)
        for token in (
            "V407 video-reference adaptive experience",
            "#purchasePanel.video-purchase-split:not([hidden])",
            ".video-quality-chip[data-state=\"good\"]",
            ".video-market-lens-chip",
            "V408 freshness-aware verified market lens",
            "prefers-reduced-motion",
        ):
            self.assertIn(token, self.css)
        self.assertIn("watchItems.slice(0, MARKET_LENS_CANDIDATE_LIMIT)", self.js)
        self.assertIn("declaredGames.every((key) => Number.isFinite(Number(gameScores[key])))", self.js)
        self.assertNotIn('["Pokémon","ONE PIECE","NARUTO"].every((key) => Number.isFinite(Number(gameScores[key])))', self.js)
        self.assertIn("priceEntries.slice(0, MARKET_LENS_CANDIDATE_LIMIT)", self.js)
        self.assertNotIn(".sort((a,b) => b.score - a.score).slice(0,40)", self.js)
        self.assertIn("시장 컨텍스트", self.js)
        self.assertIn("시장기회 순", self.js)
        self.assertIn("수익예측이 아니라", self.js)
        self.assertIn("0.65 * verifiedComponent", self.js)
        self.assertIn(".sort(registryMarketRank)", self.js)
        self.assertIn("if (aCore && bCore) return 0;", self.js)
        self.assertIn("declaredRanked", self.js)
        self.assertIn("검증 시장 컨텍스트 어댑터 최대 +4%", self.js)
        self.assertIn('Object.prototype.hasOwnProperty.call(safe, "stable_focus_game")', self.js)
        self.assertIn('Object.prototype.hasOwnProperty.call(safe, "stable_focus_region")', self.js)
        self.assertIn("연속확인 ", self.js)
        self.assertIn("시장 방향을 예측하지 않고", self.js)
        self.assertIn("현재 위치 좌표는 저장하지 않습니다", self.js)
        self.assertIn('"안산시"', self.js)
        self.assertIn("자동촬영 준비", self.js)
        self.assertIn("사선광 또는 각도를 바꿔 재촬영 권장", self.js)
        self.assertIn("등급 예상 순수익", self.js)
        self.assertIn("등급 예상 ROI", self.js)
        self.assertIn("근거 ", self.js)
        self.assertIn("재검증 ", self.js)
        self.assertNotIn('localStorage.setItem("tcgPurchaseLat', self.js)
        self.assertNotIn('localStorage.setItem("tcgPurchaseLon', self.js)
        self.assertNotIn("navigator.sendBeacon", self.js)
        self.assertNotIn('addEventListener("pointermove"', self.js)
        self.assertNotIn('addEventListener("mousemove"', self.js)


    def test_promoted_registry_games_populate_all_general_market_selectors(self):
        self.assertIn("registrySelectValue", self.js)
        self.assertIn('const marketRows = promotedRegistryGames(registry, "market")', self.js)
        self.assertIn('["v12Game","v13Game","analysisGame","tradeGame"]', self.js)
        self.assertIn('replaceRegistrySelect(document.getElementById(id), marketRows, "market", true)', self.js)
        self.assertIn('if (capability === "purchase")', self.js)
        self.assertIn('if (capability === "promo")', self.js)
        self.assertIn('return String(row.canonical)', self.js)
        self.assertIn("registryMarketLensGames", self.js)
        self.assertIn("registryMarketLensLabel", self.js)
        self.assertIn("const registryDeclared = registryMarketLensGames()", self.js)
        self.assertIn("...reportDeclared, ...registryDeclared", self.js)
        self.assertIn("gameRegistryData().catch(() => null)", self.js)
        self.assertIn('Object.freeze(["ALL","Pokémon","ONE PIECE","NARUTO"])', self.js)

    def test_runtime_route_and_bundle_use_v400_while_preserving_v399_core(self):
        for name in (
            "tablet_autonomous_evolution_v399.py",
            "tablet_autonomous_evolution_v400.py",
            "screen_policy_neural_v401.py",
            "tablet_autonomy_dashboard_v400.css",
            "tablet_autonomy_dashboard_v400.js",
            "tcg_game_registry.py",
            "tcg_game_registry.json",
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
