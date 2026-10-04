#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v420_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V420.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v420_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v420.json"
BASE_SHA="6faaea1319623bc378be7209c54ad38cafc66707"
CANDIDATE_SHA="f821c57901e47707c80e5b69dbdcbeda9244871a"
LESSON_ID="TABLET-GPT-REGISTRY-MARKET-ROUTING-V420"

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV420Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V419.json",c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"]); self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(110,c["prior_required_lesson_count"]); self.assertEqual(111,c["current_required_lesson_count"])
        self.assertIn(442,c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])

    def test_candidate_exactly_covers_registry_market_purchase_routing(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual(["feature_contract.py","tablet_autonomy_dashboard_v400.js","tcg_updater.py"],x["watched_paths"])
        assert_v420_successor(self)

    def test_promoted_categories_are_routed_across_general_market_controls(self):
        js=(ROOT/"tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        self.assertIn('const marketRows = promotedRegistryGames(registry, "market")',js)
        self.assertIn('["v12Game","v13Game","analysisGame","tradeGame"]',js)
        self.assertIn('replaceRegistrySelect(document.getElementById(id), marketRows, "market", true)',js)
        self.assertIn('return String(row.canonical)',js)

    def test_purchase_api_delegates_game_authorization_to_registry(self):
        server=(ROOT/"tcg_updater.py").read_text(encoding="utf-8")
        start=server.index("if path=='/api/purchase-live-search':")
        end=server.index("if path=='/api/market-price':",start)
        route=server[start:end]
        self.assertIn("PURCHASE_LIVE_REGISTRY_DELEGATED",route)
        self.assertIn("from purchase_intelligence import search_web_signals",route)
        self.assertNotIn("game not in ('Pokemon','ONE PIECE','NARUTO')",route)
        self.assertIn("len(game)>80",route)

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
