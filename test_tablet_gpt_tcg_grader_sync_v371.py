import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
import multi_market_price_collector as market
import update_exchange_rates as updater
ROOT=Path(__file__).resolve().parent
SOURCE='a00ebfd3888740ee50c5e86c8ee6008fe8a54908'
CANDIDATE='15d28fbf238fb08e34fd8c1d147894cf13a2740e'
PRIOR=ROOT/'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v370_delta.json'
DELTA=ROOT/'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v371_delta.json'
RECEIPT=ROOT/'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v371.json'
PRIOR_CONTRACT=ROOT/'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V370.json'
CONTRACT=ROOT/'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V371.json'
EXPECTED_DIGEST='48e22357c3e6a66bad4f0c920004db394b7f7aae8de3139c2a04fb9889c81b5c'
def read(path): return json.loads(path.read_text(encoding='utf-8'))
def watched_paths(contract,source,head='HEAD'):
    watch=contract['freshness_watch']; exact=set(watch['exact_paths']); prefixes=tuple(watch['path_prefixes']); excluded=set(watch['exclude_paths']); changed=subprocess.check_output(['git','diff','--name-only',f'{source}..{head}'],text=True).splitlines(); return sorted(path for path in changed if path not in excluded and (path in exact or path.startswith(prefixes)))
class TabletGptTcgGraderSyncV371(unittest.TestCase):
    def test_lineage_digest_receipt_and_merge_anchor(self):
        prior,delta,receipt,pc,contract=map(read,(PRIOR,DELTA,RECEIPT,PRIOR_CONTRACT,CONTRACT)); self.assertEqual(prior['lesson_digest_sha256'],delta['prior_lesson_digest_sha256']); self.assertEqual(delta['prior_lesson_digest_sha256'],receipt['prior_lesson_digest_sha256']); self.assertEqual(SOURCE,delta['source_main_sha']); self.assertEqual(SOURCE,receipt['source_main_sha']); self.assertEqual([355],[row['pr'] for row in delta['covered_merges']]); self.assertEqual(SOURCE,delta['covered_merges'][0]['merge_sha']); self.assertEqual(set(contract['current_required_merge_prs']),set(pc['current_required_merge_prs'])|{355}); self.assertEqual(pc['current_required_lesson_count'],contract['prior_required_lesson_count']); self.assertEqual(contract['prior_required_lesson_count']+1,contract['current_required_lesson_count']); raw=json.dumps(delta['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':')); value=hashlib.sha256(raw.encode()).hexdigest(); self.assertEqual(EXPECTED_DIGEST,value); self.assertEqual(value,delta['lesson_digest_sha256']); self.assertEqual(value,receipt['delta_lesson_digest_sha256']); self.assertEqual([row['lesson_id'] for row in delta['lessons']],receipt['accepted_lesson_ids']); self.assertEqual('SYNCED_VERIFIED',receipt['status']); self.assertEqual('TABLET_GPT_TCG_GRADER_MATCH',receipt['verification']['verified_result']); self.assertFalse(receipt['verification']['physical_tablet_runtime_verified']); self.assertFalse(receipt['verification']['physical_drive_readback_verified']); subprocess.run(['git','merge-base','--is-ancestor',SOURCE,'HEAD'],check=True); subprocess.run(['git','merge-base','--is-ancestor',CANDIDATE,'HEAD'],check=True)
    def test_exact_candidate_scope_and_complete_generation(self):
        contract=read(CONTRACT); candidate=contract['candidate_sync']; self.assertEqual(SOURCE,candidate['base_main_sha']); self.assertEqual(CANDIDATE,candidate['candidate_commit']); expected=['multi_market_price_collector.py']; self.assertEqual(expected,watched_paths(contract,SOURCE,CANDIDATE)); self.assertEqual(expected,sorted(candidate['watched_paths'])); generation={'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V371.json','TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v371_delta.json','TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v371.json','test_tablet_gpt_tcg_grader_sync_v371.py'}; self.assertEqual(generation,set(candidate['generation_files'])); self.assertTrue(generation.issubset(set(contract['freshness_watch']['exclude_paths']))); self.assertTrue(candidate['requires_exact_watched_path_match']); self.assertTrue(candidate['post_merge_coverage_allowed']); self.assertEqual([],watched_paths(contract,CANDIDATE))
    def test_future_fx_is_strictly_held_at_both_boundaries(self):
        future=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=5)).isoformat(); self.assertFalse(market._fresh_fx_timestamp(future)); raw=[{'quote':'KRW','rate':1360.0,'updated_at':future},{'quote':'JPY','rate':158.1,'updated_at':future}];
        with self.assertRaises(ValueError): updater.parse_source_timestamp(raw)
        market_text=(ROOT/'multi_market_price_collector.py').read_text(encoding='utf-8'); updater_text=(ROOT/'update_exchange_rates.py').read_text(encoding='utf-8'); self.assertNotIn('FX_MAX_FUTURE_SKEW_SECONDS',market_text); self.assertIn('return 0 <= age <= FX_MAX_AGE_SECONDS',market_text); self.assertNotIn('-6*60*60 <= age',updater_text); self.assertIn('if not (0 <= age <= 72*60*60):',updater_text); rules=read(CONTRACT)['rules']; self.assertIs(rules['future_fx_timestamp_must_hold'],True); self.assertIs(rules['fx_future_skew_allowance_forbidden'],True); self.assertIs(rules['fx_max_age_72h_must_remain_enforced'],True)
if __name__=='__main__': unittest.main(verbosity=2)
