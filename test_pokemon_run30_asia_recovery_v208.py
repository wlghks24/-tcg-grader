#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import event_gap_learning
import update_promo_events as promo

ROOT = Path(__file__).resolve().parent
CASE_ID = "pokemon-asia-run30-pikachu-promo-2026-09-02"
OFFICIAL_SOURCE = "https://tw.portal-pokemon.com/30th/topics/20260902_02/?lang=en"


class PokemonRun30AsiaRecoveryV208Tests(unittest.TestCase):
    def test_run_and_finisher_promo_terms_are_discoverable(self):
        samples = (
            "Pokémon RUN 30",
            "Pokemon RUN 30 fun run",
            "all participants receive a promo card upon completion",
            "완주자 피카츄 프로모 카드",
            "참가 보상 프로모 카드",
        )
        for value in samples:
            with self.subTest(value=value):
                self.assertIsNotNone(promo.EVENT_WORDS.search(value))

    def test_asia_scope_is_allowed_without_expanding_core_market_regions(self):
        self.assertEqual(("KR", "JP", "US"), promo.CORE_REGIONS)
        self.assertEqual(("KR", "JP", "US"), promo.REGIONS)
        self.assertIn("ASIA", promo.EVENT_REGIONS)
        self.assertIn(("포켓몬 카드", "ASIA"), promo.EVENT_SCOPE_PAIRS)
        self.assertNotIn(("원피스 카드", "ASIA"), promo.EVENT_SCOPE_PAIRS)
        self.assertEqual(
            "ASIA",
            promo.event_region(
                "ASIA",
                "Pokémon RUN 30 Singapore Malaysia Philippines Thailand Indonesia Hong Kong Taiwan",
            ),
        )
        self.assertIsNone(
            promo.event_region("KR", "Pokémon RUN 30 Singapore Malaysia Philippines")
        )

    def test_official_asia_sources_are_allowlisted_and_indexed(self):
        self.assertIn("tw.portal-pokemon.com", promo.ALLOWED)
        self.assertIn("hk.portal-pokemon.com", promo.ALLOWED)
        self.assertIn("pokemongo.com", promo.ALLOWED)
        self.assertTrue(
            any(region == "ASIA" and game == "포켓몬 카드" and "portal-pokemon.com" in url
                for region, game, url in promo.INDEXES)
        )
        self.assertEqual(OFFICIAL_SOURCE, promo.approved_url(OFFICIAL_SOURCE))

    def test_verified_seed_preserves_reward_and_korea_exclusion(self):
        seed = next(
            row for row in promo.OFFICIAL_VERIFIED_SEEDS
            if row.get("source") == OFFICIAL_SOURCE
        )
        self.assertTrue(promo.valid(seed))
        self.assertEqual("ASIA", seed["region"])
        self.assertTrue(seed["reward_watch"])
        self.assertTrue(seed["must_show_candidate"])
        self.assertFalse(seed["korea_included"])
        self.assertEqual(["KR"], seed["excluded_regions"])
        self.assertEqual({"PH", "TW", "SG", "MY", "ID", "TH", "HK"}, set(seed["region_members"]))
        self.assertIn("완주", seed["reward"])
        self.assertIn("Pokémon RUN Pikachu", seed["reward"])

    def test_current_promo_dataset_contains_recovered_event(self):
        payload = json.loads((ROOT / "promo_events.json").read_text(encoding="utf-8"))
        rows = [
            row for row in payload.get("items", [])
            if row.get("source") == OFFICIAL_SOURCE
        ]
        self.assertEqual(1, len(rows))
        self.assertEqual("ASIA", rows[0]["region"])
        self.assertFalse(rows[0]["korea_included"])

    def test_manual_recovery_is_verified_and_teaches_asia_terms(self):
        payload = json.loads((ROOT / "manual_event_evidence.json").read_text(encoding="utf-8"))
        row = next(item for item in payload.get("items", []) if item.get("recovery_case_id") == CASE_ID)
        self.assertTrue(row["verified"])
        self.assertTrue(row["official_domain_match"])
        self.assertEqual("ASIA", row["region"])
        self.assertIn("Pokémon RUN", row["learning_terms"])
        self.assertIn("완주", row["learning_terms"])

        with tempfile.TemporaryDirectory() as td:
            evidence = Path(td) / "evidence.json"
            memory = Path(td) / "learning.json"
            evidence.write_text(json.dumps({"items": [row]}, ensure_ascii=False), encoding="utf-8")
            learner = event_gap_learning.EventGapLearner(memory_path=memory)
            learned = learner.learn_verified_evidence_file(evidence)
            self.assertGreaterEqual(learned, 1)
            asia_terms = [key for key in learner.data.get("terms", {}) if "|ASIA|" in key]
            self.assertTrue(asia_terms)
            self.assertTrue(any("Pokémon RUN" in key or "완주" in key for key in asia_terms))


if __name__ == "__main__":
    unittest.main()
