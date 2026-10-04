#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import screen_policy_neural_v401 as screen_neural
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v423_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V423.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v423_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v423.json"
BASE_SHA = "419ab6b068cdcdcb8ab771e47e0aab1fdf6b12f1"
CANDIDATE_SHA = "0ba80d955b0e4b704d4cafa387eb13dd62bcbf2c"
LESSON_IDS = [
    "TABLET-GPT-TCG-VERIFIED-ACTIVATION-AUTHORITY-V423",
    "TABLET-GPT-SCREEN-NEURAL-GROUP-HOLDOUT-V423",
]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV423Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        contract, delta, receipt = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V422.json",
            contract["prior_contract"],
        )
        self.assertEqual(BASE_SHA, delta["source_main_sha"])
        self.assertEqual(BASE_SHA, receipt["source_main_sha"])
        self.assertEqual(delta["lesson_digest_sha256"], digest(delta["lessons"]))
        self.assertEqual(delta["lesson_digest_sha256"], receipt["delta_lesson_digest_sha256"])
        self.assertEqual(LESSON_IDS, receipt["accepted_lesson_ids"])
        self.assertEqual(113, contract["prior_required_lesson_count"])
        self.assertEqual(2, contract["delta_required_lesson_count"])
        self.assertEqual(115, contract["current_required_lesson_count"])
        self.assertIn(445, contract["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])

    def test_candidate_exactly_covers_verified_activation_and_neural_holdout(self):
        contract = load(CONTRACT)
        sync = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, sync["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, sync["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, sync["functional_candidate_commit"])
        self.assertEqual(
            ["feature_contract.py", "screen_policy_neural_v401.py", "tcg_game_registry.py"],
            sync["watched_paths"],
        )
        assert_v423_successor(self)

    def test_non_core_activation_is_current_verified_evidence_only(self):
        source = (ROOT / "tcg_game_registry.py").read_text(encoding="utf-8")
        self.assertIn(
            'activation = 1.0 if row["state"] == "core" else evidence_activation',
            source,
        )
        self.assertNotIn("max(seed_activation, evidence_activation)", source)
        self.assertIn("old high score cannot self-reinforce", source)

    def test_screen_neural_holdout_is_evidence_group_isolated(self):
        source = (ROOT / "screen_policy_neural_v401.py").read_text(encoding="utf-8")
        self.assertTrue(screen_neural.SAFETY["group_isolated_holdout_required"])
        self.assertIn("def _evidence_group_key(", source)
        self.assertIn("def _evidence_refs(", source)
        self.assertIn("SCREEN_NEURAL_HOLDOUT_LEAKAGE_HOLD", source)
        self.assertIn("train_refs & holdout_refs", source)

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
