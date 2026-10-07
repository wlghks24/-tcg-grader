#!/usr/bin/env python3
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ExpandedTcgUiV469Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "index.html").read_text(encoding="utf-8")
        cls.ui = (ROOT / "tcg_registry_ui_v469.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "tcg_registry_ui_v469.css").read_text(encoding="utf-8")
        cls.updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        cls.manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        cls.sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        cls.registry = json.loads((ROOT / "tcg_game_registry.json").read_text(encoding="utf-8"))

    def test_registry_has_expanded_market_population_without_grading_expansion(self):
        games = self.registry["games"]
        core = [row for row in games if row.get("state") == "core"]
        promoted = [row for row in games if row.get("state") == "promoted"]
        watch = [row for row in games if row.get("state") == "watch"]
        self.assertGreaterEqual(len(games), 30)
        self.assertEqual(3, len(core))
        self.assertGreaterEqual(len(promoted), 9)
        self.assertGreaterEqual(len(watch), 18)
        self.assertTrue(all(row.get("capabilities", {}).get("grading") is True for row in core))
        self.assertTrue(all(row.get("capabilities", {}).get("grading") is False for row in promoted + watch))
        self.assertTrue(all(row.get("capabilities", {}).get("market") is True for row in promoted))

    def test_visible_tablet_ui_has_registry_cockpit_and_keeps_three_grading_buttons(self):
        self.assertIn('id="tcgRegistryMarketHub"', self.index)
        self.assertIn("시세 · 확장 TCG 수집센터", self.index)
        self.assertIn("tcg_registry_ui_v469.css?v=469", self.index)
        self.assertIn("tcg_registry_ui_v469.js?v=469", self.index)
        self.assertIn("등급 보정이 검증된 포켓몬 · 원피스 · 나루토 3종만", self.index)
        games = re.findall(r'data-simple-game="([^"]+)"', self.index)
        self.assertEqual(["pokemon", "onepiece", "naruto"], games)

    def test_market_promo_purchase_selectors_are_registry_driven(self):
        for selector in ("v12Game", "v13Game", "analysisGame", "tradeGame"):
            self.assertIn(f'"{selector}"', self.ui)
        self.assertIn('document.getElementById("promoGame")', self.ui)
        self.assertIn('document.getElementById("purchaseGame")', self.ui)
        self.assertIn('row.state !== "watch"', self.ui)
        self.assertIn('["watch", "WATCH · 관찰중", true]', self.ui)
        self.assertIn("WATCH TCG는 화면에서 수집·검증 상태만 보여주며", self.ui)
        self.assertIn("purchaseTerm(game,region)", self.index)
        self.assertIn('purchaseTerm(game,"KR")', self.index)

    def test_real_collection_evidence_outputs_are_exposed_read_only(self):
        self.assertIn("'promoted_tcg_source_signals_v413.json'", self.updater)
        self.assertIn("'promoted_tcg_multisource_coverage_v432.json'", self.updater)
        self.assertIn("RUNTIME_PUBLIC_FILES", self.updater)
        self.assertIn("promoted_tcg_source_signals_v413.json", self.ui)
        self.assertIn("promoted_tcg_multisource_coverage_v432.json", self.ui)

    def test_new_ui_is_bound_to_runtime_and_pwa_cache(self):
        for name in ("tcg_registry_ui_v469.js", "tcg_registry_ui_v469.css"):
            self.assertIn(f'"{name}"', self.manifest)
            self.assertIn(name, self.updater)
            self.assertIn("./" + name, self.sw)
        self.assertIn("tcg-v469-network-first-runtime", self.sw)

    def test_fail_closed_copy_does_not_claim_unverified_prices_stock_or_grading(self):
        self.assertIn("확인되지 않은 가격/재고/수익은 생성하지 않습니다.", self.ui)
        self.assertIn("등급 미지원", self.ui)
        self.assertIn("실시간 구매 차단", self.ui)
        self.assertNotIn("profit guarantee", self.ui.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
