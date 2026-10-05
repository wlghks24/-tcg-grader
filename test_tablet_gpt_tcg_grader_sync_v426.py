#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import purchase_intelligence
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v426_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V426.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v426_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v426.json"
BASE_SHA = "7b73dac4be2f66af1441c4992a029e13dea60bea"
CANDIDATE_SHA = "ff3eec8409c0741d5305a07c9c5f8f898ef0ad7b"
LESSON_IDS = ["TABLET-GPT-REGISTRY-MARKET-LENS-V426", "TABLET-GPT-WIXOSS-VERIFIED-WATCH-V426"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV426Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        contract, delta, receipt = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V425.json",
            contract["prior_contract"],
        )
        self.assertEqual(BASE_SHA, delta["source_main_sha"])
        self.assertEqual(BASE_SHA, receipt["source_main_sha"])
        self.assertEqual(delta["lesson_digest_sha256"], digest(delta["lessons"]))
        self.assertEqual(delta["lesson_digest_sha256"], receipt["delta_lesson_digest_sha256"])
        self.assertEqual(LESSON_IDS, receipt["accepted_lesson_ids"])
        self.assertEqual(118, contract["prior_required_lesson_count"])
        self.assertEqual(2, contract["delta_required_lesson_count"])
        self.assertEqual(120, contract["current_required_lesson_count"])
        self.assertIn(452, contract["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])

    def test_candidate_exactly_covers_registry_market_lens_and_wixoss_watch(self):
        sync = load(CONTRACT)["candidate_sync"]
        self.assertEqual(BASE_SHA, sync["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, sync["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, sync["functional_candidate_commit"])
        self.assertEqual(
            ["tablet_autonomy_dashboard_v400.js", "tcg_game_registry.json"],
            sync["watched_paths"],
        )
        assert_v426_successor(self)

    def test_wixoss_starts_watch_and_live_actions_remain_blocked(self):
        data = registry.load_registry(ROOT)
        row = next(item for item in data["games"] if item["id"] == "wixoss")
        self.assertEqual("watch", row["state"])
        self.assertEqual(0.0, row["activation_score"])
        self.assertEqual(4673, row["evidence"]["marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["official_live"])
        self.assertTrue(row["evidence"]["organized_play"])
        self.assertTrue(row["evidence"]["collector_rarity_signal"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertEqual("WIXOSS", registry.canonical_game("위크로스 TCG", root=ROOT))
        value, terms = purchase_intelligence._resolve_purchase_game("위크로스 TCG")
        self.assertIsNone(value)
        self.assertEqual("", terms)

    def test_market_lens_is_live_registry_driven_and_non_directional(self):
        js = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        for token in (
            "registryMarketLensGames",
            "registryMarketLensLabel",
            "const registryDeclared = registryMarketLensGames()",
            "...reportDeclared, ...registryDeclared",
            "gameRegistryData().catch(() => null)",
            'Object.freeze(["ALL","Pokémon","ONE PIECE","NARUTO"])',
            "시장기회 순",
            "수익예측이 아니라",
        ):
            self.assertIn(token, js)
        updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        self.assertIn("AUTO_INTERVAL_SECONDS=6*60*60", updater)
        self.assertNotIn("expected_return", js)
        self.assertIn("price_direction_used", js)

    def test_global_safety_contract_unchanged(self):
        data = registry.load_registry(ROOT)
        self.assertEqual(
            {"pokemon", "onepiece", "naruto"},
            {row["id"] for row in registry.enabled_games("grading", root=ROOT)},
        )
        self.assertEqual(8, JOB_COUNT)
        self.assertEqual(17, autonomy.screen_neural.INPUT_DIM)
        self.assertEqual(12, autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18, len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["investment_return_prediction"])
        self.assertFalse(data["policy"]["market_direction_prediction"])
        self.assertTrue(data["policy"]["grading_requires_separate_calibration"])
        receipt = load(RECEIPT)
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
