#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v414_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V414.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v414_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v414.json"
BASE_SHA="34bd952f83d5735d5c7f73a3db8af3316cf3d6a4"
CANDIDATE_SHA="c9b2ae26d7c774a4cce6376b67972f65b99d8cf4"
LESSON_ID="TABLET-GPT-AUTONOMOUS-UNKNOWN-TCG-WATCH-SEEDING-V414"

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV414Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V413.json",c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"]); self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(106,c["prior_required_lesson_count"]); self.assertEqual(107,c["current_required_lesson_count"])
        self.assertIn(433,c["current_required_merge_prs"]); self.assertEqual("SYNCED_VERIFIED",r["status"])

    def test_candidate_exactly_covers_v414_runtime_policy(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual([
            "feature_contract.py","tablet_autonomous_evolution_v400.py",
            "tablet_autonomy_dashboard_v400.js","tcg_game_registry.json","tcg_game_registry.py",
        ],x["watched_paths"])
        assert_v414_successor(self)

    def test_unknown_watch_seeding_and_core_neural_safety(self):
        data=registry.load_registry(ROOT)
        watch={row["canonical"] for row in data["games"] if row["state"]=="watch"}
        self.assertTrue({"Godzilla Card Game","Palworld OFFICIAL CARD GAME","Cyberpunk TCG"}.issubset(watch))
        for name in ("Godzilla Card Game","Palworld OFFICIAL CARD GAME","Cyberpunk TCG"):
            row=next(item for item in data["games"] if item["canonical"]==name)
            self.assertFalse(row["capabilities"]["grading"])
        self.assertEqual({"pokemon","onepiece","naruto"},{row["id"] for row in registry.enabled_games("grading",root=ROOT)})
        self.assertEqual(8,JOB_COUNT)
        self.assertEqual(17,autonomy.screen_neural.INPUT_DIM)
        self.assertEqual(12,autonomy.screen_neural.HIDDEN_DIM)
        self.assertEqual(18,len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertTrue(autonomy.SAFETY["autonomous_tcg_unknown_auto_watch_enabled"])
        self.assertTrue(autonomy.SAFETY["autonomous_tcg_unknown_auto_watch_fresh_official_https_required"])
        self.assertTrue(autonomy.SAFETY["autonomous_tcg_unknown_auto_watch_independent_market_https_required"])
        self.assertFalse(autonomy.SAFETY["autonomous_tcg_unknown_auto_watch_auto_promotion"])
        self.assertFalse(autonomy.SAFETY["autonomous_tcg_unknown_auto_watch_grading_enabled"])
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["market_direction_prediction"])

    def test_registry_code_has_independent_source_fail_closed_gate(self):
        code=(ROOT/"tcg_game_registry.py").read_text(encoding="utf-8")
        self.assertIn("def _provisional_watch_row(",code)
        self.assertIn("fresh_official_source_required",code)
        self.assertIn("fresh_independent_market_source_required",code)
        self.assertIn("independent_source_hosts_required",code)
        self.assertIn('"auto_watch_created_games": auto_watch_created_games',code)

if __name__=="__main__": unittest.main(verbosity=2)
