import copy
import json
from pathlib import Path
import tempfile
import unittest
from execution import tablet_entity_store_v892 as store

PHOTO='a'*32
SOURCE='b'*32


def photo(**changes):
    return dict({'image_id':PHOTO,'source_record_id':None,'game_id':'pokemon','region':'JP','kind':'CARD','name':'Fixture','card_metadata':{'card_code':'SV1S-001'},'link_status':'NEEDS_EXACT_IDENTITY'},**changes)


def catalog(**changes):
    return dict(photo(image_id=None,source_record_id=SOURCE,link_status='NEEDS_IMAGE'),**changes)


class EntityStoreTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
    def state(self):return json.loads((self.root/store.FILENAME).read_text())
    def test_exact_pair_merges_separate_records_and_redirects_old_ids(self):
        rows=[photo(),catalog()];store.reconcile(rows,self.root)
        old={r['id'] for r in self.state()['records']}
        matched=photo(source_record_id=SOURCE,link_status='VERIFIED_PAIR',card_metadata={'card_code':'SV1S-001','set_code':'SV1S','language':'ja','printing':'Normal'})
        store.reconcile([matched],self.root);state=self.state()
        self.assertEqual(1,len(state['records']));record=state['records'][0]
        self.assertEqual({'photo:'+PHOTO,'catalog:'+SOURCE},set(record['aliases']))
        self.assertIn(record['id'],old)
        self.assertEqual({oldid:record['id'] for oldid in old-{record['id']}},state['redirects'])
        self.assertEqual('READY',record['completion'])
    def test_missing_information_accumulates_with_reconfirmation_not_false_completion(self):
        complete=photo(card_metadata={'card_code':'SV1S-001','generation':'9'})
        store.reconcile([complete],self.root);old=self.state()['records'][0]['id']
        view=store.project([photo()],self.root)
        self.assertEqual('9',view[0]['card_metadata']['generation'])
        self.assertEqual(['generation'],view[0]['retained_fields'])
        self.assertEqual(old,view[0]['canonical_id'])
        self.assertIn('RECONFIRM_RETAINED_FIELDS',{x['action'] for x in view[0]['work_items']})
    def test_same_name_is_not_a_match(self):
        store.reconcile([photo(),catalog()],self.root)
        self.assertEqual(2,len(self.state()['records']))
    def test_identity_change_preserves_previous_file(self):
        store.reconcile([photo()],self.root);path=self.root/store.FILENAME;before=path.read_bytes()
        for row in [photo(region='US'),photo(card_metadata={'card_code':'OTHER'})]:
            with self.assertRaises(ValueError):store.reconcile([row],self.root)
            self.assertEqual(before,path.read_bytes())
    def test_unverified_pair_and_duplicate_claim_are_rejected(self):
        for rows in [[photo(source_record_id=SOURCE)],[photo(),photo()]]:
            with self.assertRaises(ValueError):store.reconcile(rows,self.root)
        self.assertFalse((self.root/store.FILENAME).exists())
    def test_deleted_photo_is_not_resurrected_and_history_keeps_id(self):
        store.reconcile([photo()],self.root);ident=self.state()['records'][0]['id']
        store.reconcile([],self.root);record=self.state()['records'][0]
        self.assertIsNone(record['image_id']);self.assertFalse(record['present'])
        self.assertEqual([],store.project([],self.root))
        self.assertEqual(ident,store.project([photo()],self.root)[0]['canonical_id'])
    def test_read_projection_does_not_write_or_mutate_inputs(self):
        rows=[photo()];before=copy.deepcopy(rows)
        first=store.project(rows,self.root);self.assertEqual(before,rows)
        self.assertFalse((self.root/store.FILENAME).exists())
        self.assertEqual(first,store.project(rows,self.root))
    def test_work_items_are_attached_to_same_record(self):
        row=catalog(card_metadata={});store.reconcile([row],self.root)
        item=self.state()['records'][0]
        self.assertEqual({'COLLECT_EXACT_IMAGE','ENRICH_EXACT_METADATA'},{w['action'] for w in item['work_items']})
    def test_damaged_state_symlink_and_capacity_fail_closed(self):
        target=self.root/store.FILENAME;target.write_text('{broken')
        with self.assertRaises(ValueError):store.project([],self.root)
        target.unlink();other=self.root/'other';other.write_text('{}');target.symlink_to(other)
        with self.assertRaises(ValueError):store.reconcile([],self.root)
        target.unlink()
        with self.assertRaises(ValueError):store.reconcile([photo()]*(store.MAX_ROWS+1),self.root)

    def test_repeated_projection_cannot_promote_retained_values_to_current_evidence(self):
        store.reconcile([photo(card_metadata={'card_code':'SV1S-001','generation':'9'})],self.root)
        projected=store.project([photo()],self.root)
        store.reconcile(projected,self.root)
        record=self.state()['records'][0]
        self.assertEqual(['generation'],record['retained_fields'])
        self.assertIn('RECONFIRM_RETAINED_FIELDS',{x['action'] for x in record['work_items']})

    def run_actual_collector_wrapper(self):
        import importlib.util
        import sys
        import threading
        from types import SimpleNamespace
        from unittest.mock import patch
        state={'enabled':False}
        stats={'metadata_enriched':0,'metadata_repair_attempted':0,'issues':[],'errors':0,'deferred':False}
        auto=SimpleNamespace(collect_once=lambda *a:None,_LOCK=threading.RLock(),_BUDGET_CONTEXT=threading.local(),_state=lambda root:state,_save=lambda *a:None,_collect_once=lambda *a,**k:stats)
        auto.policy=SimpleNamespace(Budget=lambda data,save:SimpleNamespace(state=data,save=save))
        library=SimpleNamespace(storage_root=lambda:self.root,LOCK=threading.RLock(),_load=lambda root:{'items':[]})
        modules={'tablet_image_auto_v2':auto,'tablet_image_library_v1':library,
                 'execution.tablet_image_unified_v888':SimpleNamespace(repair_existing=lambda *a:{'enriched':0,'attempted':0,'issues':[],'deferred':False},export_html=lambda *a:None),
                 'execution.tablet_image_recheck_review_v887':SimpleNamespace(read_live=lambda root:{'ok':True,'unified_catalog':[photo()]})}
        path=Path(__file__).resolve().parents[1]/'tablet_unified_runtime_v889.py'
        with patch.dict(sys.modules,modules):
            spec=importlib.util.spec_from_file_location('reviewed_entity_collector',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            result=module.collect_once(self.root)
        self.assertIsNone(getattr(auto._BUDGET_CONTEXT,'current',None))
        return result,state

    def test_actual_collection_entry_persists_canonical_record(self):
        result,state=self.run_actual_collector_wrapper()
        self.assertTrue(result['canonical_store']['ok'])
        self.assertEqual(PHOTO,self.state()['records'][0]['image_id'])
        self.assertEqual(result,state['last_result'])

    def test_store_failure_keeps_previous_bytes_and_marks_collector_error(self):
        path=self.root/store.FILENAME;path.write_text('{broken')
        result,_=self.run_actual_collector_wrapper()
        self.assertFalse(result['canonical_store']['ok'])
        self.assertEqual(1,result['errors'])
        self.assertEqual('{broken',path.read_text())
