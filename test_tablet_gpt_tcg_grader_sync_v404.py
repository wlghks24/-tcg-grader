import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v404_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V404.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v404_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v404.json"
BASE_SHA = "0f2621f27a2206d487167e9ec4c9ca67d70404d3"
CANDIDATE_SHA = "307ddca680441f0263bfcf52a3521fa5da84def1"
LESSON_ID = "TABLET-GPT-VIDEO-UX-REFINEMENT-V404"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV404Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_merge_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V403.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v403_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(96, c["prior_required_lesson_count"])
        self.assertEqual(97, c["current_required_lesson_count"])
        self.assertIn(416, c["current_required_merge_prs"])
        self.assertIn(417, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v404_video_refinement_contract_is_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "video_reference_v404_two_stage_region_required",
            "video_reference_v404_region_strings_only_required",
            "video_reference_v404_precise_location_persistence_forbidden",
            "video_reference_v404_capture_readiness_required",
            "video_reference_v404_post_capture_glare_recheck_required",
            "video_reference_v404_hot_evidence_confidence_required",
            "video_reference_v404_market_direction_invention_forbidden",
            "video_reference_v404_portfolio_existing_economics_only_required",
            "video_reference_v404_module_confidence_required",
            "video_reference_v404_low_confidence_revalidation_required",
            "video_reference_v404_experience_provenance_history_required",
            "video_reference_v404_user_behavior_tracking_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        self.assertTrue(autonomy.SAFETY["video_reference_experience_module_confidence_required"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_low_confidence_revalidation_required"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_region_drilldown_strings_only"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_capture_readiness_structured"])
        self.assertTrue(autonomy.SAFETY["video_reference_experience_portfolio_economics_existing_results_only"])

    def test_candidate_exactly_covers_v404_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.css","tablet_autonomy_dashboard_v400.js"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v404_successor(self)

    def test_receipt_preserves_location_behavior_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertFalse(r["alignment_policy"]["video_reference_v404_precise_location_persistence"])
        self.assertTrue(r["alignment_policy"]["video_reference_v404_hot_evidence_confidence_required"])
        self.assertTrue(r["alignment_policy"]["video_reference_v404_portfolio_existing_economics_only"])
        self.assertFalse(r["alignment_policy"]["video_reference_v404_user_behavior_tracking"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
