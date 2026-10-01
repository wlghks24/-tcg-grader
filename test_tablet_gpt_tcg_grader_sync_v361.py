import hashlib
import json
import re
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="14a509e5e594711be8b851f1942f2270cb1b3d69"
CANDIDATE="25a3e635475da4615095f471b74b186fba5e4260"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v360_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v361_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v361.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V360.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V361.json"
WORKFLOW=ROOT/".github/workflows/gpt-tcg-drive-package.yml"
EXPECTED_DIGEST="5b144584a3740b5025223295b626da0818549256d31fa9331087b3324935c961"

def read(path): return json.loads(path.read_text(encoding="utf-8"))
def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))

class TabletGptTcgGraderSyncV361(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"]); self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([338],[r["pr"] for r in delta["covered_merges"]]); self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{338})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+c["delta_required_lesson_count"],c["current_required_lesson_count"])
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

    def test_exact_watched_path_and_successor_delegation(self):
        c=read(CONTRACT); cand=c["candidate_sync"]
        self.assertEqual(SOURCE,cand["base_main_sha"]); self.assertEqual(CANDIDATE,cand["candidate_commit"])
        self.assertEqual(sorted(cand["watched_paths"]),watched_paths(c,SOURCE,CANDIDATE))
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V361.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v361_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v361.json","test_tablet_gpt_tcg_grader_sync_v361.py"}
        self.assertEqual(expected,set(cand["generation_files"])); self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"])))
        later=watched_paths(c,CANDIDATE)
        if not later: return
        pattern=re.compile(r"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V(\d+)\.json$")
        successors=[]
        for path in (ROOT/"TCG_CROSSCHECK").glob("TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V*.json"):
            m=pattern.fullmatch(path.name)
            if m and int(m.group(1))>361: successors.append((int(m.group(1)),path))
        self.assertTrue(successors,f"v361 stale without verified successor: {later}")
        version,sp=max(successors); s=read(sp); d=read(ROOT/s["delta_snapshot"]); r=read(ROOT/s["receiver_receipt"])
        raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        dg=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(dg,d["lesson_digest_sha256"]); self.assertEqual(dg,r["delta_lesson_digest_sha256"])
        self.assertEqual("SYNCED_VERIFIED",r["status"]); self.assertEqual("TABLET_GPT_TCG_GRADER_MATCH",r["verification"]["verified_result"])
        self.assertEqual(d["source_main_sha"],r["source_main_sha"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        files={sp.relative_to(ROOT).as_posix(),s["delta_snapshot"],s["receiver_receipt"],s["verification_test"]}
        [self.assertTrue((ROOT/p).is_file(),p) for p in files]
        self.assertTrue(files.issubset(set(s["freshness_watch"]["exclude_paths"])))
        sc=s.get("candidate_sync") or {}
        if sc:
            self.assertTrue(sc["requires_exact_watched_path_match"])
            self.assertTrue(sc["post_merge_coverage_allowed"])
            self.assertEqual(files,set(sc["generation_files"]))
            self.assertEqual(sc["base_main_sha"],d["source_main_sha"])
            self.assertEqual(sorted(sc["watched_paths"]),watched_paths(s,sc["base_main_sha"],sc["candidate_commit"]))
            self.assertEqual([],watched_paths(s,sc["candidate_commit"]),"latest successor has uncovered watched changes")
            subprocess.run(["git","merge-base","--is-ancestor",sc["base_main_sha"],"HEAD"],check=True)
            subprocess.run(["git","merge-base","--is-ancestor",sc["candidate_commit"],"HEAD"],check=True)
            return
        self.assertTrue(s["rules"].get("post_merge_checkpoint_must_anchor_future_pr_freshness"),f"v{version} must be an exact candidate or verified post-merge checkpoint")
        self.assertTrue(s["rules"].get("subsequent_watched_change_requires_new_generation"))
        base=d["source_main_sha"]
        self.assertIn(base,[row["merge_sha"] for row in d["covered_merges"]],"checkpoint source must be a covered merged-main SHA")
        self.assertEqual([],watched_paths(s,base),f"v{version} checkpoint has uncovered watched changes")
        subprocess.run(["git","merge-base","--is-ancestor",base,"HEAD"],check=True)

    def test_upload_artifact_explicitly_includes_hidden_outbox_without_weakening_gates(self):
        workflow=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",workflow)
        self.assertIn("path: .tcg_drive_outbox/*",workflow); self.assertIn("include-hidden-files: true",workflow)
        self.assertIn("if-no-files-found: error",workflow); self.assertIn("STALE_AUTO_UPDATE_REPORT",workflow)
        self.assertIn("FRESH_LOCAL_COLLECTION_RETRY",workflow)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-refresh')",workflow)
        self.assertIn("never widen freshness gates",workflow)
        self.assertNotIn("actions: write",workflow)
        latest=read(ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V370.json")
        self.assertTrue(latest["rules"]["drive_package_stale_inputs_upload_forbidden"])
        self.assertTrue(latest["rules"]["drive_package_non_freshness_critical_remains_blocking"])

if __name__=="__main__": unittest.main(verbosity=2)
