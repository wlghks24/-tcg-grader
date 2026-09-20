#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
from urllib.parse import urlparse

import update_market_prices_parallel_v260 as market

ROOT = Path(__file__).resolve().parent


class MarketSourceHubV268Tests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(row) for row in market.MARKET_REFERENCE_SOURCES]
        self.by_id = {row["id"]: row for row in self.rows}

    def test_registry_has_domestic_japan_global_and_europe_coverage(self):
        self.assertGreaterEqual(len(self.rows), 19)
        self.assertEqual(len(self.by_id), len(self.rows))
        self.assertTrue({"KR", "JP", "US_GLOBAL", "EU"}.issubset({row["region"] for row in self.rows}))
        required = {
            "collectory", "joongna", "kream", "bunjang", "daangn", "wyyyes",
            "yahoo_auction_jp", "mercari_jp", "snkrdunk", "ebay_sold",
            "tcgplayer", "pricecharting", "130point", "psa_apr", "cardmarket",
            "collectr", "card_ladder", "tcgfish", "pokevalues_jp",
        }
        self.assertTrue(required.issubset(self.by_id))

    def test_reference_urls_are_https_and_templates_are_navigation_only(self):
        for row in self.rows:
            self.assertEqual(urlparse(row["url"]).scheme, "https", row["id"])
            template = row.get("search_url_template") or ""
            if template:
                self.assertEqual(urlparse(template.replace("{query}", "pikachu")).scheme, "https", row["id"])
                self.assertIn("{query}", template)
        self.assertFalse(any("api_key" in str(row).lower() or "token=" in str(row).lower() for row in self.rows))

    def test_evidence_semantics_do_not_promote_active_listings_to_sales(self):
        for source_id in ("bunjang", "daangn", "mercari_jp", "cardmarket"):
            self.assertEqual(self.by_id[source_id]["evidence_group"], "asking")
        for source_id in ("yahoo_auction_jp", "ebay_sold", "130point", "psa_apr"):
            self.assertEqual(self.by_id[source_id]["evidence_group"], "sold")
        for source_id in (
            "tcgplayer", "pricecharting", "snkrdunk", "collectr",
            "card_ladder", "tcgfish", "pokevalues_jp",
        ):
            self.assertEqual(self.by_id[source_id]["evidence_group"], "guide")
        self.assertEqual(self.by_id["joongna"]["evidence_group"], "mixed")
        self.assertIn("체결가로 자동 간주하지 않음", self.by_id["bunjang"]["note"])
        self.assertIn("체결가로 간주하지 않음", self.by_id["mercari_jp"]["note"])

    def test_new_global_sources_keep_navigation_only_boundary(self):
        self.assertTrue(self.by_id["collectr"]["recommended"])
        self.assertTrue(self.by_id["card_ladder"]["recommended"])
        self.assertEqual(self.by_id["tcgfish"]["games"], ["Pokémon"])
        self.assertEqual(self.by_id["pokevalues_jp"]["region"], "JP")
        for source_id in ("collectr", "card_ladder", "tcgfish", "pokevalues_jp"):
            self.assertFalse(self.by_id[source_id]["auto_collected"])

    def test_registry_attachment_adds_no_network_collection(self):
        db = {}
        count = market._attach_reference_sources(db)
        self.assertEqual(count, len(self.rows))
        self.assertEqual(db["market_reference_schema_version"], 1)
        self.assertEqual(len(db["market_reference_sources"]), count)
        policy = db["market_reference_policy"]
        self.assertTrue(policy["navigation_only"])
        self.assertFalse(policy["new_scrapers_added"])
        self.assertFalse(policy["login_or_private_api_bypass"])
        self.assertTrue(policy["asking_price_is_not_completed_sale"])

    def test_ui_is_easy_to_filter_and_builds_encoded_card_search_links(self):
        flow = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        css = (ROOT / "grade_market_flow.css").read_text(encoding="utf-8")
        for label in ("⭐ 핵심", "🇰🇷 국내", "🇯🇵 일본", "🌎 미국·글로벌", "🇪🇺 유럽", "쉽게 보는 순서"):
            self.assertIn(label, flow)
        for source_name in ("Collectr", "Card Ladder", "TCGFish", "PokeValues Japanese"):
            self.assertIn(source_name, flow)
        self.assertIn("encodeURIComponent(query)", flow)
        self.assertIn("REFERENCE_HOSTS", flow)
        self.assertIn("이 카드 검색", flow)
        self.assertIn("체결·낙찰", flow)
        self.assertIn("판매중 호가", flow)
        self.assertIn("최소 2~3곳을 교차확인", flow)
        self.assertIn("agm-source-grid", css)
        self.assertIn("agm-evidence-sold", css)
        self.assertIn("agm-evidence-asking", css)
        self.assertIn("min-height:40px", css)

    def test_wyyyes_safety_boundary_and_tablet_css_delivery_remain_fail_closed(self):
        wrapper = (ROOT / "update_market_prices_parallel_v260.py").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn('"asking_price_is_not_completed_sale": True', wrapper)
        self.assertIn('"canonical_market_price_overwrite": False', wrapper)
        self.assertIn('"market_reference_network_calls_added": 0', wrapper)
        self.assertIn('"grade_market_flow.js","grade_market_flow.css"', manifest)


if __name__ == "__main__":
    unittest.main()
