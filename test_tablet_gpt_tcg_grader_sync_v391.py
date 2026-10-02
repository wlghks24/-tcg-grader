import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v398 as autonomy
from sync_v376_successor_test_support import assert_v391_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V391.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v391_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v391.json"
BASE_SHA="80c1210c453b779021292d8eb16015bd5f54147d"
CANDIDATE_SHA="47fe605f68e2f8a73b0cf50bb51244db03e12f2b"
LESSON_ID="TABLET-GPT-VERIFIED-MULTI-CANDIDATE-SELF-EVOLUTION-V398"
EXPECTED_WATCHED=["main","tablet_autonomous_evolution_v398.py","tablet_runtime_manifest.py"]

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV391Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V390.json",c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v390_delta.json",c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(83,c["prior_required_lesson_count"])
        self.assertEqual(84,c["current_required_lesson_count"])
        self.assertEqual(403,c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED",r["status"])

    def test_v398_rules_and_safety(self):
        c=load(CONTRACT)
        for key in (
            "multi_candidate_self_extension_required",
            "candidate_tournament_deterministic_required",
            "candidate_tournament_canonical_v373_allowlist_only_required",
            "candidate_verified_kpi_memory_only_required",
            "candidate_bounded_exploration_required",
            "single_v398_canary_required",
            "v398_owned_exact_rollback_required",
            "failed_recipe_bounded_quarantine_required",
            "v397_v398_experiment_overlap_forbidden",
            "v397_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key],True,key)
        self.assertTrue(autonomy.SAFETY["multi_candidate_self_extension_enabled"])
        self.assertTrue(autonomy.SAFETY["candidate_tournament_verified_history_learning"])
        self.assertTrue(autonomy.SAFETY["single_canary_capability_only"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_v398_runtime_route(self):
        candidate=load(CONTRACT)["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED,candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v391_successor(self)

    def test_main_and_runtime_manifest_use_v398(self):
        main=(ROOT/"main").read_text(encoding="utf-8")
        manifest=(ROOT/"tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn("tablet_autonomous_evolution_v399.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",main)
        for version in ("v399", "v398","v397","v391","v390","v388","v387","v386","v385","v382","v381","v380","v379","v378","v377","v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"',manifest)

    def test_receipt_preserves_device_and_source_boundaries(self):
        r=load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["multi_candidate_allowlisted_only"])
        self.assertTrue(r["alignment_policy"]["candidate_verified_kpi_memory_only"])
        self.assertTrue(r["alignment_policy"]["single_v398_canary"])
        self.assertTrue(r["alignment_policy"]["failed_recipe_bounded_quarantine"])
        self.assertTrue(r["alignment_policy"]["exact_v398_owned_rollback"])
        self.assertTrue(r["alignment_policy"]["v397_experiment_conflict_prevention"])
        self.assertFalse(r["alignment_policy"]["source_feature_runtime_code_generation"])

if __name__=="__main__":
    unittest.main(verbosity=2)
