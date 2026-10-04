import hashlib
import json
import re
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v407_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V407.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v407_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v407.json"
NAV = ROOT / "feature_category_nav.js"
DASHBOARD = ROOT / "tablet_autonomy_dashboard_v400.js"
BASE_SHA = "7e4665bdc7b4737fa4aff8af8f2b52e09d646b77"
FUNCTIONAL_CANDIDATE_SHA = "894e0342fe605d04d8de59f86d5144774dcbce39"
CANDIDATE_SHA = "83ed83788bf774c5f755da3490d982115a5c4277"
LESSON_ID = "TABLET-GPT-VIDEO-NEURAL-ADAPTIVE-DOCK-V407"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV407Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_merge_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V406.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v406_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(99, c["prior_required_lesson_count"])
        self.assertEqual(100, c["current_required_lesson_count"])
        self.assertIn(420, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v407_contract_is_bounded_and_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "video_neural_dock_v407_five_slots_required",
            "video_neural_dock_v407_fixed_home_required",
            "video_neural_dock_v407_fixed_center_capture_required",
            "video_neural_dock_v407_exact_eighteen_feature_allowlist_required",
            "video_neural_dock_v407_verified_screen_ranking_only_required",
            "video_neural_dock_v407_unique_existing_targets_required",
            "video_neural_dock_v407_invalid_plan_fail_closed_required",
            "video_neural_dock_v407_user_reversible_required",
            "video_neural_dock_v407_user_behavior_tracking_forbidden",
            "video_neural_dock_v407_arbitrary_target_or_command_forbidden",
            "video_neural_dock_v407_source_auto_rewrite_forbidden",
            "video_neural_dock_v407_git_write_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_video_neural_dock_runtime(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(FUNCTIONAL_CANDIDATE_SHA, candidate["functional_candidate_commit"])
        self.assertEqual(CANDIDATE_SHA, candidate["post_merge_commit"])
        self.assertEqual("reviewed_squash_merge", candidate["candidate_commit_kind"])
        self.assertEqual(
            ["feature_category_nav.js", "tablet_autonomy_dashboard_v400.js"],
            candidate["watched_paths"],
        )
        assert_v407_successor(self)

    def test_dock_matches_exact_existing_feature_allowlist_and_neural_plan(self):
        nav = NAV.read_text(encoding="utf-8")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        block = nav.split("const ADAPTIVE_DOCK_FEATURES = Object.freeze({", 1)[1].split("\n  });", 1)[0]
        keys = set(re.findall(r'^\s+"([^"]+)":Object\.freeze\(', block, flags=re.MULTILINE))
        expected = {
            key
            for category in autonomy.CATEGORY_ORDER
            for key in autonomy.FEATURE_SHORTCUT_ORDER[category]
        }
        self.assertEqual(expected, keys)
        self.assertEqual(18, len(keys))
        self.assertIn("repeat(5,minmax(0,1fr))", nav)
        self.assertIn("FIXED_DOCK_PRIMARY", nav)
        self.assertIn("chosen.length !== 3", nav)
        self.assertIn("screen_module_plan.rankings.map", dashboard)
        self.assertIn("TCGFeatureCategoryNav?.applyAdaptiveDock", dashboard)

    def test_receipt_preserves_device_source_and_privacy_boundaries(self):
        r = load(RECEIPT)
        self.assertTrue(r["verification"]["uploaded_video_frame_review_verified"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertFalse(r["alignment_policy"]["user_behavior_tracking"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])
        self.assertFalse(r["alignment_policy"]["runtime_ui_source_auto_rewrite"])
        self.assertFalse(r["alignment_policy"]["git_write"])
        self.assertFalse(r["alignment_policy"]["arbitrary_command_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
