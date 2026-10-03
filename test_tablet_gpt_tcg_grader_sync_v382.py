import hashlib
import json
import subprocess
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v382 as autonomy
from sync_v376_successor_test_support import V383_WATCHED, V384_WATCHED, V385_WATCHED, V386_WATCHED, V387_WATCHED, V388_WATCHED, V389_WATCHED, V390_WATCHED, V391_WATCHED, V392_LEGACY_VISIBLE_WATCHED, assert_v382_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V382.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v382_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v382.json"
BASE_SHA = "10265fdcf464fab80d396be1b8afdc2a906118c2"
CANDIDATE_SHA = "fdbe8d711dd4eda6e4cc7ed1ec069858d0b3b1d7"
LESSON_ID = "TABLET-GPT-DRIFT-NEURAL-CALIBRATION-AUTONOMOUS-META-GOVERNOR-V382"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v382.py", "tablet_runtime_manifest.py"]

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def watched_paths(contract, source, head="HEAD"):
    watch = contract["freshness_watch"]
    exact = set(watch["exact_paths"])
    prefixes = tuple(watch["path_prefixes"])
    excluded = set(watch["exclude_paths"])
    changed = subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"], text=True).splitlines()
    return sorted(path for path in changed if path not in excluded and (path in exact or path.startswith(prefixes)))

class TabletGptTcgGraderSyncV382Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V381.json", c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(74,c["prior_required_lesson_count"])
        self.assertEqual(75,c["current_required_lesson_count"])
        self.assertEqual(373,c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v382_rules_are_fail_closed(self):
        c=load(CONTRACT)
        for key in (
            "multi_objective_verified_feedback_governor_required",
            "operational_concept_drift_detection_required",
            "operational_drift_must_not_infer_market_direction",
            "neural_policy_calibration_monitoring_required",
            "neural_calibration_verified_outcomes_only",
            "verified_history_confidence_bound_required",
            "verified_regression_quarantine_required",
            "high_drift_recovery_only",
            "shadow_challenger_advisory_only",
            "feature_contracts_non_executable",
            "feature_contracts_require_protected_pr_ci",
            "v381_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key],True,key)
        self.assertTrue(autonomy.SAFETY["neural_policy_calibration_monitoring"])
        self.assertTrue(autonomy.SAFETY["shadow_challenger_advisory_only"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_current_runtime_entrypoint(self):
        c=load(CONTRACT)
        candidate=c["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED,candidate["watched_paths"])
        self.assertEqual(EXPECTED_WATCHED,watched_paths(c,BASE_SHA,CANDIDATE_SHA))
        self.assertEqual(sorted(set(V383_WATCHED) | set(V384_WATCHED) | set(V385_WATCHED) | set(V386_WATCHED) | set(V387_WATCHED) | set(V388_WATCHED) | set(V389_WATCHED) | set(V390_WATCHED) | set(V391_WATCHED) | set(V392_LEGACY_VISIBLE_WATCHED)),watched_paths(c,CANDIDATE_SHA))
        assert_v382_successor(self)
        main=(ROOT/"main").read_text(encoding="utf-8")
        manifest=(ROOT/"tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn("tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",main)
        for version in ("v400", "v399", "v398", "v397", "v388","v387","v386","v385","v382","v381","v380","v379","v378","v377","v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"',manifest)

if __name__=="__main__":
    unittest.main(verbosity=2)
