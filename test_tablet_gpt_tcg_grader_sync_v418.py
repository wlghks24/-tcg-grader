#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v418_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V418.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v418_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v418.json"
BASE_SHA="d2ef5e21194feb54ace894623935c755284d0e27"
CANDIDATE_SHA="71c420cd369e9a4e9e893e5880da20a0f44edc7d"
LESSON_ID="TABLET-GPT-AUTO-WATCH-LIFECYCLE-ELESTRALS-V418"

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV418Tests(unittest.TestCase):
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

    def test_candidate_exactly_covers_registry_watch_lifecycle(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual(["tcg_game_registry.json","tcg_game_registry.py"],x["watched_paths"])
        assert_v418_successor(self)

    def test_auto_watch_lifecycle_is_bounded_and_manual_watch_is_protected(self):
        data=registry.load_registry(ROOT)
        self.assertEqual(180,data["policy"]["auto_watch_retire_after_days"])
        code=(ROOT/"tcg_game_registry.py").read_text(encoding="utf-8")
        self.assertIn("def _auto_watch_retirable(",code)
        self.assertIn('evidence.get("auto_watch_seeded") is not True',code)
        self.assertIn('"retired_auto_watch_games": retired_auto_watch_games',code)
        self.assertIn("rows = active_rows",code)

    def test_elestrals_is_verified_market_surface_not_grading(self):
        data=registry.load_registry(ROOT)
        row=next(item for item in data["games"] if item["id"]=="elestrals")
        self.assertEqual("promoted",row["state"])
        self.assertGreaterEqual(row["activation_score"],data["policy"]["min_auto_promotion_score"])
        self.assertGreaterEqual(row["evidence"]["marketplace_catalog_count"],data["policy"]["min_marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["official_live"])
        self.assertTrue(row["evidence"]["organized_play"])
        self.assertTrue(row["evidence"]["collector_rarity_signal"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertTrue(row["official_source"].startswith("https://"))
        self.assertTrue(row["market_source"].startswith("https://"))

    def test_core_neural_and_grading_safety_remain_unchanged(self):
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
