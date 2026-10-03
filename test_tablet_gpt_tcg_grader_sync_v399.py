import hashlib
import json
import re
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v399_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V399.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v399_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v399.json"
BASE_SHA = "866de4ee12382fd7767e0d939b1e154aa0c0cd03"
CANDIDATE_SHA = "b054c580f895c08d26c38f799b83babbfbcf9beb"
LESSON_ID = "TABLET-GPT-FULL-SCREEN-AUTONOMY-V399"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV399Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V398.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v398_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(91, c["prior_required_lesson_count"])
        self.assertEqual(92, c["current_required_lesson_count"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_full_screen_and_needed_feature_rules_are_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "all_18_feature_priority_scoring_required",
            "full_screen_existing_target_priority_required",
            "screen_module_allowlist_exact_required",
            "screen_module_dom_reorder_forbidden",
            "screen_module_user_restore_required",
            "target_binding_runtime_health_fail_closed_required",
            "needed_feature_specific_selection_required",
            "needed_feature_protected_pr_ci_required",
            "needed_feature_runtime_source_generation_forbidden",
            "module_focus_market_activity_nondirectional_required",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_all_feature_targets_are_existing_and_exact(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        pairs = re.findall(r'class="feature-shortcut" href="#([^"]+)" data-feature-key="([^"]+)"', html)
        self.assertEqual(18, len(pairs))
        self.assertEqual(dict(autonomy.FEATURE_TARGETS), {feature: target for target, feature in pairs})
        ids = set(re.findall(r'\bid="([^"]+)"', html))
        self.assertTrue(set(autonomy.FEATURE_TARGETS.values()).issubset(ids))
        self.assertEqual(18, len(autonomy.FEATURE_TARGETS))
        self.assertEqual(set(autonomy.SURFACES), set(autonomy.FEATURE_GAP_RECIPES))
        self.assertEqual(7, len(set(autonomy.FEATURE_GAP_RECIPES.values())))

    def test_candidate_exactly_covers_full_screen_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.css","tablet_autonomy_dashboard_v400.js"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v399_successor(self)

    def test_receipt_preserves_physical_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["full_screen_existing_targets_only"])
        self.assertTrue(r["alignment_policy"]["needed_feature_protected_pr_ci_required"])
        self.assertFalse(r["alignment_policy"]["needed_feature_runtime_source_generation"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
