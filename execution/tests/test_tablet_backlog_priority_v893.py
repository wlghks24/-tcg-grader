from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from execution import tablet_entity_store_v892 as entities
from execution import tablet_backlog_priority_v893 as backlog


class BacklogPriorityTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
    def rows(self,count=1):
        return [{'image_id':None,'source_record_id':f'{i:032x}','game_id':'pokemon','region':'JP','kind':'CARD','card_metadata':{},'link_status':'NEEDS_IMAGE'} for i in range(count)]
    def test_real_canonical_work_reaches_original_rotation(self):
        entities.reconcile(self.rows(),self.root)
        calls=[]
        def original(state,priority):calls.append((state,priority));return iter(['original-provider'])
        auto=SimpleNamespace(_candidate_batches=original,SUPPORTED={('pokemon','JP'):'TCGdex'})
        backlog.install(auto,lambda:self.root)
        state={'cross_cycle':2};base={('pokemon','JP'):8}
        self.assertEqual(['original-provider'],list(auto._candidate_batches(state,base)))
        self.assertIs(state,calls[0][0]);self.assertEqual(9,calls[0][1][('pokemon','JP')]);self.assertEqual(8,base[('pokemon','JP')])
    def test_bonus_is_bounded_and_unsupported_provider_never_added(self):
        entities.reconcile(self.rows(5),self.root)
        self.assertEqual({('pokemon','JP'):2},backlog.pending_priorities(self.root,{('pokemon','JP')}))
        self.assertEqual({},backlog.pending_priorities(self.root,{('pokemon','KR')}))
    def test_absent_history_does_not_trigger_collection(self):
        entities.reconcile(self.rows(),self.root);entities.reconcile([],self.root)
        self.assertEqual({},backlog.pending_priorities(self.root,{('pokemon','JP')}))
    def test_corrupt_backlog_preserves_original_rotation(self):
        (self.root/entities.FILENAME).write_text('{broken')
        auto=SimpleNamespace(_candidate_batches=lambda state,p:p,SUPPORTED={('pokemon','JP')})
        backlog.install(auto,lambda:self.root)
        self.assertEqual({('pokemon','JP'):3},auto._candidate_batches({}, {('pokemon','JP'):3}))
    def test_install_idempotent_and_get_does_not_write(self):
        auto=SimpleNamespace(_candidate_batches=lambda s,p:p,SUPPORTED=set())
        backlog.install(auto,lambda:self.root);first=auto._candidate_batches
        backlog.install(auto,lambda:self.root);self.assertIs(first,auto._candidate_batches)
        self.assertEqual({},auto._candidate_batches({}));self.assertEqual([],list(self.root.iterdir()))

    def test_actual_provider_rotation_keeps_fair_cycles_and_prioritizes_backlog(self):
        import importlib.util
        import sys
        from unittest.mock import patch
        path=Path(__file__).resolve().parents[2]/'tablet_image_auto_v2.py'
        policy=SimpleNamespace(RUN_IMAGES=36,RUN_BYTES=24*1024*1024,PERIOD_SECONDS=21600)
        modules={'tablet_image_library_v1':SimpleNamespace(MAX_IMAGE_BYTES=5*1024*1024),'execution.tablet_image_collection_policy':policy}
        with patch.dict(sys.modules,modules):
            spec=importlib.util.spec_from_file_location('reviewed_provider_rotation',path)
            auto=importlib.util.module_from_spec(spec);spec.loader.exec_module(auto)
        entities.reconcile(self.rows(),self.root)
        original=auto._candidate_batches
        backlog.install(auto,lambda:self.root)
        for cycle in (0,1):
            state={'cross_cycle':cycle,'next_source_index':0,'pages':{}}
            self.assertEqual(list(original(state,{})),list(auto._candidate_batches(state,{})))
        state={'cross_cycle':2,'next_source_index':0,'pages':{}}
        ordered=list(auto._candidate_batches(state,{}))
        self.assertEqual(('pokemon','JP'),ordered[0][3:])
        self.assertEqual(len(auto.SUPPORTED),len(ordered))
