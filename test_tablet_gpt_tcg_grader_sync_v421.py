#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v421_successor
ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V421.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v421_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v421.json"
BASE_SHA="a13f80da8d341020da8e650868816300e0eafcad"
CANDIDATE_SHA="11cff2bd294dbaeb00a04dce4f49d8ddde181fca"
LESSON_ID="TABLET-GPT-TCG-VERIFIED-ACTIVATION-OBSERVABILITY-V421"
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
class TabletGptTcgGraderSyncV421Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V420.json",c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"]); self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(111,c["prior_required_lesson_count"]); self.assertEqual(112,c["current_required_lesson_count"])
        self.assertIn(443,c["current_required_merge_prs"]); self.assertEqual("SYNCED_VERIFIED",r["status"])
    def test_candidate_exactly_covers_verified_activation_observability(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual(["feature_contract.py","tablet_autonomy_dashboard_v400.js","tcg_game_registry.py"],x["watched_paths"])
        assert_v421_successor(self)
    def test_verified_score_is_persisted_but_never_authoritative(self):
        code=(ROOT/"tcg_game_registry.py").read_text(encoding="utf-8")
        start=code.index("def _evidence_activation_score("); review=code.index("def review_registry(")
        self.assertNotIn("verified_activation_score",code[start:review])
        self.assertIn('evidence["verified_activation_score"] = round(evidence_activation, 6)',code)
        self.assertIn('evidence["verified_activation_gate"] = {',code)
        self.assertIn("old high score cannot self-reinforce",code)
        self.assertIn("activation = max(seed_activation, evidence_activation)",code)
    def test_watch_score_is_read_only_visible_and_safety_unchanged(self):
        js=(ROOT/"tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        self.assertIn("verified_activation_score",js); self.assertIn("검증점수",js)
        data=registry.load_registry(ROOT)
        self.assertEqual({"pokemon","onepiece","naruto"},{row["id"] for row in registry.enabled_games("grading",root=ROOT)})
        self.assertEqual(8,JOB_COUNT); self.assertEqual(17,autonomy.screen_neural.INPUT_DIM); self.assertEqual(12,autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18,len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertFalse(data["policy"]["profit_guarantee"]); self.assertFalse(data["policy"]["investment_return_prediction"])
        self.assertFalse(data["policy"]["market_direction_prediction"]); self.assertTrue(data["policy"]["grading_requires_separate_calibration"])
if __name__=="__main__": unittest.main(verbosity=2)
