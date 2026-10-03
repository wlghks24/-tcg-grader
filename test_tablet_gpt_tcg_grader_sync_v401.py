import hashlib
import json
import unittest
from pathlib import Path

import screen_policy_neural_v401 as screen_neural
import tablet_autonomous_evolution_v400 as autonomy
import tablet_runtime_manifest
from sync_v376_successor_test_support import assert_v401_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V401.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v401_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v401.json"
BASE_SHA = "ff04ecb767d98df886719573ac6d65bb4f452203"
CANDIDATE_SHA = "361812899a42c1b588d015187402234369562d52"
LESSON_ID = "TABLET-GPT-DEDICATED-SCREEN-NEURAL-V401"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV401Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_merge_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V400.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v400_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(93, c["prior_required_lesson_count"])
        self.assertEqual(94, c["current_required_lesson_count"])
        self.assertEqual(412, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_dedicated_screen_neural_contract_is_exact_and_bounded(self):
        c = load(CONTRACT)
        for key in (
            "dedicated_screen_neural_required",
            "screen_neural_architecture_17_12_18_required",
            "screen_neural_exact_feature_allowlist_required",
            "screen_neural_verified_surface_outcomes_only_required",
            "screen_neural_minimum_sample_gate_required",
            "screen_neural_confidence_gate_required",
            "screen_neural_feature_bias_bounded_required",
            "screen_neural_total_policy_bias_bounded_required",
            "screen_neural_transactional_persistence_required",
            "screen_neural_corruption_isolation_required",
            "screen_neural_user_behavior_tracking_forbidden",
            "screen_neural_market_direction_invention_forbidden",
            "screen_neural_runtime_manifest_binding_required",
            "screen_neural_source_generation_forbidden",
            "legacy_sync_prefix_collision_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        self.assertIn("screen_policy_neural_v401.py", c["freshness_watch"]["exact_paths"])
        self.assertEqual(17, screen_neural.INPUT_DIM)
        self.assertEqual(12, screen_neural.HIDDEN_DIM)
        self.assertEqual(18, len(screen_neural.FEATURE_KEYS))
        self.assertEqual(12, screen_neural.MIN_TRAINING_ROWS)
        self.assertEqual(0.55, screen_neural.MIN_VERIFIED_CONFIDENCE)
        self.assertEqual(0.05, screen_neural.MAX_FEATURE_BIAS)
        self.assertEqual(0.08, autonomy.MAX_COMBINED_FEATURE_BIAS)
        self.assertEqual(set(autonomy.FEATURE_TARGETS), set(screen_neural.FEATURE_KEYS))

    def test_runtime_bundle_and_safety_keep_neural_fail_closed(self):
        self.assertIn("screen_policy_neural_v401.py", tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_adapter_enabled"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_verified_outcomes_only"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_allowlisted_features_only"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_advisory_only"])
        self.assertFalse(autonomy.SAFETY["screen_policy_neural_user_behavior_tracking"])
        self.assertFalse(autonomy.SAFETY["screen_policy_neural_source_generation"])
        self.assertFalse(screen_neural.SAFETY["source_code_generation"])
        self.assertFalse(screen_neural.SAFETY["git_write"])
        self.assertFalse(screen_neural.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_dedicated_screen_neural_runtime(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["screen_policy_neural_v401.py","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.js","tablet_runtime_manifest.py"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v401_successor(self)

    def test_receipt_preserves_physical_device_boundary(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["screen_neural_verified_surface_outcomes_only"])
        self.assertTrue(r["alignment_policy"]["screen_neural_confidence_gate_required"])
        self.assertFalse(r["alignment_policy"]["screen_neural_user_behavior_tracking"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
