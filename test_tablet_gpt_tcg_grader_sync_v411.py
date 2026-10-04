#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v411_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V411.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v411_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v411.json"
DASHBOARD = ROOT / "tablet_autonomy_dashboard_v400.js"
BASE_SHA = "820d874a509affa488bfa0468ba9cefa65d8b226"
CANDIDATE_SHA = "fb42766e7c4ee22ce3f8382329f92294867b430a"
LESSON_ID = "TABLET-GPT-STABLE-MARKET-CONTEXT-HYSTERESIS-V411"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV411Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V410.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v410_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(103, c["prior_required_lesson_count"])
        self.assertEqual(104, c["current_required_lesson_count"])
        self.assertIn(427, c["current_required_merge_prs"])
        self.assertIn(428, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v411_contract_is_bounded_and_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "market_context_v411_history_hysteresis_required",
            "market_context_v411_history_window_5_required",
            "market_context_v411_min_confirmations_2_required",
            "market_context_v411_confidence_floor_0_45_required",
            "market_context_v411_first_seen_fail_closed_all_required",
            "market_context_v411_changed_focus_reconfirmation_required",
            "market_context_v411_stable_experience_bonus_max_0_03_required",
            "market_context_v411_screen_neural_17_12_18_unchanged_required",
            "market_context_v411_user_override_immediate_reversible_required",
            "market_context_v411_user_behavior_tracking_forbidden",
            "market_context_v411_market_direction_invention_forbidden",
            "market_context_v411_price_direction_use_forbidden",
            "market_context_v411_source_auto_rewrite_forbidden",
            "market_context_v411_git_write_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_v411_runtime_policy(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, candidate["functional_candidate_commit"])
        self.assertEqual(
            ["tablet_autonomous_evolution_v400.py", "tablet_autonomy_dashboard_v400.js"],
            candidate["watched_paths"],
        )
        assert_v411_successor(self)

    def test_runtime_hysteresis_preserves_neural_shape_and_safety(self):
        self.assertEqual(17, autonomy.screen_neural.INPUT_DIM)
        self.assertEqual(12, autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18, len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertEqual(5, autonomy.MARKET_CONTEXT_HISTORY)
        self.assertEqual(2, autonomy.MARKET_CONTEXT_MIN_CONFIRMATIONS)
        self.assertEqual(0.45, autonomy.MIN_STABLE_MARKET_LENS_CONFIDENCE)
        self.assertEqual(0.03, autonomy.MAX_STABLE_MARKET_LENS_BONUS)
        self.assertTrue(autonomy.SAFETY["market_context_history_hysteresis_enabled"])
        self.assertTrue(autonomy.SAFETY["market_context_history_verified_signals_only"])
        self.assertTrue(autonomy.SAFETY["market_context_stable_focus_required_before_experience_bonus"])
        self.assertTrue(autonomy.SAFETY["market_context_screen_neural_input_shape_unchanged"])
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("stable_focus_game", dashboard)
        self.assertIn("stable_focus_region", dashboard)
        self.assertIn("연속확인 ", dashboard)
        self.assertNotIn("navigator.sendBeacon", dashboard)
        self.assertNotIn('addEventListener("pointermove"', dashboard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
