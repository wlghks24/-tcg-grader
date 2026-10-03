import hashlib
import json
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v403_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V403.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v403_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v403.json"
BASE_SHA = "b3d4c6d4000b5565de80c52294a7efc5b9b5de51"
CANDIDATE_SHA = "50bdfc06216399b4c38fe958a4934391002dc2bd"
LESSON_ID = "TABLET-GPT-VIDEO-INFORMED-ADAPTIVE-UI-V403"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV403Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_merge_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V402.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v402_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(95, c["prior_required_lesson_count"])
        self.assertEqual(96, c["current_required_lesson_count"])
        self.assertEqual(414, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_video_informed_ui_rules_preserve_factual_and_privacy_boundaries(self):
        c = load(CONTRACT)
        for key in (
            "video_informed_market_home_required",
            "video_informed_home_uses_existing_neural_plan_required",
            "market_activity_not_direction_required",
            "camera_preflight_existing_runtime_status_required",
            "compact_region_recent_workspace_required",
            "precise_location_explicit_action_only_required",
            "precise_location_persistence_forbidden",
            "purchase_coordinate_distribution_not_road_map_required",
            "portfolio_local_only_required",
            "portfolio_user_entered_prices_only_required",
            "portfolio_network_upload_forbidden",
            "bottom_safe_area_required",
            "video_ui_runtime_delivery_required",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_new_ui_assets_are_explicitly_watched(self):
        c = load(CONTRACT)
        for path in ("video_informed_tablet_ui_v403.css", "video_informed_tablet_ui_v403.js"):
            self.assertIn(path, c["freshness_watch"]["exact_paths"])

    def test_candidate_exactly_covers_video_informed_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["VERIFY_TABLET_FINAL.sh","index.html","sw.js","tablet_runtime_manifest.py","tcg_updater.py","video_informed_tablet_ui_v403.css","video_informed_tablet_ui_v403.js"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v403_successor(self)

    def test_receipt_keeps_physical_device_and_location_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["precise_location_explicit_action_only"])
        self.assertFalse(r["alignment_policy"]["precise_location_persistence"])
        self.assertTrue(r["alignment_policy"]["portfolio_local_only"])
        self.assertFalse(r["alignment_policy"]["portfolio_network_upload"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
