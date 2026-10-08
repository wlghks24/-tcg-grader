#!/usr/bin/env python3
"""V489 graded-photo cockpit purchase handoff, market evidence, and registry boundaries."""
from __future__ import annotations
import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class CardGradePurchaseHandoffV489(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "ui_app_shell_v272.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "ui_app_shell_v272.css").read_text(encoding="utf-8")
        cls.registry = (ROOT / "tcg_registry_ui_v469.js").read_text(encoding="utf-8")

    def test_game_generation_is_explicit_and_cannot_create_fake_seasons(self):
        for token in (
            'gradeCockpitGame', 'gradeGameLabel', 'function exactSetContext',
            'game === "onepiece"', 'game === "naruto"',
            'simplePokemonGeneration', '세트코드 확인 필요',
            '세대 번호는 별도 근거 없음',
        ):
            self.assertIn(token, self.js)
        self.assertIn('gradeCockpitGeneration', self.js)

    def test_measured_card_to_purchase_panels_is_bounded(self):
        for token in (
            "gradeCockpitPurchaseOnline", "gradeCockpitPurchaseNearby",
            "gradeCockpitPurchaseMeta", 'identityCardNumber',
            'identityCardName', 'purchaseQuery', 'purchaseGame',
            'purchasePanel', 'data-purchase-channel', 'mode === "nearby"',
            '재고는 매장에 최종 확인',
        ):
            self.assertIn(token, self.js)
        self.assertIn('query = [name && name', self.js)
        self.assertIn('url.protocol !== "https:"', self.js)
        self.assertNotIn("Math.random", self.js)

    def test_seller_price_links_and_existing_condition_filters_coexist(self):
        for token in (
            'grade-cockpit-market-link', 'sample_url', 'noopener noreferrer',
            'freshness_age_days', 'seller_names', 'recommendation_confidence',
            'requested_condition', 'requested_printing',
            'contributes_to_recommendation',
        ):
            self.assertIn(token, self.js)
        self.assertIn(".grade-cockpit-purchase-actions", self.css)
        self.assertIn(".grade-cockpit-market-link", self.css)

    def test_registry_snapshot_from_validated_rows_only(self):
        for token in (
            'const games = validateRegistry(results[0]);',
            'window.tcgRegistryGames = publicGames;',
            'new CustomEvent("tcg:registry-updated"',
            'script.src = "tcg_market_expanded_v487.js?v=487"',
            'if (row.state === "watch" || !row.capabilities.purchase) continue;',
        ):
            self.assertIn(token, self.registry)

    def test_committed_store_candidates_never_claim_live_stock(self):
        payload = json.loads((ROOT / "purchase_sources.json").read_text(encoding="utf-8"))
        rows = payload["sources"]
        promoted = [x for x in rows if x.get("registry_generated") is True]
        self.assertGreater(len(promoted), 0)
        self.assertTrue(all(x.get("inventory_verified") is not True for x in promoted))
        self.assertEqual(12, int(payload.get("registry_purchase_game_count") or 0))
        self.assertTrue(any(x.get("type") == "map" for x in promoted))

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_js_syntax(self):
        for path in ("ui_app_shell_v272.js", "tcg_registry_ui_v469.js"):
            subprocess.run(["node", "--check", str(ROOT / path)], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
