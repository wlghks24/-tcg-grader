#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import box_hit_market_discovery as box_hit
import runtime_bundle_guard_v143
import tablet_runtime_manifest
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v424_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V424.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v424_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v424.json"
BASE_SHA = "58cd34422347584d091c8c22ba9b44e0bd8a8b87"
CANDIDATE_SHA = "8d2cbcf6f07c22b1910558f3c72f08d229fb6d0f"
LESSON_IDS = ["TABLET-GPT-REGISTRY-BOX-HIT-MARKET-V424"]


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
        self.assertEqual(LESSON_IDS, receipt["accepted_lesson_ids"])
        self.assertEqual(115, contract["prior_required_lesson_count"])
        self.assertEqual(1, contract["delta_required_lesson_count"])
        self.assertEqual(116, contract["current_required_lesson_count"])
        self.assertIn(446, contract["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])

    def test_candidate_exactly_covers_registry_box_hit_surface(self):
        contract = load(CONTRACT)
        sync = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, sync["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, sync["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, sync["functional_candidate_commit"])
        self.assertEqual(
            ["feature_contract.py", "tablet_runtime_manifest.py"],
            sync["watched_paths"],
        )
        assert_v424_successor(self)

    def test_box_hit_market_scope_is_registry_driven_and_watch_safe(self):
        source = (ROOT / "box_hit_market_discovery.py").read_text(encoding="utf-8")
        self.assertIn('tcg_game_registry.enabled_games("market",root=BASE)', source)
        self.assertIn("WATCH remains review-only", source)
        self.assertIn("if game not in CORE_GAME_TERMS:", source)
        self.assertIn("return [base[0]]", source)
        enabled = registry.enabled_games("market", root=ROOT)
        self.assertTrue(all(row["state"] in {"core", "promoted"} for row in enabled))
        self.assertNotIn("Godzilla Card Game", {row["canonical"] for row in enabled if row["state"] == "watch"})

    def test_runtime_delivery_and_global_safety_are_preserved(self):
        self.assertIn("box_hit_market_discovery.py", tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn("box_hit_market_discovery.py", runtime_bundle_guard_v143.REQUIRED_FILES)
        self.assertEqual(8, JOB_COUNT)
        self.assertEqual(
            {"pokemon", "onepiece", "naruto"},
            {row["id"] for row in registry.enabled_games("grading", root=ROOT)},
        )
        data = registry.load_registry(ROOT)
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["investment_return_prediction"])
        self.assertFalse(data["policy"]["market_direction_prediction"])
        receipt = load(RECEIPT)
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
