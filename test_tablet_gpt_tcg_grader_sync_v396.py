import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v396_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V396.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v396_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v396.json"
BASE_SHA = "dff6e8be13b6bebc793855a728dcd4328a24dadf"
CANDIDATE_SHA = "cc50e98cafa560168b6231e3507378790aea5f4b"
LESSON_ID = "TABLET-GPT-ADAPTIVE-UI-SEVEN-SURFACE-V396"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV396Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V395.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v395_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(88, c["prior_required_lesson_count"])
        self.assertEqual(89, c["current_required_lesson_count"])
        self.assertEqual(406, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v396_rules_keep_adaptive_ui_bounded_and_reversible(self):
        c = load(CONTRACT)
        for key in (
            "purchase_availability_surface_required",
            "purchase_stock_confirmation_required",
            "tablet_ops_surface_required",
            "adaptive_ui_composition_required",
            "adaptive_ui_allowlisted_categories_only_required",
            "adaptive_ui_user_override_required",
            "adaptive_ui_original_order_restore_required",
            "adaptive_ui_market_activity_non_directional_required",
            "adaptive_ui_source_code_rewrite_forbidden",
            "stock_fact_invention_forbidden",
            "v399_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        self.assertTrue(autonomy.SAFETY["adaptive_ui_composition_enabled"])
        self.assertTrue(autonomy.SAFETY["adaptive_ui_user_override_required"])
        self.assertTrue(autonomy.SAFETY["adaptive_ui_reversible"])
        self.assertFalse(autonomy.SAFETY["stock_fact_invention"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_adaptive_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual([
            "tablet_autonomous_evolution_v400.py",
            "tablet_autonomy_dashboard_v400.css",
            "tablet_autonomy_dashboard_v400.js",
        ], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v396_successor(self)

    def test_receipt_preserves_physical_device_boundary(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["adaptive_ui_user_override_required"])
        self.assertTrue(r["alignment_policy"]["adaptive_ui_original_order_restore_required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
