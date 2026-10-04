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
CANDIDATE_SHA="4928a3c1b0388d03cb80ab116b96ffb6ed1b4c00"
LESSON_ID="TABLET-GPT-TCG-REVIEW-EXPLAINABILITY-V421"

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
        self.assertIn(443,c["current_required_merge_prs"])

    def test_candidate_exactly_covers_review_explainability_runtime_changes(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(["auto_update_all.py","feature_contract.py","tablet_autonomy_dashboard_v400.js","tcg_game_registry.py"],x["watched_paths"])
        assert_v421_successor(self)

    def test_review_snapshot_is_explanatory_only_and_last_good_preserving(self):
        code=(ROOT/"tcg_game_registry.py").read_text(encoding="utf-8")
        updater=(ROOT/"auto_update_all.py").read_text(encoding="utf-8")
        js=(ROOT/"tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        self.assertIn("def _promotion_hold_reasons(",code)
        self.assertIn("def build_review_snapshot(",code)
        self.assertIn("def write_review_snapshot(",code)
        self.assertIn("review_snapshot_preserved",updater)
        self.assertIn('const GAME_REGISTRY_REVIEW_URL = "./tcg_registry_review.json"',js)
        self.assertIn("registryHoldReasonLabel",js)
        self.assertIn("검증점수 ",js)

    def test_core_neural_collection_and_prediction_safety_unchanged(self):
        data=registry.load_registry(ROOT)
        self.assertEqual({"pokemon","onepiece","naruto"},{r["id"] for r in registry.enabled_games("grading",root=ROOT)})
        self.assertEqual(8,JOB_COUNT)
        self.assertEqual(17,autonomy.screen_neural.INPUT_DIM)
        self.assertEqual(12,autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18,len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["investment_return_prediction"])
        self.assertFalse(data["policy"]["market_direction_prediction"])

if __name__=="__main__":
    unittest.main(verbosity=2)
