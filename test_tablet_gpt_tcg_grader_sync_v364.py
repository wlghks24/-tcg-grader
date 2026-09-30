import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="f637f866aabbc1a76bcdd1a9b64744ed9a725b1c"
CANDIDATE="bf581df26f1b222a3f70520e4df8e921de976616"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v363_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v364_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v364.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V363.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V364.json"
WORKFLOW=ROOT/".github/workflows/gpt-tcg-drive-package.yml"
EXPECTED_DIGEST="ab76114736b636533cce3707c6442075058623e8be4e0b6a53e64307f50e83c2"


def read(path): return json.loads(path.read_text(encoding="utf-8"))
def watched_paths(contract, source, head="HEAD"):
    watch=contract["freshness_watch"]
    exact=set(watch["exact_paths"]); prefixes=tuple(watch["path_prefixes"]); excluded=set(watch["exclude_paths"])
    changed=subprocess.check_output(["git","diff","--name-only",f"{source}..{head}"],text=True).splitlines()
    return sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))


class TabletGptTcgGraderSyncV364(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"]); self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([342],[r["pr"] for r in delta["covered_merges"]]); self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{342})
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
        expected_watched=[".github/workflows/gpt-tcg-drive-package.yml"]
        self.assertEqual(expected_watched,watched_paths(c,SOURCE,CANDIDATE))
        self.assertEqual(sorted(cand["watched_paths"]),watched_paths(c,SOURCE,CANDIDATE))
        self.assertEqual([],watched_paths(c,CANDIDATE),"v364 candidate has uncovered later watched changes")
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V364.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v364_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v364.json","test_tablet_gpt_tcg_grader_sync_v364.py"}
        self.assertEqual(expected,set(cand["generation_files"]))
        self.assertTrue(expected.issubset(set(c["freshness_watch"]["exclude_paths"])))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]

    def test_package_recovery_is_freshness_only_and_fail_closed(self):
        text=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('freshness = {"STALE_SOCIAL_SNAPSHOT", "STALE_AUTO_UPDATE_REPORT"}',text)
        self.assertIn('critical and critical <= freshness',text)
        self.assertIn('FRESH_STATIC_REFRESH_DISPATCHED',text)
        self.assertIn('tcg-static-data-refresh.yml/dispatches',text)
        self.assertIn('echo "ready=false"',text)
        self.assertIn("if: steps.package.outputs.ready == 'true'",text)
        self.assertIn('exit "${rc}"',text)
        self.assertIn('never widen report/social freshness gates',text)


if __name__=="__main__": unittest.main(verbosity=2)
