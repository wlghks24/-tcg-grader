import hashlib
import json
import unittest
from pathlib import Path

import screen_policy_neural_v401 as neural
import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v402_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V402.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v402_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v402.json"
BASE_SHA = "221dd2ca754291c878eb894292687146e16a6fb1"
CANDIDATE_SHA = "1884da614f74075c421a8c36bf2f0f22a89ef762"
LESSON_ID = "TABLET-GPT-SCREEN-NEURAL-CHAMPION-CHALLENGER-V402"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV402Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_merge_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V401.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v401_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(94, c["prior_required_lesson_count"])
        self.assertEqual(95, c["current_required_lesson_count"])
        self.assertEqual(413, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_champion_challenger_contract_is_exact_and_bounded(self):
        c = load(CONTRACT)
        for key in (
            "screen_neural_champion_challenger_required",
            "screen_neural_chronological_holdout_required",
            "screen_neural_minimum_train_holdout_gate_required",
            "screen_neural_challenger_improvement_required",
            "screen_neural_holdout_loss_cap_required",
            "screen_neural_input_drift_hold_required",
            "screen_neural_last_good_backup_required",
            "screen_neural_transactional_promotion_required",
            "screen_neural_backup_recovery_required",
            "screen_neural_rejected_challenger_cannot_replace_champion",
        ):
            self.assertIs(c["rules"][key], True, key)
        self.assertEqual(12, neural.MIN_TRAINING_ROWS)
        self.assertEqual(4, neural.MIN_HOLDOUT_ROWS)
        self.assertEqual(16, neural.MIN_PROMOTION_ROWS)
        self.assertEqual(0.0005, neural.MIN_PROMOTION_IMPROVEMENT)
        self.assertEqual(0.45, neural.MAX_HOLDOUT_LOSS)
        self.assertEqual(0.30, neural.MAX_INPUT_DRIFT)
        self.assertEqual(0.05, neural.MAX_FEATURE_BIAS)
        self.assertEqual(0.08, autonomy.MAX_COMBINED_FEATURE_BIAS)

    def test_runtime_safety_requires_holdout_backup_and_no_self_modification(self):
        self.assertTrue(neural.SAFETY["champion_challenger_required"])
        self.assertTrue(neural.SAFETY["holdout_validation_required"])
        self.assertTrue(neural.SAFETY["challenger_must_improve"])
        self.assertTrue(neural.SAFETY["input_drift_hold_required"])
        self.assertTrue(neural.SAFETY["backup_rollback_required"])
        self.assertTrue(neural.SAFETY["promotion_transactional"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_champion_challenger_required"])
        self.assertTrue(autonomy.SAFETY["screen_policy_neural_backup_rollback_required"])
        self.assertFalse(neural.SAFETY["user_behavior_tracking"])
        self.assertFalse(neural.SAFETY["source_code_generation"])
        self.assertFalse(neural.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])

    def test_candidate_exactly_covers_model_governance_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["screen_policy_neural_v401.py","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.js"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v402_successor(self)

    def test_receipt_preserves_physical_device_boundary(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["screen_neural_champion_challenger_required"])
        self.assertTrue(r["alignment_policy"]["screen_neural_backup_recovery_required"])
        self.assertFalse(r["alignment_policy"]["user_behavior_tracking"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
