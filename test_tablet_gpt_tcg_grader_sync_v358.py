import hashlib
import json
import math
from pathlib import Path
import subprocess
import unittest

ROOT=Path(__file__).resolve().parent
SOURCE="5ebab8c0fcddacf06958933199f091ab60bfc057"
CANDIDATE="bfb712d4a9a403416b74ade6400f23a1d5214a81"
PRIOR=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v357_delta.json"
DELTA=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v358_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v358.json"
PRIOR_CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V357.json"
CONTRACT=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V358.json"
EXPECTED_DIGEST="ae7c7747393f3ef9774d8527b5c09e41879bc983b7480058437f53470cb287ab"

def read(p): return json.loads(p.read_text(encoding="utf-8"))
def explicit_link_state(value):
    prefix="접속 불가 확인 (HTTP "
    if value=="정상": return True
    if not (isinstance(value,str) and value.startswith(prefix) and value.endswith(")")): return False
    code=value[len(prefix):-1]
    return code.isdigit() and 400<=int(code)<=599

class TabletGptTcgGraderSyncV358(unittest.TestCase):
    def test_lineage_digest_receipt_and_safe_transfer_boundary(self):
        prior,delta,receipt,pc,c=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"],delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"],receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE,delta["source_main_sha"])
        self.assertEqual(SOURCE,receipt["source_main_sha"])
        self.assertEqual([333],[r["pr"] for r in delta["covered_merges"]])
        self.assertEqual(SOURCE,delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(set(c["current_required_merge_prs"]),set(pc["current_required_merge_prs"])|{333})
        self.assertEqual(pc["current_required_lesson_count"],c["prior_required_lesson_count"])
        self.assertEqual(c["prior_required_lesson_count"]+c["delta_required_lesson_count"],c["current_required_lesson_count"])
        raw=json.dumps(delta["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        d=hashlib.sha256(raw.encode()).hexdigest()
        self.assertEqual(EXPECTED_DIGEST,d)
        self.assertEqual(d,delta["lesson_digest_sha256"])
        self.assertEqual(d,receipt["delta_lesson_digest_sha256"])
        self.assertEqual([r["lesson_id"] for r in delta["lessons"]],receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED",receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        for sha in (SOURCE,CANDIDATE): subprocess.run(["git","merge-base","--is-ancestor",sha,"HEAD"],check=True)

    def test_exact_candidate_watched_path_set_and_generation_files(self):
        c=read(CONTRACT); cand=c["candidate_sync"]
        self.assertEqual(SOURCE,cand["base_main_sha"])
        self.assertEqual(CANDIDATE,cand["candidate_commit"])
        self.assertTrue(cand["requires_exact_watched_path_match"])
        self.assertTrue(cand["post_merge_coverage_allowed"])
        w=c["freshness_watch"]; exact=set(w["exact_paths"]); prefixes=tuple(w["path_prefixes"]); excluded=set(w["exclude_paths"])
        changed=subprocess.check_output(["git","diff","--name-only",f"{SOURCE}..HEAD"],text=True).splitlines()
        relevant=sorted(p for p in changed if p not in excluded and (p in exact or p.startswith(prefixes)))
        self.assertEqual(cand["watched_paths"],relevant)
        expected={"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V358.json","TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v358_delta.json","TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v358.json","test_tablet_gpt_tcg_grader_sync_v358.py"}
        self.assertEqual(expected,set(cand["generation_files"]))
        self.assertTrue(expected.issubset(excluded))
        [self.assertTrue((ROOT/p).is_file(),p) for p in expected]

    def test_static_candidate_output_remains_fail_closed_and_provenanced(self):
        report=read(ROOT/"auto_update_report.json"); fx=read(ROOT/"exchange_rates.json"); grading=read(ROOT/"grading_company_updates.json"); promo=read(ROOT/"promo_events.json")
        self.assertTrue(report["ok"]); self.assertEqual(0,report["fresh_failure_count"]); self.assertGreaterEqual(report["fresh_success_count"],1); self.assertEqual("정상",fx["collection_status"])
        for key in ("JPY_KRW","USD_KRW"): self.assertTrue(math.isfinite(fx["rates"][key]) and fx["rates"][key]>0)
        self.assertIsInstance(grading,dict); self.assertNotEqual({},grading)
        kr=[r for r in promo.get("items",[]) if r.get("game")=="포켓몬 카드" and r.get("region")=="KR" and r.get("category")=="movie"]
        self.assertTrue(kr); self.assertEqual("https://pokemoncard.co.kr/main",kr[0].get("source")); self.assertEqual("official",kr[0].get("source_grade")); self.assertTrue(explicit_link_state(kr[0].get("link_status")))

if __name__=="__main__": unittest.main(verbosity=2)
