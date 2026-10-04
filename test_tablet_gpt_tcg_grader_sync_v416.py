#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v416_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V416.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v416_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v416.json"
BASE_SHA="bfb2c3714d5cb81178adf685e84755b38cacb424"
CANDIDATE_SHA="c86616f9b385cff0a7681d6af52930a4054fd117"
LESSON_ID="TABLET-GPT-REGISTRY-MARKET-SURFACE-PARITY-V416"

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
        self.assertIn(436,c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])

    def test_candidate_exactly_covers_market_surface_parity(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual(["feature_contract.py","tablet_autonomy_dashboard_v400.js","tcg_updater.py"],x["watched_paths"])
        assert_v416_successor(self)

    def test_promoted_market_controls_and_purchase_api_are_registry_driven(self):
        dashboard=(ROOT/"tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        server=(ROOT/"tcg_updater.py").read_text(encoding="utf-8")
        self.assertIn('const marketRows = promotedRegistryGames(registry, "market")',dashboard)
        self.assertIn('["v12Game","v13Game","analysisGame","tradeGame"]',dashboard)
        self.assertIn('replaceRegistrySelect(document.getElementById(id), marketRows, "market", true)',dashboard)
        route=server[server.index("if path=='/api/purchase-live-search':"):server.index("if path=='/api/market-price':",server.index("if path=='/api/purchase-live-search':"))]
        self.assertIn("PURCHASE_LIVE_REGISTRY_DELEGATED",route)
        self.assertNotIn("game not in ('Pokemon','ONE PIECE','NARUTO')",route)
        self.assertIn("from purchase_intelligence import search_web_signals",route)

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
