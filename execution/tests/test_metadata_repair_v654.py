"""Repair old metadata without revisiting its catalogue page or image download."""
import hashlib
import threading
from unittest.mock import patch
from execution import tablet_image_metadata_repair as repair
from execution.tests import test_image_metadata_enrichment as fixtures
import tablet_image_auto_v2 as auto
import tablet_image_library_v1 as library


class MetadataRepairTests(fixtures.ImageMetadataTests):
    def run_repair(self, state, detail, *, now=1000):
        budget=auto.policy.Budget(state,lambda:None,clock=lambda:now)
        with patch.object(auto,'fetch_json',return_value=detail) as fetch:
            result=repair.repair(auto,self.store,state,library._load(self.store)['items'],budget,
                                 threading.Event(),clock=lambda:now)
        return result,fetch

    def test_old_image_is_repaired_when_its_page_is_not_visited(self):
        saved=self.save();state=auto._state(self.store)
        state['completed'][hashlib.sha256(self.row['key'].encode()).hexdigest()]={'id':saved['id']}
        auto._save(self.store,state)
        detail={'id':'sv1s-001','set':{'id':'sv1s'},'localId':'001'}
        with patch.object(auto,'_candidate_batches',return_value=[]),patch.object(auto,'fetch_json',return_value=detail) as fetch,patch.object(auto,'fetch_binary') as image:
            result=auto.collect_once(self.repo,sleeper=lambda _:None)
        self.assertEqual(result['metadata_enriched'],1)
        self.assertEqual(result['metadata_repair_pending'],0)
        self.assertEqual(result['saved'],0);image.assert_not_called()
        fetch.assert_called_once_with('https://api.tcgdex.net/v2/ja/cards/sv1s-001')

    def test_failed_detail_waits_six_hours_and_then_retries(self):
        self.save();state=auto._state(self.store)
        failed,fetch=self.run_repair(state,{'id':'wrong'})
        self.assertEqual(failed['attempted'],1);self.assertEqual(failed['pending'],1)
        waiting,fetch=self.run_repair(state,{},now=1001)
        self.assertEqual(waiting['attempted'],0);fetch.assert_not_called()
        done,fetch=self.run_repair(state,{'id':'sv1s-001','set':{'id':'sv1s'}},now=22600)
        self.assertEqual(done['enriched'],1)

    def test_failure_is_not_retried_again_by_the_same_page(self):
        saved=self.save();state=auto._state(self.store)
        state['completed'][hashlib.sha256(self.row['key'].encode()).hexdigest()]={'id':saved['id']}
        auto._save(self.store,state)
        with patch.object(auto,'_candidate_batches',return_value=[(0,'pokemon|JP',1,'pokemon','JP')]),patch.object(auto,'candidates_pokemon',return_value=[self.row]),patch.object(auto,'fetch_json',return_value={'id':'wrong'}) as fetch:
            result=auto.collect_once(self.repo,sleeper=lambda _:None)
        self.assertEqual(fetch.call_count,1);self.assertEqual(result['metadata_repair_pending'],1)

    def test_deleted_and_conflicting_locale_records_never_fetch(self):
        saved=self.save();library.delete_image(saved['id']);state=auto._state(self.store)
        result,fetch=self.run_repair(state,{})
        self.assertEqual(result['attempted'],0);fetch.assert_not_called()
        self.save({'card_code':'sv1s-001','language':'en'})
        result,fetch=self.run_repair(state,{})
        self.assertEqual(result['attempted'],0);fetch.assert_not_called()

    def test_budget_deferral_is_preserved_without_enrichment(self):
        self.save();state=auto._state(self.store);budget=auto.policy.Budget(state,lambda:None,clock=lambda:1000)
        with patch.object(auto,'_complete_candidate_metadata',side_effect=auto.policy.Deferred('quota')):
            result=repair.repair(auto,self.store,state,library._load(self.store)['items'],budget,threading.Event(),clock=lambda:1000)
        self.assertTrue(result['deferred']);self.assertEqual(result['enriched'],0)

    def test_invalid_retry_history_stops_before_network(self):
        self.save();state=auto._state(self.store);state['metadata_repairs']={'x':{'next_at':True}}
        with self.assertRaises(ValueError):self.run_repair(state,{})

    def test_empty_metadata_uses_exact_stored_provider_key_and_verified_response(self):
        self.save({});state=auto._state(self.store)
        result,fetch=self.run_repair(state,{'id':'sv1s-001','set':{'id':'sv1s'},'localId':'001'})
        self.assertEqual(result['enriched'],1)
        fetch.assert_called_once_with('https://api.tcgdex.net/v2/ja/cards/sv1s-001')
        metadata=library.list_images()['items'][0]['card_metadata']
        self.assertEqual(metadata['card_code'],'sv1s-001');self.assertEqual(metadata['set_code'],'sv1s')

    def test_four_request_cap_and_waiting_cards_do_not_starve_next_card(self):
        self.save();state=auto._state(self.store);record=library._load(self.store)['items'][0]
        records=[dict(record,id=f'{i:032x}',source_id=f'pokemon/ja/sv1s-00{i}',
                      card_metadata={'card_code':f'sv1s-00{i}','language':'ja'}) for i in range(1,6)]
        budget=auto.policy.Budget(state,lambda:None,clock=lambda:1000)
        with patch.object(auto,'_complete_candidate_metadata',side_effect=auto.ProviderError('offline')) as detail:
            first=repair.repair(auto,self.store,state,records,budget,threading.Event(),clock=lambda:1000)
            self.assertEqual(detail.call_count,4);self.assertEqual(first['pending'],5)
            detail.reset_mock()
            second=repair.repair(auto,self.store,state,records,budget,threading.Event(),clock=lambda:1001)
            self.assertEqual(detail.call_count,1);self.assertEqual(second['attempted'],1)

    def test_real_fetch_path_obeys_existing_request_quota(self):
        self.save();state=auto._state(self.store)
        import time
        state['image_budget_events']=[{'at':time.time(),'kind':'request','provider':'TCGdex','bytes':0} for _ in range(80)]
        auto._save(self.store,state)
        with patch.object(auto,'_candidate_batches',return_value=[]),patch.object(auto.urllib.request,'build_opener') as opener:
            result=auto.collect_once(self.repo,sleeper=lambda _:None)
        opener.assert_not_called();self.assertTrue(result['deferred'])
        self.assertEqual(result['metadata_enriched'],0)

    def test_repair_dependency_is_in_verified_runtime_delivery(self):
        import tablet_runtime_manifest as manifest
        self.assertIn("execution/tablet_image_metadata_repair.py", manifest.ACTIVE_RUNTIME_FILES)
