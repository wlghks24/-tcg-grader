import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="7f6afc86dbb635eacb98d325270bc4c6fffe9b68"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v366_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v367_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v367.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V366.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V367.json"
EXPECTED_DIGEST="f4f8419f4998804650c33bdad406461f683a90aa5d373f6742f255fbce4c52cb"


def read(path): return json.loads(path.read_text(encoding="utf-8"))

def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))


class TabletGptTcgGraderSyncV367(unittest.TestCase):
    def _assert_newer_successor_covers(self, minimum_version, relevant):
        pattern=re.compile(r"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V(\d+)\.json$")
        successors=[]
        for path in (ROOT/"TCG_CROSSCHECK").glob("TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V*.json"):
            match=pattern.fullmatch(path.name)
            if match and int(match.group(1))>minimum_version:
                successors.append((int(match.group(1)),path))
        self.assertTrue(successors,f"v{minimum_version} stale without verified successor: {relevant}")
        version,sp=max(successors)
        s=read(sp); d=read(ROOT/s["delta_snapshot"]); r=read(ROOT/s["receiver_receipt"])
        raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":")); dg=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(dg,d["lesson_digest_sha256"]); self.assertEqual(dg,r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",r["status"]); self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",r["verification"]["verified_result"])
        self.assertEqual(d["source_main_sha"],r["source_main_sha"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"]); self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        files={sp.relative_to(ROOT).as_posix(),s["delta_snapshot"],s["receiver_receipt"],s["verification_test"]}
        self.assertTrue(files.issubset(set(s["freshness_watch"]["exclude_paths"]))); [self.assertTrue((ROOT/path).is_file(),path) for path in files]
        candidate=s.get("candidate_sync") or {}
        if candidate:
            self.assertTrue(candidate["requires_exact_watched_path_match"]); self.assertTrue(candidate["post_merge_coverage_allowed"])
            self.assertEqual(files,set(candidate["generation_files"])); self.assertEqual(candidate["base_main_sha"],d["source_main_sha"])
            base=candidate["base_main_sha"]; head=candidate["candidate_commit"]
            self.assertEqual(sorted(candidate["watched_paths"]),watched_paths(s,base,head)); self.assertEqual([],watched_paths(s,head),"latest successor has uncovered watched changes")
            subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True); subprocess.run(["git","merge-base","--is-ancestor",head,"HEAD"],check=True)
            return
        self.assertTrue(s["rules"].get("post_merge_checkpoint_must_anchor_future_pr_freshness"),f"v{version} must be an exact candidate or verified post-merge checkpoint")
        self.assertTrue(s["rules"].get("subsequent_watched_change_requires_new_generation")); base=d["source_main_sha"]
        self.assertEqual([],watched_paths(s,base),f"v{version} checkpoint has uncovered watched changes"); subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True)

    def test_lineage_digest_receipt_and_exact_merged_main_anchor(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"]); self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"]); self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([348],[row["pr"] for row in delta["covered_merges"]]); self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{348})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"]); self.assertEqual(c["prior_required_lesson_count"]+1,c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":")); digest=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,digest); self.assertEqual(digest,delta["lesson_digest_sha256"]); self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]],receipt["accepted_lesson_ids"]); self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",receipt["verification"]["verified_result"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"]); self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"]); self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"]); self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git","merge-base","--is-ancestor",SOURCE,"HEAD"],check=True)

    def test_checkpoint_generation_is_complete_excluded_and_current(self):
        c=read(CONTRACT)
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V367.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v367_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v367.json","test_tablet_gpt_tcg_grader_sync_v367.py"}
        self.assertFalse(c.get("candidate_sync"),"post-merge checkpoint must not masquerade as a pre-merge candidate")
        self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"]))); [self.assertTrue((ROOT/path).is_file(),path) for path in expected]
        relevant=watched_paths(c,SOURCE)
        if relevant: self._assert_newer_successor_covers(367,relevant)

    def test_protected_main_and_evidence_boundaries_remain_explicit(self):
        rules=read(CONTRACT)["rules"]
        required=("post_merge_checkpoint_requires_exact_merged_main","post_merge_checkpoint_must_anchor_future_pr_freshness","subsequent_watched_change_requires_new_generation","protected_main_candidate_branch_required","required_checks_must_succeed_before_merge","direct_main_push_forbidden","force_or_admin_bypass_forbidden","freshness_threshold_widening_forbidden","chatgpt_model_weights_transfer_forbidden","raw_grading_calibration_transfer_forbidden","device_local_learning_memory_blind_overwrite_forbidden","physical_tablet_and_drive_results_must_not_be_invented")
        for key in required: self.assertIs(rules[key],True,key)


if __name__=="__main__": unittest.main(verbosity=2)
