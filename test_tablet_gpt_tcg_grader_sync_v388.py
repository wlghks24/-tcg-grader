import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v390 as autonomy
from sync_v376_successor_test_support import assert_v388_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V388.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v388_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v388.json"
BASE_SHA = "d4e4bd16e7e853a53274119f9f10f7a5521b114c"
CANDIDATE_SHA = "3c9a9afa58214f7a67fcfe5373acb7823259684f"
LESSON_ID = "TABLET-GPT-GOAL-DIRECTED-VERIFIED-SELF-IMPROVEMENT-V390"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v390.py", "tablet_runtime_manifest.py"]

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV388Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V387.json",c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v387_delta.json",c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(80,c["prior_required_lesson_count"])
        self.assertEqual(81,c["current_required_lesson_count"])
        self.assertEqual(388,c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v390_rules_preserve_fail_closed_goal_autonomy(self):
        c=load(CONTRACT)
        for key in (
            "goal_directed_self_improvement_required",
            "operational_goal_inputs_only_required",
            "verified_meta_critic_required",
            "meta_critic_new_verified_samples_only_required",
            "unchanged_verified_aggregate_replay_forbidden",
            "mature_critic_required_for_goal_alignment_hold",
            "recovery_action_goal_alignment_hold_forbidden",
            "goal_capability_canonical_allowlist_only_required",
            "goal_capability_v388_preview_gate_required",
            "goal_capability_next_cycle_only_required",
            "source_feature_shadow_canary_pr_pipeline_required",
            "source_feature_runtime_code_generation_forbidden",
            "v388_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key],True,key)
        self.assertTrue(autonomy.SAFETY["goal_directed_self_improvement"])
        self.assertTrue(autonomy.SAFETY["verified_meta_critic_training_only"])
        self.assertTrue(autonomy.SAFETY["goal_capability_canonical_allowlist_only"])
        self.assertTrue(autonomy.SAFETY["source_feature_plan_non_executable"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_v390_runtime_route(self):
        c=load(CONTRACT)
        candidate=c["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED,candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v388_successor(self)

    def test_main_and_runtime_manifest_use_v390(self):
        main=(ROOT/"main").read_text(encoding="utf-8")
        manifest=(ROOT/"tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v391.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        for version in ("v391", "v390","v388","v387","v386","v385","v382","v381","v380","v379","v378","v377","v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"',manifest)

    def test_receipt_preserves_device_and_source_boundaries(self):
        r=load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["meta_critic_new_verified_samples_only"])
        self.assertTrue(r["alignment_policy"]["goal_capability_v388_preview_gate_required"])
        self.assertFalse(r["alignment_policy"]["source_feature_runtime_code_generation"])

if __name__=="__main__":
    unittest.main(verbosity=2)
