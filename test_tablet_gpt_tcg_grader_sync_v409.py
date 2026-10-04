#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v409_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V409.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v409_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v409.json"
DASHBOARD = ROOT / "tablet_autonomy_dashboard_v400.js"
BASE_SHA = "53a6aef86cb900ef06bdc920a59bd7a9e0e4ff75"
CANDIDATE_SHA = "b26d82335e9ec4ec260ed4de5656543531e0731a"
LESSON_ID = "TABLET-GPT-MARKET-LENS-CLAIM-TOPK-HARDENING-V409"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV409Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V408.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v408_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(101, c["prior_required_lesson_count"])
        self.assertEqual(102, c["current_required_lesson_count"])
        self.assertIn(423, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v409_contract_is_bounded_and_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "market_lens_v409_claim_deadline_after_event_end_required",
            "market_lens_v409_all_operational_deadlines_expired_excluded_required",
            "market_lens_v409_tracking_placeholders_excluded_required",
            "market_lens_v409_filter_before_hot_topk_required",
            "market_lens_v409_candidate_scan_bounded_required",
            "market_lens_v409_exact_game_region_allowlist_unchanged_required",
            "market_lens_v409_screen_neural_governance_unchanged_required",
            "market_lens_v409_user_behavior_tracking_forbidden",
            "market_lens_v409_market_direction_invention_forbidden",
            "market_lens_v409_source_auto_rewrite_forbidden",
            "market_lens_v409_git_write_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_v409_runtime_hardening(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(
            ["tablet_autonomous_evolution_v400.py", "tablet_autonomy_dashboard_v400.js"],
            candidate["watched_paths"],
        )
        assert_v409_successor(self)

    def test_runtime_preserves_neural_and_market_safety(self):
        self.assertTrue(autonomy.SAFETY["market_activity_claim_deadline_respected"])
        self.assertTrue(autonomy.SAFETY["market_lens_filter_before_topk_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_challenger_must_improve"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_input_drift_hold_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_backup_rollback_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_transactional_promotion"])
        self.assertFalse(autonomy.SAFETY["screen_policy_neural_source_generation"])
        self.assertEqual(("Pokémon", "ONE PIECE", "NARUTO"), autonomy.MARKET_LENS_GAMES)
        self.assertEqual(("KR", "JP", "US"), autonomy.MARKET_LENS_REGIONS)

        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("const MARKET_LENS_CANDIDATE_LIMIT = 5000", dashboard)
        self.assertIn("watchItems.slice(0, MARKET_LENS_CANDIDATE_LIMIT)", dashboard)
        self.assertIn("priceEntries.slice(0, MARKET_LENS_CANDIDATE_LIMIT)", dashboard)
        self.assertNotIn(".sort((a,b) => b.score - a.score).slice(0,40)", dashboard)
        self.assertNotIn("navigator.sendBeacon", dashboard)
        self.assertNotIn('addEventListener("pointermove"', dashboard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
