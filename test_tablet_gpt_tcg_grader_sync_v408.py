import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v408_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V408.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v408_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v408.json"
DASHBOARD = ROOT / "tablet_autonomy_dashboard_v400.js"
CSS = ROOT / "tablet_autonomy_dashboard_v400.css"
BASE_SHA = "879d131cdf8877870eb4f5c10528a817bdf3b36c"
CANDIDATE_SHA = "7dffbe8311a92fcfb9b77ce5b7bc3e1be2533ccf"
LESSON_ID = "TABLET-GPT-FRESHNESS-AWARE-ADAPTIVE-MARKET-LENS-V408"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV408Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V407.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v407_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(100, c["prior_required_lesson_count"])
        self.assertEqual(101, c["current_required_lesson_count"])
        self.assertIn(421, c["current_required_merge_prs"])
        self.assertIn(422, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v408_contract_is_bounded_and_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "market_lens_v408_dataset_freshness_weighted_required",
            "market_lens_v408_expired_events_excluded_required",
            "market_lens_v408_tracking_placeholders_excluded_required",
            "market_lens_v408_exact_game_allowlist_required",
            "market_lens_v408_exact_region_allowlist_required",
            "market_lens_v408_ambiguous_focus_fail_closed_required",
            "market_lens_v408_user_reversible_required",
            "market_lens_v408_user_behavior_tracking_forbidden",
            "market_lens_v408_market_direction_invention_forbidden",
            "market_lens_v408_price_direction_used_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_market_lens_runtime(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(
            [
                "tablet_autonomous_evolution_v400.py",
                "tablet_autonomy_dashboard_v400.css",
                "tablet_autonomy_dashboard_v400.js",
            ],
            candidate["watched_paths"],
        )
        assert_v408_successor(self)

    def test_market_lens_uses_exact_verified_game_region_allowlists(self):
        self.assertEqual(("Pokémon", "ONE PIECE", "NARUTO"), autonomy.MARKET_LENS_GAMES)
        self.assertEqual(("KR", "JP", "US"), autonomy.MARKET_LENS_REGIONS)
        self.assertTrue(autonomy.SAFETY["market_activity_dataset_freshness_weighted"])
        self.assertTrue(autonomy.SAFETY["market_activity_expired_events_excluded"])
        self.assertTrue(autonomy.SAFETY["market_activity_tracking_placeholders_excluded"])
        self.assertTrue(autonomy.SAFETY["market_lens_verified_rows_only"])
        self.assertTrue(autonomy.SAFETY["market_lens_user_reversible"])
        self.assertFalse(autonomy.SAFETY["market_lens_price_direction_used"])
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        for token in (
            "MARKET_LENS_GAMES",
            "MARKET_LENS_REGIONS",
            "marketLensState",
            "marketLensControls",
            "sessionMarketLensGame",
            "sessionMarketLensRegion",
            "자료 신선도",
            "오래된 데이터셋",
            "price_direction_used",
        ):
            self.assertIn(token, dashboard)
        self.assertIn("V408 freshness-aware verified market lens", css)
        self.assertNotIn("navigator.sendBeacon", dashboard)
        self.assertNotIn('addEventListener("pointermove"', dashboard)
        self.assertNotIn('addEventListener("mousemove"', dashboard)

    def test_receipt_preserves_device_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertTrue(r["verification"]["uploaded_video_frame_review_verified"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertFalse(r["alignment_policy"]["market_direction_inferred"])
        self.assertFalse(r["alignment_policy"]["price_direction_used"])
        self.assertFalse(r["alignment_policy"]["user_behavior_tracking"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])
        self.assertFalse(r["alignment_policy"]["runtime_ui_source_auto_rewrite"])
        self.assertFalse(r["alignment_policy"]["git_write"])
        self.assertFalse(r["alignment_policy"]["arbitrary_command_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
