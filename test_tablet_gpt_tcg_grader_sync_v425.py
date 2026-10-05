#!/usr/bin/env python3
import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v425_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V425.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v425_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v425.json"
BASE_SHA = "b0e0a483dee0a77cc054e978b83a83e09323d6b0"
CANDIDATE_SHA = "3b3f2c01e34e96fb05193cb62c44963ad45ef09f"
LESSON_IDS = ["TABLET-GPT-EMERGING-MARKET-ATTENTION-V425","TABLET-GPT-FOW-METAZOO-VERIFIED-WATCH-V425"]
NOW = datetime(2026, 10, 5, 3, 30, tzinfo=timezone.utc)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV425Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        contract, delta, receipt = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V424.json",
            contract["prior_contract"],
        )
        self.assertEqual(BASE_SHA, delta["source_main_sha"])
        self.assertEqual(BASE_SHA, receipt["source_main_sha"])
        self.assertEqual(delta["lesson_digest_sha256"], digest(delta["lessons"]))
        self.assertEqual(delta["lesson_digest_sha256"], receipt["delta_lesson_digest_sha256"])
        self.assertEqual(LESSON_IDS, receipt["accepted_lesson_ids"])
        self.assertEqual(116, contract["prior_required_lesson_count"])
        self.assertEqual(2, contract["delta_required_lesson_count"])
        self.assertEqual(118, contract["current_required_lesson_count"])
        self.assertIn(450, contract["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])

    def test_candidate_exactly_covers_emerging_market_runtime_paths(self):
        contract = load(CONTRACT)
        sync = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, sync["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, sync["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, sync["functional_candidate_commit"])
        self.assertEqual(
            ["tablet_autonomous_evolution_v400.py", "tablet_autonomy_dashboard_v400.js", "tcg_game_registry.json"],
            sync["watched_paths"],
        )
        assert_v425_successor(self)

    def test_force_of_will_and_metazoo_are_verified_watch_not_grading_games(self):
        data = registry.load_registry(ROOT)
        expected = {
            "force-of-will": ("Force of Will", 11216, "포스 오브 윌 TCG"),
            "metazoo": ("MetaZoo", 3456, "메타주 TCG"),
        }
        for game_id, (canonical, depth, alias) in expected.items():
            row = next(item for item in data["games"] if item["id"] == game_id)
            self.assertEqual("watch", row["state"])
            self.assertEqual(0.0, row["activation_score"])
            self.assertEqual(depth, row["evidence"]["marketplace_catalog_count"])
            self.assertTrue(row["evidence"]["official_live"])
            self.assertTrue(row["evidence"]["organized_play"])
            self.assertFalse(row["capabilities"]["grading"])
            self.assertEqual(canonical, registry.canonical_game(alias, root=ROOT))
            self.assertNotIn(canonical, registry.enabled_canonicals("market", root=ROOT))

    def test_watch_attention_can_steer_ui_but_cannot_activate_game(self):
        emerging = autonomy.watch_candidate_activity(ROOT, NOW)
        self.assertGreater(emerging["attention"], 0.0)
        self.assertFalse(emerging["auto_promoted"])
        self.assertFalse(emerging["profit_guaranteed"])
        self.assertFalse(emerging["market_direction_inferred"])
        activity = autonomy.market_activity(ROOT, NOW)
        self.assertEqual(emerging["count"], activity["watch_candidate_attention"]["count"])
        self.assertNotIn("Force of Will", activity["market_lens"]["allowed_games"])
        self.assertNotIn("MetaZoo", activity["market_lens"]["allowed_games"])
        self.assertTrue(autonomy.SAFETY["watch_candidate_attention_advisory_only"])
        self.assertTrue(autonomy.SAFETY["watch_candidate_attention_cannot_activate_game"])
        self.assertFalse(autonomy.SAFETY["watch_candidate_attention_profit_prediction"])

    def test_dashboard_ranks_watch_evidence_without_profit_or_price_direction(self):
        js = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        self.assertIn("watchCandidateEvidenceScore", js)
        self.assertIn("검증점수(근거) ", js)
        self.assertIn("scoreDelta", js)
        self.assertNotIn("predictedProfit", js)
        self.assertNotIn("expectedReturn", js)

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
        receipt = load(RECEIPT)
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
