import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v403_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V403.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v403_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v403.json"
BASE_SHA = "b3d4c6d4000b5565de80c52294a7efc5b9b5de51"
CANDIDATE_SHA = "501e9bcb34910376937bec35cfefa0a1dfb64722"
LESSON_ID = "TABLET-GPT-VIDEO-REFERENCE-ADAPTIVE-EXPERIENCE-V403"


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

    def test_video_reference_contract_is_allowlisted_verified_and_private(self):
        c = load(CONTRACT)
        for key in (
            "video_reference_five_module_allowlist_required",
            "video_reference_verified_data_only_required",
            "video_reference_market_direction_invention_forbidden",
            "video_reference_stock_fact_invention_forbidden",
            "video_reference_user_reversible_required",
            "video_reference_precise_location_persistence_forbidden",
            "video_reference_user_behavior_tracking_forbidden",
            "video_reference_camera_existing_quality_signals_required",
            "video_reference_purchase_existing_controls_required",
            "video_reference_hot_ranking_freshness_not_direction_required",
            "video_reference_portfolio_current_verified_state_only_required",
            "video_reference_runtime_dom_fail_closed_required",
            "video_reference_runtime_source_generation_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        self.assertEqual(5, len(autonomy.VIDEO_EXPERIENCE_MODULES))
        self.assertEqual(
            {
                "home-market-pulse",
                "capture-quality-gate",
                "purchase-split-view",
                "hot-card-box-ranking",
                "portfolio-summary",
            },
            set(autonomy.VIDEO_EXPERIENCE_MODULES),
        )
        self.assertTrue(autonomy.SAFETY["video_reference_experience_verified_data_only"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_market_direction_invention"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_stock_fact_invention"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_precise_location_persistence"])
        self.assertFalse(autonomy.SAFETY["video_reference_experience_user_behavior_tracking"])

    def test_candidate_exactly_covers_video_reference_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.css","tablet_autonomy_dashboard_v400.js"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v403_successor(self)

    def test_receipt_preserves_physical_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["video_reference_verified_data_only"])
        self.assertFalse(r["alignment_policy"]["video_reference_precise_location_persistence"])
        self.assertFalse(r["alignment_policy"]["video_reference_user_behavior_tracking"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
