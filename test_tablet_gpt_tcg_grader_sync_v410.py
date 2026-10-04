#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v410_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V410.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v410_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v410.json"
DASHBOARD = ROOT / "tablet_autonomy_dashboard_v400.js"
BASE_SHA = "3b0cdb01cd3083701dda198b1c1642fa43301d89"
CANDIDATE_SHA = "64cfd6393b5c6d7ad51d3a301e1b71ab4a247445"
FUNCTIONAL_CANDIDATE_SHA = "69b5a3e6a94d3b523e54b1c7c4415e993951e0a5"
LESSON_ID = "TABLET-GPT-VERIFIED-MARKET-CONTEXT-UI-POLICY-V410"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV410Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V409.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v409_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(102, c["prior_required_lesson_count"])
        self.assertEqual(103, c["current_required_lesson_count"])
        self.assertIn(424, c["current_required_merge_prs"])
        self.assertIn(425, c["current_required_merge_prs"])
        self.assertIn(427, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v410_contract_is_bounded_and_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "market_context_v410_verified_activity_only_required",
            "market_context_v410_freshness_gate_required",
            "market_context_v410_stale_zero_bias_required",
            "market_context_v410_max_bias_0_04_required",
            "market_context_v410_combined_abs_bias_0_08_required",
            "market_context_v410_state_allowlist_required",
            "market_context_v410_screen_neural_17_12_18_unchanged_required",
            "market_context_v410_user_behavior_tracking_forbidden",
            "market_context_v410_market_direction_invention_forbidden",
            "market_context_v410_price_direction_use_forbidden",
            "market_context_v410_source_auto_rewrite_forbidden",
            "market_context_v410_git_write_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_v410_runtime_policy(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(FUNCTIONAL_CANDIDATE_SHA, candidate["functional_candidate_commit"])
        self.assertEqual("squash_merge_commit", candidate["candidate_commit_kind"])
        self.assertEqual(CANDIDATE_SHA, candidate["reviewed_merge_sha"])
        self.assertEqual(
            ["tablet_autonomous_evolution_v400.py", "tablet_autonomy_dashboard_v400.js"],
            candidate["watched_paths"],
        )
        assert_v410_successor(self)

    def test_runtime_market_context_preserves_neural_and_safety_caps(self):
        self.assertEqual(17, autonomy.screen_neural.INPUT_DIM)
        self.assertEqual(12, autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18, len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertEqual(0.04, autonomy.MAX_MARKET_CONTEXT_BIAS)
        self.assertEqual(0.08, autonomy.MAX_COMBINED_FEATURE_BIAS)
        self.assertTrue(autonomy.SAFETY["market_context_adapter_enabled"])
        self.assertTrue(autonomy.SAFETY["market_context_adapter_verified_activity_only"])
        self.assertTrue(autonomy.SAFETY["market_context_adapter_freshness_gated"])
        self.assertFalse(autonomy.SAFETY["market_context_adapter_market_direction_invention"])
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("marketContext", dashboard)
        self.assertIn("검증 시장 컨텍스트 어댑터 최대 +4%", dashboard)
        self.assertNotIn("navigator.sendBeacon", dashboard)
        self.assertNotIn('addEventListener("pointermove"', dashboard)


if __name__ == "__main__":
    unittest.main(verbosity=2)
