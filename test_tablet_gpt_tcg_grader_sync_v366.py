import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="13d408aedaf802c61e17d47527aefc19e0586c4f"
CANDIDATE="fbf476fe563ed1b368727b2b8dcbbcc880a82282"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v365_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v366_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v366.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V365.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V366.json"
EXPECTED_DIGEST="96d3e899b986191d3acf8179091616555029e82d30f5843a71963c303d06f0e1"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"])
    prefixes=tuple(watch["path_prefixes"])
    excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))

class TabletGptTcgGraderSyncV366(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"])
        self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([346],[row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{346})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+c["delta_required_lesson_count"],c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        dg=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,dg)
        self.assertEqual(dg,delta["lesson_digest_sha256"])
        self.assertEqual(dg,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",receipt["verification"]["verified_result"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE,CANDIDATE):
            subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        c=read(CONTRACT)
        cand=c["candidate_sync"]
        self.assertEqual(SOURCE,cand["base_main_sha"])
        self.assertEqual(CANDIDATE,cand["candidate_commit"])
        expected_watched=["grading_company_updates.json"]
        self.assertEqual(expected_watched,watched_paths(c,SOURCE,CANDIDATE))
        self.assertEqual(sorted(cand["watched_paths"]),watched_paths(c,SOURCE,CANDIDATE))
        expected={
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V366.json",
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v366_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v366.json",
            "test_tablet_gpt_tcg_grader_sync_v366.py",
        }
        self.assertEqual(expected,set(cand["generation_files"]))
        self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]
        self.assertEqual([],watched_paths(c,CANDIDATE),"v366 successor has uncovered watched changes")

    def test_fail_closed_promotion_and_evidence_boundaries(self):
        c=read(CONTRACT)
        rules=c["rules"]
        self.assertTrue(rules["required_checks_must_succeed_before_merge"])
        self.assertTrue(rules["protected_main_candidate_branch_required"])
        self.assertTrue(rules["direct_main_push_forbidden"])
        self.assertTrue(rules["force_or_admin_bypass_forbidden"])
        self.assertTrue(rules["freshness_threshold_widening_forbidden"])
        self.assertTrue(rules["post_merge_candidate_sync_must_fail_on_any_extra_watched_path"])
        self.assertTrue(rules["physical_tablet_and_drive_results_must_not_be_invented"])
        lesson=read(DELTA)["lessons"][0]
        self.assertEqual("TGPT-PREV-STATIC-GRADING-SUCCESSOR-BEFORE-MERGE",lesson["prevention_rule_id"])
        self.assertIn("grading_company_updates.json",lesson["validation_required"][2])

if __name__=="__main__":
    unittest.main(verbosity=2)
