#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v422_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V422.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v422_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v422.json"
BASE_SHA="b5e43489bc53944f22734b56d1581e636683384f"
CANDIDATE_SHA="587d01bbc273b926c3a417ef8b2674702df36394"
LESSON_ID="TABLET-GPT-TCG-RUSH-OF-IKORR-WATCH-V422"

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV422Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V421.json",c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"]); self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(112,c["prior_required_lesson_count"]); self.assertEqual(113,c["current_required_lesson_count"])
        self.assertIn(444,c["current_required_merge_prs"]); self.assertEqual("SYNCED_VERIFIED",r["status"])

    def test_candidate_exactly_covers_rush_watch_seed(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual(["feature_contract.py","tcg_game_registry.json"],x["watched_paths"])
        assert_v422_successor(self)

    def test_rush_is_watch_only_and_market_depth_is_not_invented(self):
        data=registry.load_registry(ROOT)
        row=next(item for item in data["games"] if item["id"]=="rush-of-ikorr")
        self.assertEqual("watch",row["state"]); self.assertEqual(0,row["activation_score"])
        self.assertEqual(648,row["evidence"]["official_card_catalog_count"])
        self.assertIsNone(row["evidence"]["marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["market_depth_unverified"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertNotIn("Rush of Ikorr",{x["canonical"] for x in registry.enabled_games("purchase",root=ROOT)})
        self.assertIn("Rush of Ikorr",{x["canonical"] for x in registry.enabled_games("purchase",root=ROOT,include_watch=True)})

    def test_global_safety_contract_unchanged(self):
        data=registry.load_registry(ROOT)
        self.assertEqual({"pokemon","onepiece","naruto"},{row["id"] for row in registry.enabled_games("grading",root=ROOT)})
        self.assertEqual(8,JOB_COUNT)
        self.assertEqual(17,autonomy.screen_neural.INPUT_DIM); self.assertEqual(12,autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18,len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["investment_return_prediction"])
        self.assertFalse(data["policy"]["market_direction_prediction"])
        self.assertTrue(data["policy"]["grading_requires_separate_calibration"])

if __name__=="__main__": unittest.main(verbosity=2)
