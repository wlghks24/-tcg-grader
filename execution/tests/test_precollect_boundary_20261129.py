"""Real-import offline stage boundary regression; no device state is written."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import auto_update_all as automatic
import tcg_game_registry as registry
import tcg_updater as updater


class PrecollectBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.allowed={job[2] for job in automatic.JOBS}
        self.rows=[{'file':name,'ok':True,'collection_errors':[]} for name in sorted(self.allowed)]

    def test_exact_eight_jobs(self):
        self.assertEqual(8,len(self.allowed))
        self.assertTrue(updater._valid_precollect_results(self.rows,self.allowed))
        for rows in (self.rows[:-1],self.rows[:-1]+[self.rows[0]],self.rows+[self.rows[0]],None):
            self.assertFalse(updater._valid_precollect_results(rows,self.allowed))

    def test_wrong_result_types_never_approved(self):
        for field,values in (('ok',('false',1,None,[])),('collection_errors',('error',None,[False],[' ']))):
            for value in values:
                rows=copy.deepcopy(self.rows);rows[0][field]=value
                with self.subTest(field=field,value=value):
                    self.assertFalse(updater._valid_precollect_results(rows,self.allowed))
        rows=copy.deepcopy(self.rows);del rows[0]['collection_errors']
        self.assertFalse(updater._valid_precollect_results(rows,self.allowed))
        rows[0]['ok']=False
        self.assertTrue(updater._valid_precollect_results(rows,self.allowed))

    def test_registry_exact_bytes_and_scope_hold(self):
        raw=registry.REGISTRY_PATH.read_bytes()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stage=root/'stage';stage.mkdir()
            live=root/registry.REGISTRY_PATH.name;staged=stage/live.name
            live.write_bytes(raw);staged.write_bytes(raw)
            with patch.object(updater,'BASE',str(root)),patch.object(updater,'PRECOLLECT_STAGE',str(stage)):
                self.assertTrue(updater._precollect_registry_matches_live())
                staged.write_bytes(raw+b'\n')
                self.assertFalse(updater._precollect_registry_matches_live())
                staged.write_bytes(raw)
                hold=stage/'.tcg_reliability_state'/'registry_scope_hold'
                hold.mkdir(parents=True)
                self.assertFalse(updater._precollect_registry_matches_live())
                hold.rmdir()
                live.write_text('{}');staged.write_text('{}')
                self.assertFalse(updater._precollect_registry_matches_live())

    def test_stale_or_partial_stage_uses_all_existing_jobs_without_copy(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);stage=root/'stage';stage.mkdir()
            status=root/'precollect_status.json'
            for rows,stamp in ((self.rows,'old'),(self.rows[:-1],updater.time.strftime('%Y-%m-%dT%H:%M:%S%z',updater.time.localtime(1700000000)))):
                status.write_text(json.dumps({'state':'ready','due_at':stamp}))
                (stage/'auto_update_report.json').write_text(json.dumps({'results':rows}))
                with patch.object(updater,'BASE',str(root)),patch.object(updater,'PRECOLLECT_STAGE',str(stage)), \
                     patch.object(updater,'PRECOLLECT_STATUS',str(status)),patch.object(updater,'collect',return_value={'pending':[]}), \
                     patch.object(updater,'load_db',return_value={'pending':[],'applied':[]}),patch.object(updater,'save_db'), \
                     patch.object(updater,'_collection_mark_attempt'),patch.object(updater,'_collection_mark_failure'), \
                     patch.object(updater,'_collection_mark_success'),patch.object(updater,'_atomic_copy_json') as copy_stage, \
                     patch.object(automatic,'run_all',return_value={'ok':False,'results':[]}) as supplement:
                    updater.finalize_precollected_cycle(1700000000)
                    copy_stage.assert_not_called()
                    self.assertEqual(self.allowed,set(supplement.call_args.kwargs['selected_files']))


if __name__=='__main__':
    unittest.main()
