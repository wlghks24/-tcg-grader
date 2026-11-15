from datetime import datetime, timezone
import hashlib
import threading
from unittest.mock import patch
from execution.tests import test_image_metadata_enrichment as fixtures
from execution import tablet_target_image_v895 as target
import tablet_image_auto_v2 as auto
import tablet_image_library_v1 as library


class TargetImageTests(fixtures.ImageMetadataTests):
    def report(self):
        return {'ok':True,'summary':{},'source_errors':[],'source_catalog':[{'source_record_id':'b'*32,'game_id':'pokemon','region':'JP','kind':'CARD','source_health':'HEALTHY','language':'ja','set_code':'sv1s','product_codes':['SV1S001'],'source_url':'https://api.tcgdex.net/v2/ja/cards/sv1s-001','source_checked_at':datetime.fromtimestamp(1000,timezone.utc).isoformat()}],'gap_queue':[{'direction':'CATALOG_NEEDS_IMAGE','source_record_id':'b'*32}]}
    def detail(self):
        return {'id':'sv1s-001','localId':'001','name':'Fixture','set':{'id':'sv1s','name':'Fixture Set'},'image':'https://assets.tcgdex.net/ja/sv/sv1s/001'}
    def collect(self,report=None,detail=None,state=None):
        state=auto._state(self.store) if state is None else state
        budget=auto.policy.Budget(state,lambda:None,clock=lambda:1000)
        auto._BUDGET_CONTEXT.current=budget
        try:
            with patch.object(auto,'fetch_json',return_value=self.detail() if detail is None else detail) as meta,patch.object(auto,'fetch_binary',return_value=self.png) as photo:
                result=target.collect(auto,library,self.repo,self.store,state,budget,threading.Event(),report=self.report() if report is None else report,clock=lambda:1000)
            return result,meta,photo,state
        finally:del auto._BUDGET_CONTEXT.current
    def test_catalog_information_saves_actual_image_and_metadata_together(self):
        result,meta,photo,state=self.collect()
        self.assertEqual(1,result['saved']);photo.assert_called_once_with('https://assets.tcgdex.net/ja/sv/sv1s/001/high.webp')
        row=library.list_images()['items'][0]
        self.assertEqual('sv1s-001',row['card_metadata']['card_code']);self.assertEqual('sv1s',row['card_metadata']['set_code'])
        self.assertNotIn('printing',row['card_metadata'])
        self.assertTrue(library.get_image(row['id'])[1]);self.assertTrue(state['completed'])
    def test_repeated_cycle_and_owner_deleted_image_never_redownload(self):
        _,_,_,state=self.collect();row=library.list_images()['items'][0];library.delete_image(row['id'])
        result,meta,photo,_=self.collect(state=state)
        self.assertEqual(0,result['attempted']);meta.assert_not_called();photo.assert_not_called()
    def test_wrong_card_set_or_image_path_never_saves(self):
        for field,value in [('id','wrong'),('set',{'id':'other'}),('image','https://assets.tcgdex.net/en/sv/sv1s/001'),('image','https://assets.tcgdex.net/ja/sv/sv1s/002')]:
            detail=self.detail();detail[field]=value
            result,_,photo,_=self.collect(detail=detail)
            self.assertEqual(0,result['saved']);photo.assert_not_called()
        self.assertEqual(0,library.list_images()['count'])
    def test_stale_unsupported_locale_or_non_api_source_does_not_fetch(self):
        for field,value in [('region','KR'),('source_url','https://market.example/card'),('source_checked_at','2020-01-01T00:00:00Z'),('language','en')]:
            report=self.report();report['source_catalog'][0][field]=value
            result,meta,photo,_=self.collect(report=report)
            self.assertEqual(0,result['attempted']);meta.assert_not_called();photo.assert_not_called()
    def test_failed_detail_waits_before_retry(self):
        result,_,_,state=self.collect(detail={'id':'wrong'})
        self.assertEqual(1,result['attempted'])
        result,meta,photo,_=self.collect(state=state)
        self.assertEqual(0,result['attempted']);meta.assert_not_called();photo.assert_not_called()
    def test_existing_image_metadata_path_prevents_duplicate_download(self):
        self.save({})
        result,meta,photo,_=self.collect()
        self.assertEqual(0,result['attempted']);meta.assert_not_called();photo.assert_not_called()
    def test_shared_real_request_quota_defers_before_connection(self):
        state=auto._state(self.store);state['image_budget_events']=[{'at':1000,'kind':'request','provider':'TCGdex','bytes':0} for _ in range(80)]
        budget=auto.policy.Budget(state,lambda:None,clock=lambda:1000)
        auto._BUDGET_CONTEXT.current=budget
        try:
            with patch.object(auto.urllib.request,'build_opener') as opener:
                result=target.collect(auto,library,self.repo,self.store,state,budget,threading.Event(),report=self.report(),clock=lambda:1000)
            self.assertTrue(result['deferred']);opener.assert_not_called()
        finally:del auto._BUDGET_CONTEXT.current
    def test_one_target_per_pass_even_with_multiple_missing_cards(self):
        report=self.report();second=dict(report['source_catalog'][0],source_record_id='c'*32)
        report['source_catalog'].append(second);report['gap_queue'].append({'direction':'CATALOG_NEEDS_IMAGE','source_record_id':'c'*32})
        result,meta,photo,_=self.collect(report=report)
        self.assertEqual(1,result['attempted']);self.assertEqual(1,result['saved']);self.assertEqual(1,meta.call_count);self.assertEqual(1,photo.call_count)
    def test_reverse_image_to_metadata_repairs_actual_private_record_without_photo_rewrite(self):
        from execution.tablet_image_unified_v888 import repair_existing
        saved=self.save({});before=library.get_image(saved['id'])
        state=auto._state(self.store);budget=auto.policy.Budget(state,lambda:None,clock=lambda:1000)
        auto._BUDGET_CONTEXT.current=budget
        try:
            with patch.object(auto,'fetch_json',return_value=self.detail()),patch.object(auto,'fetch_binary') as download:
                result=repair_existing(auto,self.store,state,library._load(self.store)['items'],budget,threading.Event(),clock=lambda:1000)
            self.assertEqual(1,result['enriched']);download.assert_not_called()
            self.assertEqual('001',library.list_images()['items'][0]['card_metadata']['card_number'])
            self.assertEqual(before,library.get_image(saved['id']))
        finally:del auto._BUDGET_CONTEXT.current
