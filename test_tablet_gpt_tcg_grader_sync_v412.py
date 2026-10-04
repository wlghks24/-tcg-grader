#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v412_successor
ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V412.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v412_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v412.json"
BASE_SHA="bbb4e6f85f3d5c658ba0f9acd2f56af92985d07d"
CANDIDATE_SHA="2fc7c5a012ac480295b9630a4ebb5d0350ff307e"
LESSON_ID="TABLET-GPT-AUTONOMOUS-VERIFIED-TCG-DISCOVERY-V412"
def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
class TabletGptTcgGraderSyncV412Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V411.json",c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"]);self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"]);self.assertEqual(104,c["prior_required_lesson_count"]);self.assertEqual(105,c["current_required_lesson_count"]);self.assertIn(430,c["current_required_merge_prs"]);self.assertEqual("SYNCED_VERIFIED",r["status"])
    def test_candidate_exactly_covers_v412_runtime_policy(self):
        c=load(CONTRACT);x=c["candidate_sync"];self.assertEqual(BASE_SHA,x["base_main_sha"]);self.assertEqual(CANDIDATE_SHA,x["candidate_commit"]);self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"]);self.assertEqual(["sw.js","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.js","tablet_runtime_manifest.py","tcg_updater.py"],x["watched_paths"]);assert_v412_successor(self)
    def test_runtime_registry_and_neural_boundaries(self):
        data=registry.load_registry(ROOT);promoted={r["canonical"] for r in data["games"] if r["state"] in {"core","promoted"}}
        self.assertTrue({"Pokémon","ONE PIECE","NARUTO","GUNDAM CARD GAME","UNION ARENA","DRAGON BALL SUPER: FUSION WORLD","Disney Lorcana","Star Wars: Unlimited","Riftbound: League of Legends"}.issubset(promoted))
        self.assertEqual(8,JOB_COUNT);self.assertEqual(17,autonomy.screen_neural.INPUT_DIM);self.assertEqual(12,autonomy.screen_neural.HIDDEN_DIM);self.assertEqual(18,len(autonomy.screen_neural.FEATURE_KEYS));self.assertFalse(data["policy"]["profit_guarantee"]);self.assertFalse(data["policy"]["market_direction_prediction"]);self.assertTrue(data["policy"]["grading_requires_separate_calibration"]);self.assertTrue(autonomy.SAFETY["autonomous_tcg_category_discovery_enabled"]);self.assertFalse(autonomy.SAFETY["autonomous_tcg_category_source_code_generation"])
if __name__=="__main__": unittest.main(verbosity=2)
