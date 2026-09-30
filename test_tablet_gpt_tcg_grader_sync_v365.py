import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="b5d85005fa7df5bac575641027e89cd5a9f12735"
CANDIDATE="21ca7e359df36a848dd917d47acb67f2eb4386a6"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v364_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v365_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v365.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V364.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V365.json"
WORKFLOW=ROOT/".github/workflows/gpt-tcg-drive-package.yml"
EXPECTED_DIGEST="d9cc7ec86f347e834768069e30da8c3fb97eef769755f2fd2f52e5a3c6952abd"

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))

class TabletGptTcgGraderSyncV365(unittest.TestCase):
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
        self.assertEqual(dg,d["lesson_digest_sha256"])
        self.assertEqual(dg,r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",r["verification"]["verified_result"])
        self.assertEqual(d["source_main_sha"],r["source_main_sha"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        files={sp.relative_to(ROOT).as_posix(),s["delta_snapshot"],s["receiver_receipt"],s["verification_test"]}
        self.assertTrue(files.issubset(set(s["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/path).is_file(),path) for path in files]
        candidate=s.get("candidate_sync") or {}
        if candidate:
            self.assertTrue(candidate["requires_exact_watched_path_match"])
            self.assertTrue(candidate["post_merge_coverage_allowed"])
            self.assertEqual(files,set(candidate["generation_files"]))
            self.assertEqual(candidate["base_main_sha"],d["source_main_sha"])
            base=candidate["base_main_sha"]; head=candidate["candidate_commit"]
            self.assertEqual(sorted(candidate["watched_paths"]),watched_paths(s,base,head))
            self.assertEqual([],watched_paths(s,head),"latest successor has uncovered watched changes")
            subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True)
            subprocess.run(["git","merge-base","--is-ancestor",head,"HEAD"],check=True)
            return
        self.assertTrue(s["rules"].get("post_merge_checkpoint_must_anchor_future_pr_freshness"),
                        f"v{version} must be an exact candidate or verified post-merge checkpoint")
        self.assertTrue(s["rules"].get("subsequent_watched_change_requires_new_generation"))
        base=d["source_main_sha"]
        self.assertEqual([],watched_paths(s,base),f"v{version} checkpoint has uncovered watched changes")
        subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True)

    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"]); self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([345],[row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{345})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+c["delta_required_lesson_count"],c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        dg=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,dg); self.assertEqual(dg,delta["lesson_digest_sha256"]); self.assertEqual(dg,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",receipt["verification"]["verified_result"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE,CANDIDATE): subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],check=True)

    def test_exact_candidate_scope_and_complete_generation(self):
        c=read(CONTRACT); cand=c["candidate_sync"]
        self.assertEqual(SOURCE,cand["base_main_sha"]); self.assertEqual(CANDIDATE,cand["candidate_commit"])
        expected_watched=[".github/workflows/gpt-tcg-drive-package.yml"]
        self.assertEqual(expected_watched,watched_paths(c,SOURCE,CANDIDATE))
        self.assertEqual(sorted(cand["watched_paths"]),watched_paths(c,SOURCE,CANDIDATE))
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V365.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v365_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v365.json","test_tablet_gpt_tcg_grader_sync_v365.py"}
        self.assertEqual(expected,set(cand["generation_files"]))
        self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]
        later=watched_paths(c,CANDIDATE)
        if later:
            self._assert_newer_successor_covers(365,later)

    def test_drive_package_recovery_is_freshness_only_and_fail_closed(self):
        workflow=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('recoverable = {"STALE_AUTO_UPDATE_REPORT", "STALE_SOCIAL_SNAPSHOT"}',workflow)
        self.assertIn("critical and critical <= recoverable",workflow)
        self.assertIn("FRESH_STATIC_REFRESH_DISPATCHED",workflow)
        self.assertIn("tcg-static-data-refresh.yml/dispatches",workflow)
        self.assertIn('echo "ready=false"',workflow)
        self.assertIn('exit "${rc}"',workflow)
        self.assertIn("never widen the two-hour report freshness gate",workflow)
        self.assertNotIn("publish_allowed = true",workflow)

if __name__=="__main__":
    unittest.main(verbosity=2)
