from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import tablet_runtime_manifest

ROOT = Path(__file__).resolve().parent


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


class UIAppShellV272Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = read("index.html")
        self.css = read("ui_app_shell_v272.css")
        self.js = read("ui_app_shell_v272.js")
        self.sw = read("sw.js")
        self.server = read("tcg_updater.py")
        self.multi_market_js = read("multi_market_prices.js")
        self.multi_market_css = read("multi_market_prices.css")

    def test_shell_assets_load_once_with_current_cache_buster(self):
        self.assertEqual(1, self.index.count('ui_app_shell_v272.css?v=272'))
        self.assertEqual(1, self.index.count('ui_app_shell_v272.js?v=272'))
        self.assertIn('<main class="app"', self.index)

    def test_accessibility_and_keyboard_contracts(self):
        self.assertIn('className = "ui-skip-link"', self.js)
        self.assertIn('skip.textContent = "본문 바로가기"', self.js)
        self.assertIn('host.setAttribute("role", "search")', self.js)
        self.assertIn('status.setAttribute("aria-live", "polite")', self.js)
        self.assertIn('event.key === "Escape"', self.js)
        self.assertIn('event.key !== "/"', self.js)
        self.assertIn('main.setAttribute("tabindex", "-1")', self.js)
        self.assertIn(':focus-visible', self.css)
        self.assertIn('@media(prefers-reduced-motion:reduce)', self.css)
        self.assertIn('@media(prefers-contrast:more)', self.css)
        self.assertIn('@media(forced-colors:active)', self.css)
        self.assertIn('env(safe-area-inset-top', self.css)

    def test_feature_search_is_local_only_and_dom_safe(self):
        self.assertNotIn("innerHTML", self.js)
        self.assertNotIn("fetch(", self.js)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)
        self.assertNotIn("eval(", self.js)
        self.assertNotIn("new Function", self.js)
        self.assertIn('querySelectorAll(".feature-category")', self.js)
        self.assertIn('querySelectorAll(".feature-shortcut")', self.js)
        self.assertIn('toggleAttribute("data-ui-filter-hidden"', self.js)
        self.assertIn('Object.freeze({', self.js)

    def test_grading_result_cockpit_is_safe_and_explains_prediction_context(self):
        for token in (
            'panel.id = "gradeResultCockpit"',
            'AI 추정 · 공식등급 아님',
            '게임 · 카드명/번호 · 세대/세트 · 예상등급 · PSA 확률 · 출처별 시세 · 추천 거래금액 · 구매처',
            'window.tcgGradeProbabilities',
            'window.tcgLastGrades',
            'simplePokemonGeneration',
            'pokemonGenerationBadge',
            'identityCardName',
            'identityCardNumber',
            'identityRegion',
            'agmRawPrice',
            'agmRawSource',
            'gradeCockpitRecommended',
            'gradeCockpitRange',
            'gradeCockpitPsaMarket',
            'gradeCockpitMarketSources',
            'gradeCockpitGame',
            'gradeCockpitPurchaseOnline',
            'gradeCockpitPurchaseNearby',
            '추천 거래금액 · 출처별 참고가',
            '이 카드 구매처 바로 찾기',
            'exactSetContext',
            'OP: "부스터 계열"',
            '세대 번호는 별도 근거 없음',
            '원문 가격 확인 ↗',
            'window.__multiMarketPrices',
            'tcg:multi-market-updated',
            'RESULT_COMPANIES = Object.freeze(["PSA", "BGS", "CGC", "TAG", "BRG"])',
            '포켓몬은 세대 정보를 표시하고, 원피스·나루토는 세대 대신 탄/세트',
        ):
            self.assertIn(token, self.js)
        self.assertIn('gradeCockpitState.timer = setInterval(syncGradeCockpit, 1000)', self.js)
        self.assertIn('if (document.hidden) stopGradeCockpitTimer()', self.js)
        self.assertIn('window.addEventListener("pagehide", stopGradeCockpitTimer', self.js)
        self.assertIn('refreshGradeSummary: syncGradeCockpit', self.js)

    def test_grading_result_cockpit_responsive_accessibility_styles(self):
        for token in (
            '.grade-result-cockpit',
            '.grade-cockpit-grid',
            '.grade-cockpit-probabilities',
            '.grade-cockpit-companies',
            '@media(max-width:700px)',
            '@media(max-width:450px)',
            '.grade-cockpit-ai-badge',
            '.grade-cockpit-market-sources',
            '.grade-cockpit-market-source',
            '.grade-cockpit-market-meta',
            '.grade-cockpit-purchase-block',
            '.grade-cockpit-purchase-actions',
            '.grade-cockpit-market-link',
        ):
            self.assertIn(token, self.css)
        self.assertIn('.grade-result-cockpit[data-state="ready"]', self.css)
        self.assertIn('grid-template-columns:repeat(5,minmax(0,1fr))', self.css)


    def test_market_recommendation_panel_exposes_source_prices_without_blind_averaging(self):
        for token in (
            'id="multiMarketRecommendation"',
            '추천 거래 기준가',
            '어디서 얼마인지',
            'contributes_to_recommendation',
            'recommendation_source_count',
            'recommendation_sample_count',
            "window.dispatchEvent(new CustomEvent('tcg:multi-market-updated'",
        ):
            self.assertIn(token, self.multi_market_js)
        for token in (
            '.mmp-recommendation',
            '.mmp-source-price-grid',
            '.mmp-source-price',
            '.mmp-recommendation-hold',
        ):
            self.assertIn(token, self.multi_market_css)
        self.assertIn('판매중 호가는 완료거래보다 낮은 우선순위', self.multi_market_js)

    def test_market_freshness_variant_correction_and_local_export_are_visible(self):
        for token in (
            'id="multiMarketVariant"',
            'id="multiMarketExportCsv"',
            'id="multiMarketExportJson"',
            '변형/패러렐 확인 필요',
            'variantOverride',
            'freshnessText',
            'downloadEvidence',
            '추천신뢰도',
            '가격최신성',
        ):
            self.assertIn(token, self.multi_market_js)
        for token in (
            '.mmp-variant-control',
            '.mmp-head-actions',
            '.mmp-fresh-fresh',
            '.mmp-fresh-expired',
        ):
            self.assertIn(token, self.multi_market_css)
        self.assertIn("variantTerms", self.multi_market_js)
        self.assertIn("URL.createObjectURL", self.multi_market_js)

    def test_card_context_to_purchase_handoff_is_fail_closed_and_reuses_confirmed_identity(self):
        for token in (
            'function exactSetContext',
            'OP: "부스터 계열"',
            'ST: "스타터덱 계열"',
            'EB: "엑스트라 부스터 계열"',
            'PRB: "프리미엄 부스터 계열"',
            '세트코드 확인 필요 · 세대 번호는 별도 근거 없음',
            'function openPurchaseFinder',
            'purchaseQuery.value = query',
            'data-purchase-channel',
            '재고는 매장에 최종 확인하세요',
            'window.tcgRegistryGames',
            'tcg:registry-updated',
        ):
            self.assertIn(token, self.js)
        self.assertNotIn('가장 비싼', self.js)
        self.assertNotIn('재고 있음', self.js)

    def test_compact_market_sources_show_freshness_and_public_provenance_link(self):
        for token in (
            'recommendation_freshness',
            'freshness_status',
            'freshness_age_days',
            '원문 가격 확인 ↗',
            'sample_url',
            'function safeHttps',
        ):
            self.assertIn(token, self.js)

    def test_responsive_shell_contract(self):
        self.assertIn('--shell-content-max:1120px', self.css)
        self.assertIn('@media(min-width:1180px)', self.css)
        self.assertIn('--shell-content-max:1180px', self.css)
        self.assertIn('@media(max-width:350px)', self.css)
        self.assertIn('touch-action:manipulation', self.css)
        self.assertIn('overflow-wrap:anywhere', self.css)

    def test_pwa_runtime_delivery_and_manifest_contract(self):
        cache_match = re.search(r"const CACHE='tcg-v(\d+)-network-first-runtime';", self.sw)
        self.assertIsNotNone(cache_match)
        self.assertGreaterEqual(int(cache_match.group(1)), 272)
        for asset in ("./ui_app_shell_v272.css", "./ui_app_shell_v272.js"):
            self.assertIn(asset, self.sw)
        for asset in ("ui_app_shell_v272.css", "ui_app_shell_v272.js"):
            self.assertIn(repr(asset), self.server)
            self.assertIn(asset, tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)

        manifest = json.loads(read("manifest.webmanifest"))
        self.assertEqual("any", manifest.get("orientation"))
        self.assertEqual("109", str(manifest.get("version")))
        self.assertEqual("standalone", manifest.get("display"))

    def test_expanded_tcg_registry_ui_is_visible_safe_and_runtime_bound(self):
        registry_ui = read("tcg_registry_ui_v469.js")
        registry = json.loads(read("tcg_game_registry.json"))
        games = registry.get("games", [])
        core = [row for row in games if row.get("state") == "core"]
        promoted = [row for row in games if row.get("state") == "promoted"]
        watch = [row for row in games if row.get("state") == "watch"]

        self.assertIn('id="tcgRegistryMarketHub"', self.index)
        self.assertIn("시세 · 확장 TCG 수집센터", self.index)
        self.assertEqual(1, self.index.count("tcg_registry_ui_v469.css?v=469"))
        self.assertEqual(1, self.index.count("tcg_registry_ui_v469.js?v=469"))
        self.assertEqual(3, len(core))
        self.assertGreaterEqual(len(promoted), 9)
        self.assertGreaterEqual(len(watch), 18)
        self.assertTrue(all(row.get("capabilities", {}).get("grading") is True for row in core))
        self.assertTrue(all(row.get("capabilities", {}).get("grading") is False for row in promoted + watch))
        self.assertIn('row.state !== "watch"', registry_ui)
        self.assertIn('window.tcgRegistryGames = publicGames', registry_ui)
        self.assertIn('tcg:registry-updated', registry_ui)
        self.assertIn('["watch", "WATCH · 관찰중", true]', registry_ui)
        self.assertIn("promoted_tcg_source_signals_v413.json", registry_ui)
        self.assertIn("promoted_tcg_multisource_coverage_v432.json", registry_ui)
        for asset in ("tcg_registry_ui_v469.css", "tcg_registry_ui_v469.js"):
            self.assertIn(asset, self.sw)
            self.assertIn(repr(asset), self.server)
            self.assertIn(asset, tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn("'promoted_tcg_source_signals_v413.json'", self.server)
        self.assertIn("'promoted_tcg_multisource_coverage_v432.json'", self.server)

    def test_ci_and_tablet_guards_cover_new_ui_assets(self):
        final_workflow = read(".github/workflows/final-tablet-guard.yml")
        final_shell = read("VERIFY_TABLET_FINAL.sh")
        feature_matrix = read("verify_critical_feature_matrix_v25.py")
        current_runtime = read("verify_current_runtime.py")
        tablet_manifest_test = read("test_tablet_runtime_manifest_ui_assets_v254.py")
        for token in ("ui_app_shell_v272.css", "ui_app_shell_v272.js", "test_ui_app_shell_v272.py"):
            self.assertIn(token, final_workflow)
            self.assertIn(token, feature_matrix)
        for token in ("ui_app_shell_v272.css", "ui_app_shell_v272.js"):
            self.assertIn(token, final_shell)
            self.assertIn(token, tablet_manifest_test)
        self.assertIn('"ui_app_shell_v272"', current_runtime)
        self.assertIn('"test_ui_app_shell_v272.py"', current_runtime)


if __name__ == "__main__":
    unittest.main()
