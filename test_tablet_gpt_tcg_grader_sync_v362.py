import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="ce2e26b139b31ac62829332041bccef0f6158e7d"
CANDIDATE="ea2b3a0dd8e358254f54d0324504189ca6dc6fbc"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v361_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v362_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v362.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V361.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V362.json"
RUNTIME=ROOT/"tablet_gdrive_sync_perf_v262.py"
EXPECTED_DIGEST="00d53569b2a916b5024bae663ec7485160ddc4f209bbe37f083d96072c3118ca"

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))

class TabletGptTcgGraderSyncV362(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"]); self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([340],[r["pr"] for r in delta["covered_merges"]]); self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{340})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+1,c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        d=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,d); self.assertEqual(d,delta["lesson_digest_sha256"]); self.assertEqual(d,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([r["lesson_id"] for r in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE,CANDIDATE): subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        c=read(CONTRACT); cand=c["candidate_sync"]
        self.assertEqual(SOURCE,cand["base_main_sha"]); self.assertEqual(CANDIDATE,cand["candidate_commit"])
        self.assertEqual(["tablet_gdrive_sync_perf_v262.py"],watched_paths(c,SOURCE,CANDIDATE))
        self.assertEqual(sorted(cand["watched_paths"]),watched_paths(c,SOURCE,CANDIDATE))
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V362.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v362_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v362.json","test_tablet_gpt_tcg_grader_sync_v362.py"}
        self.assertEqual(expected,set(cand["generation_files"]))
        self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]

        later=watched_paths(c,CANDIDATE)
        if not later:
            return
        pattern=re.compile(r"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V(\d+)\.json$")
        successors=[]
        for path in (ROOT/"TCG_CROSSCHECK").glob("TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V*.json"):
            m=pattern.fullmatch(path.name)
            if m and int(m.group(1))>362:
                successors.append((int(m.group(1)),path))
        self.assertTrue(successors,f"v362 stale without verified successor: {later}")
        version,successor_path=max(successors)
        successor=read(successor_path)
        delta=read(ROOT/successor["delta_snapshot"]); receipt=read(ROOT/successor["receiver_receipt"])
        self.assertEqual(delta["source_main_sha"],receipt["source_main_sha"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",receipt["verification"]["verified_result"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(digest,delta["lesson_digest_sha256"]); self.assertEqual(digest,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([r["lesson_id"] for r in delta["lessons"]],receipt["accepted_lesson_ids"])
        generation_files={successor_path.relative_to(ROOT).as_posix(),successor["delta_snapshot"],successor["receiver_receipt"],successor["verification_test"]}
        [self.assertTrue((ROOT/p).is_file(),p) for p in generation_files]
        self.assertTrue(generation_files.issubset(set(successor["freshness_watch"]["exclude_paths"])))
        successor_candidate=successor.get("candidate_sync") or {}
        if successor_candidate:
            self.assertTrue(successor_candidate["requires_exact_watched_path_match"])
            self.assertTrue(successor_candidate["post_merge_coverage_allowed"])
            self.assertEqual(successor_candidate["base_main_sha"],delta["source_main_sha"])
            self.assertEqual(generation_files,set(successor_candidate["generation_files"]))
            base=successor_candidate["base_main_sha"]; head=successor_candidate["candidate_commit"]
            self.assertEqual(sorted(successor_candidate["watched_paths"]),watched_paths(successor,base,head))
            self.assertEqual([],watched_paths(successor,head),f"v{version} successor has uncovered watched changes")
            subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True)
            subprocess.run(["git","merge-base","--is-ancestor",head,"HEAD"],check=True)
            return
        self.assertTrue(successor["rules"].get("post_merge_checkpoint_must_anchor_future_pr_freshness"),f"v{version} must be an exact candidate or verified post-merge checkpoint")
        self.assertTrue(successor["rules"].get("subsequent_watched_change_requires_new_generation"))
        base=delta["source_main_sha"]
        self.assertIn(base,[row["merge_sha"] for row in delta["covered_merges"]],"checkpoint source must be a covered merged-main SHA")
        self.assertEqual([],watched_paths(successor,base),f"v{version} checkpoint has uncovered watched changes")
        subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True)

    def test_receipt_delivery_precedes_completed_marker(self):
        text=RUNTIME.read_text(encoding="utf-8")
        for marker in ("strict_flush_pending_receipts","_require_secured_completed_receipt","_finalize_success_delivery","TABLET_SYNC_OK"):
            self.assertIn(marker,text)
        fn=text[text.index("def _finalize_success_delivery"):text.index("def sync_once_receipt_fail_closed")]
        upload=fn.index("core.rclone_upload")
        sent=fn.index("_mark_receipt_sent")
        completed=fn.index("_atomic_write_text(completed")
        self.assertLess(upload,sent); self.assertLess(sent,completed)

if __name__=="__main__": unittest.main(verbosity=2)
