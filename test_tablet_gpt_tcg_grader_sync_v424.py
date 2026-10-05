#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import purchase_intelligence
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v424_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V424.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v424_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v424.json"
BASE_SHA = "58cd34422347584d091c8c22ba9b44e0bd8a8b87"
CANDIDATE_SHA = "e9a0bb5868ececa74dc39e747f3097fb3682a6d4"
LESSON_ID = "TABLET-GPT-VERIFIED-MARKET-WATCH-EXPANSION-V424"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV424Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        contract, delta, receipt = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V423.json",
            contract["prior_contract"],
        )
        self.assertEqual(BASE_SHA, delta["source_main_sha"])
        self.assertEqual(BASE_SHA, receipt["source_main_sha"])
        self.assertEqual(delta["lesson_digest_sha256"], digest(delta["lessons"]))
        self.assertEqual(delta["lesson_digest_sha256"], receipt["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], receipt["accepted_lesson_ids"])
        self.assertEqual(115, contract["prior_required_lesson_count"])
        self.assertEqual(1, contract["delta_required_lesson_count"])
        self.assertEqual(116, contract["current_required_lesson_count"])
        self.assertIn(449, contract["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])

    def test_candidate_exactly_covers_registry_watch_expansion(self):
        contract = load(CONTRACT)
        sync = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, sync["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, sync["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, sync["functional_candidate_commit"])
        self.assertEqual(["tcg_game_registry.json"], sync["watched_paths"])
        assert_v424_successor(self)

    def test_new_verified_market_candidates_start_watch_and_are_not_live_purchase(self):
        data = registry.load_registry(ROOT)
        expected = {
            "cookierun-braverse": ("CookieRun: Braverse TCG", 2104, "쿠키런 브레이버스 TCG"),
            "universus": ("UniVersus", 8422, "유니버서스 CCG"),
        }
        for game_id, (canonical, depth, alias) in expected.items():
            row = next(item for item in data["games"] if item["id"] == game_id)
            self.assertEqual("watch", row["state"])
            self.assertEqual(0.0, row["activation_score"])
            self.assertEqual(depth, row["evidence"]["marketplace_catalog_count"])
            self.assertTrue(row["evidence"]["official_live"])
            self.assertTrue(row["evidence"]["organized_play"])
            self.assertTrue(row["evidence"]["collector_rarity_signal"])
            self.assertFalse(row["capabilities"]["grading"])
            self.assertEqual(canonical, registry.canonical_game(alias, root=ROOT))
            value, terms = purchase_intelligence._resolve_purchase_game(alias)
            self.assertIsNone(value)
            self.assertEqual("", terms)

    def test_verified_review_can_promote_market_category_without_enabling_grading(self):
        result = registry.review_registry(
            ROOT,
            now=registry.dt.datetime(2026, 10, 5, 3, 0, tzinfo=registry.dt.timezone.utc),
            persist=False,
        )
        checked = {item["canonical"]: item for item in result["reviewed"]}
        for canonical in ("CookieRun: Braverse TCG", "UniVersus"):
            self.assertIn(canonical, checked)
            self.assertTrue(checked[canonical]["eligible"])
            self.assertEqual("promoted", checked[canonical]["state"])
            self.assertGreaterEqual(
                checked[canonical]["evidence_activation_score"],
                result["min_auto_promotion_score"],
            )
        self.assertFalse(result["profit_guaranteed"])
        self.assertFalse(result["market_direction_inferred"])

    def test_core_neural_grading_and_collection_safety_unchanged(self):
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
