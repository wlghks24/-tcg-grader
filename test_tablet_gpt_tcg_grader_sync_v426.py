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
CANDIDATE_SHA = "1ad0c21facb403483bd39fd59ae63462290f2afa"
LESSON_IDS = ["TABLET-GPT-REGISTRY-FAIL-CLOSED-V426","TABLET-GPT-METAZOO-VERIFIED-WATCH-V426"]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV426Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        contract, delta, receipt = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V425.json", contract["prior_contract"])
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

    def test_candidate_exactly_covers_v426_registry_and_guard_changes(self):
        sync = load(CONTRACT)["candidate_sync"]
        self.assertEqual(BASE_SHA, sync["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, sync["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, sync["functional_candidate_commit"])
        self.assertEqual([
            ".github/workflows/tcg-autonomy-market-guard-v426.yml",
            "tablet_autonomy_dashboard_v400.js",
            "tcg_game_registry.json",
        ], sync["watched_paths"])
        assert_v426_successor(self)

    def test_browser_registry_policy_is_fail_closed_and_fallback_is_current(self):
        js = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        for token in (
            "v400-video-ux-v426-autonomous-market-guard",
            "policy.investment_return_prediction !== false",
            "policy.category_auto_promotion_requires_verified_evidence !== true",
            "policy.source_code_auto_generation !== false",
            "policy.user_behavior_tracking !== false",
            "policy.grading_requires_separate_calibration !== true",
            'state === "watch" && row.capabilities.grading !== false',
            '["Pokémon","ONE PIECE","NARUTO"].every',
            '"Magic: The Gathering"',
            '"Yu-Gi-Oh!"',
            '"Digimon Card Game"',
        ):
            self.assertIn(token, js)
        guard = (ROOT / ".github/workflows/tcg-autonomy-market-guard-v426.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '17 */6 * * *'", guard)
        self.assertIn("python tablet_autonomous_evolution_v400.py --self-test", guard)
        final_guard = (ROOT / ".github/workflows/final-tablet-guard.yml").read_text(encoding="utf-8")
        self.assertIn("'tcg_game_registry.json'", final_guard)
        self.assertIn("'tablet_autonomy_dashboard_v400.js'", final_guard)

    def test_metazoo_starts_watch_and_live_actions_remain_blocked(self):
        data = registry.load_registry(ROOT)
        row = next(item for item in data["games"] if item["id"] == "metazoo")
        self.assertEqual("watch", row["state"])
        self.assertEqual(0, row["activation_score"])
        self.assertEqual(3456, row["evidence"]["marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["official_live"])
        self.assertTrue(row["evidence"]["organized_play"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertEqual("MetaZoo", registry.canonical_game("메타주 TCG", root=ROOT))
        value, terms = purchase_intelligence._resolve_purchase_game("메타주 TCG")
        self.assertIsNone(value)
        self.assertEqual("", terms)

    def test_global_safety_contract_unchanged(self):
        data = registry.load_registry(ROOT)
        self.assertEqual({"pokemon", "onepiece", "naruto"}, {row["id"] for row in registry.enabled_games("grading", root=ROOT)})
        self.assertEqual(8, JOB_COUNT)
        self.assertEqual(17, autonomy.screen_neural.INPUT_DIM)
        self.assertEqual(12, autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18, len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["investment_return_prediction"])
        self.assertFalse(data["policy"]["market_direction_prediction"])
        self.assertFalse(data["policy"]["source_code_auto_generation"])
        receipt = load(RECEIPT)
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
