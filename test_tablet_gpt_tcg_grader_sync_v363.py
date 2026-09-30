import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="5b18eb7c0c0721bcbedf6697e6254fe2e830f1e3"
CANDIDATE="9c11f5390aad2b59dee8f067bffb571102130203"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v362_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v363_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v363.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V362.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V363.json"
RUNTIME_WORKFLOW=ROOT/".github/workflows/runtime-optimization-hardening.yml"
PUBLISHER=ROOT/"scripts/publish_candidate_pr.sh"
EXPECTED_DIGEST="44454f70aec8a4ee5f261b9f25c3761b6c210f67038a4ba9cfcebdfa568d9902"

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))

class TabletGptTcgGraderSyncV363(unittest.TestCase):
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
        raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        dg=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(dg,d["lesson_digest_sha256"]); self.assertEqual(dg,r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",r["status"]); self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",r["verification"]["verified_result"])
        self.assertEqual(d["source_main_sha"],r["source_main_sha"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"]); self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        files={sp.relative_to(ROOT).as_posix(),s["delta_snapshot"],s["receiver_receipt"],s["verification_test"]}
        self.assertTrue(files.issubset(set(s["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/path).is_file(),path) for path in files]
        candidate=s.get("candidate_sync") or {}
        if candidate:
            self.assertTrue(candidate["requires_exact_watched_path_match"]); self.assertTrue(candidate["post_merge_coverage_allowed"])
            self.assertEqual(files,set(candidate["generation_files"])); self.assertEqual(candidate["base_main_sha"],d["source_main_sha"])
            base=candidate["base_main_sha"]; head=candidate["candidate_commit"]
            self.assertEqual(sorted(candidate["watched_paths"]),watched_paths(s,base,head))
            self.assertEqual([],watched_paths(s,head),"latest successor has uncovered watched changes")
            subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True); subprocess.run(["git","merge-base","--is-ancestor",head,"HEAD"],check=True)
            return
        self.assertTrue(s["rules"].get("post_merge_checkpoint_must_anchor_future_pr_freshness"),f"v{version} must be an exact candidate or verified post-merge checkpoint")
        self.assertTrue(s["rules"].get("subsequent_watched_change_requires_new_generation"))
        base=d["source_main_sha"]; self.assertEqual([],watched_paths(s,base),f"v{version} checkpoint has uncovered watched changes")
        subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True)

    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"]); self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([341],[r["pr"] for r in delta["covered_merges"]]); self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{341})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"]); self.assertEqual(c["prior_required_lesson_count"]+1,c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":")); d=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,d); self.assertEqual(d,delta["lesson_digest_sha256"]); self.assertEqual(d,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([r["lesson_id"] for r in delta["lessons"]],receipt["accepted_lesson_ids"]); self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"]); self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"]); self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"]); self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE,CANDIDATE): subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        c=read(CONTRACT); cand=c["candidate_sync"]
        self.assertEqual(SOURCE,cand["base_main_sha"]); self.assertEqual(CANDIDATE,cand["candidate_commit"])
        expected_watched=[".github/workflows/runtime-optimization-hardening.yml"]
        self.assertEqual(expected_watched,watched_paths(c,SOURCE,CANDIDATE)); self.assertEqual(sorted(cand["watched_paths"]),watched_paths(c,SOURCE,CANDIDATE))
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V363.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v363_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v363.json","test_tablet_gpt_tcg_grader_sync_v363.py"}
        self.assertEqual(expected,set(cand["generation_files"])); self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]
        relevant=watched_paths(c,CANDIDATE)
        if relevant: self._assert_newer_successor_covers(363,relevant)

    def test_protected_runtime_workflow_publishes_only_verified_candidate(self):
        workflow=RUNTIME_WORKFLOW.read_text(encoding="utf-8"); publisher=PUBLISHER.read_text(encoding="utf-8")
        self.assertIn("bash scripts/publish_candidate_pr.sh",workflow)
        for permission in ("contents: write","pull-requests: write","actions: write","checks: read"): self.assertIn(permission,workflow)
        self.assertNotIn("git push origin HEAD:main",workflow); self.assertNotIn("git push origin main",workflow)
        for marker in ("BASE_ADVANCED","BASE_ADVANCED_BEFORE_MERGE","REQUIRED_CHECK_FAILED","REQUIRED_CHECK_TIMEOUT","NO_CANDIDATE_COMMIT","MERGE_REJECTED"): self.assertIn(marker,publisher)
        for required in ("Tablet GPT TCG Grader Main Alignment","Repository Integrity Guard","Main SELFREFINE","Deep SELFREFINE Guard","Exhaustive SELFREFINE Guard","Tablet Termux Main Guard","Android Updater Guard"): self.assertIn(required,publisher)
        self.assertNotIn("HEAD:main",publisher); self.assertNotIn("--admin",publisher); self.assertNotIn("--force",publisher)

if __name__=="__main__": unittest.main(verbosity=2)
