#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path

import purchase_intelligence
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v416_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V416.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v416_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v416.json"
BASE_SHA="d2ef5e21194feb54ace894623935c755284d0e27"
CANDIDATE_SHA="eacdd19291f35ff63d3208ec4446a41181dc5107"
LESSON_ID="TABLET-GPT-ELESTRALS-VERIFIED-WATCH-V416"

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV416Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V415.json",c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"]); self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(108,c["prior_required_lesson_count"]); self.assertEqual(109,c["current_required_lesson_count"])
        self.assertIn(436,c["current_required_merge_prs"]); self.assertIn(438,c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])

    def test_candidate_exactly_covers_elestrals_registry_change(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual(["tcg_game_registry.json"],x["watched_paths"])
        assert_v416_successor(self)

    def test_elestrals_starts_watch_and_is_evidence_promotable_not_profit_predicted(self):
        data=registry.load_registry(ROOT)
        row=next(item for item in data["games"] if item["id"]=="elestrals")
        self.assertEqual("watch",row["state"])
        self.assertEqual(0.0,row["activation_score"])
        self.assertEqual(2831,row["evidence"]["marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["official_live"])
        self.assertTrue(row["evidence"]["organized_play"])
        self.assertTrue(row["evidence"]["collector_rarity_signal"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertEqual("Elestrals",registry.canonical_game("엘레스트럴스 TCG",root=ROOT))
        value,terms=purchase_intelligence._resolve_purchase_game("엘레스트럴스 TCG")
        self.assertIsNone(value); self.assertEqual("",terms)
        review=registry.review_registry(
            ROOT,now=registry.dt.datetime(2026,10,4,6,0,tzinfo=registry.dt.timezone.utc),persist=False,
        )
        checked=next(item for item in review["reviewed"] if item["canonical"]=="Elestrals")
        self.assertTrue(checked["eligible"])
        self.assertEqual("promoted",checked["state"])
        self.assertGreaterEqual(checked["evidence_activation_score"],data["policy"]["min_auto_promotion_score"])
        self.assertFalse(review["profit_guaranteed"])
        self.assertFalse(review["market_direction_inferred"])

    def test_core_neural_grading_and_collection_safety_unchanged(self):
        data=registry.load_registry(ROOT)
        self.assertEqual({"pokemon","onepiece","naruto"},{row["id"] for row in registry.enabled_games("grading",root=ROOT)})
        self.assertEqual(8,JOB_COUNT)
        self.assertEqual(17,autonomy.screen_neural.INPUT_DIM)
        self.assertEqual(12,autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18,len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["investment_return_prediction"])
        self.assertFalse(data["policy"]["market_direction_prediction"])
        self.assertTrue(data["policy"]["grading_requires_separate_calibration"])

if __name__=="__main__": unittest.main(verbosity=2)
