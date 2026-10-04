#!/usr/bin/env python3
import hashlib, json, unittest
from pathlib import Path
import tablet_autonomous_evolution_v400 as autonomy
import tcg_game_registry as registry
import promoted_tcg_source_monitor_v413 as monitor
import update_purchase_sources as purchase
from collection_job_contract import JOB_COUNT
from sync_v376_successor_test_support import assert_v413_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V413.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v413_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v413.json"
BASE_SHA="393fe2a43d0ef330a2f47e1b976fa86519beb220"
CANDIDATE_SHA="83ed1943dcdd25879505adf50a08449d22707b7b"
LESSON_ID="TABLET-GPT-REGISTRY-FIRST-MARKET-EXPANSION-V413"

def load(path): return json.loads(path.read_text(encoding="utf-8"))
def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV413Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V412.json",c["prior_contract"])
        self.assertEqual(BASE_SHA,d["source_main_sha"]); self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(105,c["prior_required_lesson_count"]); self.assertEqual(106,c["current_required_lesson_count"])
        self.assertIn(431,c["current_required_merge_prs"]); self.assertEqual("SYNCED_VERIFIED",r["status"])

    def test_candidate_exactly_covers_v413_runtime_policy(self):
        c=load(CONTRACT); x=c["candidate_sync"]
        self.assertEqual(BASE_SHA,x["base_main_sha"]); self.assertEqual(CANDIDATE_SHA,x["candidate_commit"])
        self.assertEqual(CANDIDATE_SHA,x["functional_candidate_commit"])
        self.assertEqual(["auto_update_all.py","feature_contract.py","promoted_tcg_source_monitor_v413.py","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.js","tablet_runtime_manifest.py","tcg_game_registry.json","tcg_game_registry.py","update_purchase_sources.py"],x["watched_paths"])
        assert_v413_successor(self)

    def test_registry_first_categories_and_neural_boundaries(self):
        data=registry.load_registry(ROOT)
        promoted={row["canonical"] for row in data["games"] if row["state"] in {"core","promoted"}}
        watch={row["canonical"] for row in data["games"] if row["state"]=="watch"}
        self.assertTrue({"Magic: The Gathering","Yu-Gi-Oh!","Digimon Card Game"}.issubset(promoted))
        self.assertTrue({
            "Flesh and Blood TCG","Weiß Schwarz","Cardfight!! Vanguard","hololive OFFICIAL CARD GAME",
            "Shadowverse: Evolve","Grand Archive TCG","Final Fantasy TCG","Sorcery: Contested Realm",
        }.issubset(watch))
        self.assertEqual({"pokemon","onepiece","naruto"},{row["id"] for row in registry.enabled_games("grading",root=ROOT)})
        self.assertEqual(8,JOB_COUNT)
        self.assertEqual(17,autonomy.screen_neural.INPUT_DIM); self.assertEqual(12,autonomy.screen_neural.HIDDEN_DIM); self.assertEqual(18,len(autonomy.screen_neural.FEATURE_KEYS))
        self.assertFalse(data["policy"]["profit_guarantee"]); self.assertFalse(data["policy"]["market_direction_prediction"])
        self.assertTrue(data["policy"]["grading_requires_separate_calibration"])
        review=registry.review_registry(ROOT, now=registry.dt.datetime(2026,10,4,4,0,tzinfo=registry.dt.timezone.utc), persist=False)
        self.assertTrue(review["activation_score_uses_verified_evidence"])
        self.assertFalse(review["activation_score_uses_price_direction"])
        self.assertFalse(review["activation_score_uses_profit_prediction"])
        self.assertFalse(review["activation_score_uses_user_behavior"])
        self.assertTrue(autonomy.SAFETY["promoted_tcg_source_monitor_v413_enabled"])
        self.assertFalse(autonomy.SAFETY["promoted_tcg_source_monitor_market_direction_invention"])
        self.assertFalse(autonomy.SAFETY["promoted_tcg_source_monitor_profit_guarantee"])
        self.assertFalse(autonomy.SAFETY["promoted_tcg_source_monitor_stock_claim"])
        self.assertEqual(2_000_000, monitor.MAX_RESPONSE_BYTES)
        promoted_purchase = {row["purchase_value"] for row in registry.enabled_games("purchase", root=ROOT)}
        self.assertTrue(promoted_purchase.issubset(purchase.GAMES))

    def test_dashboard_validates_declared_allowed_games_not_fixed_core_three(self):
        js=(ROOT/"tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        self.assertIn('declaredGames.every((key) => Number.isFinite(Number(gameScores[key])))',js)
        self.assertNotIn('["Pokémon","ONE PIECE","NARUTO"].every((key) => Number.isFinite(Number(gameScores[key])))',js)
        self.assertIn('registryLabel || MARKET_LENS_GAME_LABELS[key] || key',js)

if __name__=="__main__": unittest.main(verbosity=2)
