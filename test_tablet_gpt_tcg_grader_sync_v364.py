import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="f637f866aabbc1a76bcdd1a9b64744ed9a725b1c"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v363_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v364_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v364.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V363.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V364.json"
EXPECTED_DIGEST="01c64b1220a3479cc00ef9e237cdcfa1b7df26376326a1c0a4890d255f7fb10b"

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))

class TabletGptTcgGraderSyncV364(unittest.TestCase):
    def test_lineage_digest_receipt_and_exact_merged_main_anchor(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"]); self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([342],[r["pr"] for r in delta["covered_merges"]])
        self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{342})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+1,c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        d=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,d); self.assertEqual(d,delta["lesson_digest_sha256"]); self.assertEqual(d,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([r["lesson_id"] for r in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",receipt["verification"]["verified_result"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git","merge-base","--is-ancestor",SOURCE,"HEAD"],check=True)

    def test_checkpoint_generation_is_complete_excluded_and_current(self):
        c=read(CONTRACT)
        expected={
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V364.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v364_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v364.json",
            "test_tablet_gpt_tcg_grader_sync_v364.py",
        }
        self.assertFalse(c.get("candidate_sync"),"post-merge checkpoint must not masquerade as a pre-merge candidate")
        self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]
        self.assertEqual([],watched_paths(c,SOURCE),"v364 checkpoint has uncovered watched changes")

    def test_receipt_runtime_rollback_and_protected_main_rules_remain_explicit(self):
        rules=read(CONTRACT)["rules"]
        required=(
            "pending_receipt_delivery_failure_must_propagate",
            "tablet_completion_requires_secured_success_receipt",
            "completed_marker_must_follow_remote_receipt_delivery",
            "exact_main_pinning_must_remain_enforced",
            "exact_17_output_hash_validation_must_remain_enforced",
            "verified_runtime_sha_must_remain_enforced",
            "rollback_must_preserve_original_apply_or_runtime_failure",
            "protected_main_candidate_branch_required",
            "required_checks_must_succeed_before_merge",
            "direct_main_push_forbidden",
            "force_or_admin_bypass_forbidden",
            "freshness_threshold_widening_forbidden",
            "physical_tablet_and_drive_results_must_not_be_invented",
        )
        for key in required: self.assertIs(rules[key],True,key)

if __name__=="__main__": unittest.main(verbosity=2)
