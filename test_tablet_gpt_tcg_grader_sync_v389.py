import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v391 as autonomy
from sync_v376_successor_test_support import assert_v389_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V389.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v389_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v389.json"
BASE_SHA = "d450fd918ebb2ed25adb49e2cbb14a4b14f6dadc"
CANDIDATE_SHA = "fe3e8e00f3ed5293c6d4a3834e3a6b539891a829"
LESSON_ID = "TABLET-GPT-SELF-DIAGNOSING-VERIFIED-ADAPTIVE-EVOLUTION-V391"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v391.py", "tablet_runtime_manifest.py"]

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV389Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V388.json",c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v388_delta.json",c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(81,c["prior_required_lesson_count"])
        self.assertEqual(82,c["current_required_lesson_count"])
        self.assertEqual(395,c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v391_rules_preserve_fail_closed_self_evolution(self):
        c=load(CONTRACT)
        for key in (
            "self_diagnosis_operational_evidence_only_required",
            "persistent_fault_streak_learning_required",
            "deterministic_counterfactual_decision_stress_test_required",
            "counterfactual_stress_test_cannot_override_recovery_required",
            "verified_non_recovery_regression_hold_required",
            "recovery_regression_observe_only_required",
            "source_feature_lifecycle_non_executable_required",
            "source_feature_lifecycle_rework_on_regression_required",
            "runtime_self_extension_remains_v390_canonical_allowlist_required",
            "v390_gate_cannot_be_bypassed",
            "v388_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key],True,key)
        self.assertTrue(autonomy.SAFETY["self_diagnosis_enabled"])
        self.assertTrue(autonomy.SAFETY["counterfactual_decision_stress_test_enabled"])
        self.assertTrue(autonomy.SAFETY["verified_regression_guard_enabled"])
        self.assertTrue(autonomy.SAFETY["feature_lifecycle_planner_enabled"])
        self.assertTrue(autonomy.SAFETY["v390_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_v391_runtime_route(self):
        c=load(CONTRACT)
        candidate=c["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED,candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v389_successor(self)

    def test_main_and_runtime_manifest_use_v391(self):
        main=(ROOT/"main").read_text(encoding="utf-8")
        manifest=(ROOT/"tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v397.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        for version in ("v397", "v391","v390","v388","v387","v386","v385","v382","v381","v380","v379","v378","v377","v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"',manifest)

    def test_receipt_preserves_device_and_source_boundaries(self):
        r=load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["self_diagnosis_operational_evidence_only"])
        self.assertTrue(r["alignment_policy"]["counterfactual_decision_stress_test_deterministic"])
        self.assertTrue(r["alignment_policy"]["verified_non_recovery_regression_hold"])
        self.assertTrue(r["alignment_policy"]["recovery_regression_observe_only"])
        self.assertFalse(r["alignment_policy"]["source_feature_runtime_code_generation"])

if __name__=="__main__":
    unittest.main(verbosity=2)
