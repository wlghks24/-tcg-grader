"""Review parity with PR #921 commit 0b39b214; static findings never imply approval."""
import json
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import full_repo_engine as g
import full_repo_gui as gui
from test_global_engine import build_repo

class Pr921Integration(unittest.TestCase):
    def test_stubs_and_notimplemented_are_independent_review_leads(self):
        code=b'''def concrete():
    "pass raise NotImplementedError"
    return 1
async def stub():
    """Docstring."""
    ...
def placeholder():
    pass
def missing():
    raise NotImplementedError("pending")
def ignored():
    try:
        return 1
    except ValueError:
        pass
'''
        record,risks=g._analyze_source('abc.py',code)
        stubs=[x for x in risks if x['rule']=='PLACEHOLDER_FUNCTION_REVIEW']
        raises=[x for x in risks if x['rule']=='UNIMPLEMENTED_RAISE_REVIEW']
        self.assertEqual({'placeholder','stub'},{x['function'] for x in stubs})
        self.assertEqual(1,len(raises))
        self.assertTrue(all(x['state']=='REVIEW_NOT_CONFIRMED_DEFECT' for x in stubs+raises))
        self.assertEqual('PYTHON_AST_OK',record['syntax'])

    def test_distinct_line_locations_and_task_ids_preserved(self):
        code=b'def f():\n pass\ndef g():\n pass\n'
        _,risks=g._analyze_source('feature.py',code)
        self.assertEqual([1,3],[x['line'] for x in risks])
        # same evidence must have stable ID and different lines different IDs
        ids=[g._sha(g._canonical({key:r.get(key) for key in ('path','line','rule','function')})) for r in risks]
        self.assertEqual(2,len(set(ids)))

    def test_complete_double_run_and_all_tasks_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);repo=root/'repo';git=build_repo(repo)
            (repo/'gaps.py').write_text('def partial():\n pass\ndef todo():\n raise NotImplementedError()\n',encoding='utf8')
            git('add','.');git('commit','-qm','Add implementation review cases')
            before=git('rev-parse','HEAD').decode('ascii')
            result=g.run_global(repo,root/'report')
            row=result['receipt'];gate=result['gate']
            self.assertEqual(2,row['passes'])
            self.assertTrue(row['sha256_and_bytes_equal'])
            self.assertGreaterEqual(gate['placeholder_or_unimplemented_hints'],2)
            tasks=json.loads((root/'report/pass_1/repair_backlog.json').read_text('utf8'))['items']
            self.assertTrue(all(x['automatic_apply_allowed'] is False and x['implementation_verified'] is False for x in tasks))
            self.assertTrue(all(len(x['task_id'])==64 and len(x['next_steps'])==4 and x['source_head_sha']==before for x in tasks))
            self.assertTrue(any(x['rule']=='PLACEHOLDER_FUNCTION_REVIEW' for x in tasks))
            self.assertEqual(git('rev-parse','HEAD').decode('ascii'),before)
            self.assertEqual(git('status','--porcelain'),b'')

    def test_bounded_gui_log_does_not_require_tk_display(self):
        app=gui.App.__new__(gui.App)
        app._queue=queue.Queue(maxsize=2)
        app._suppressed=0
        app._thread_message('a')
        app._thread_message('b')
        app._thread_message('c')
        self.assertEqual(2,app._queue.qsize())
        self.assertEqual(1,app._suppressed)

    def test_worker_restores_control_after_unexpected_exception(self):
        app=gui.App.__new__(gui.App)
        app._done=None
        with mock.patch.object(gui,'run_global',side_effect=RuntimeError('synthetic exception')):
            app._worker('C:/not_a_real_repo','D:/not_a_real_report')
        self.assertIn('[HOLD]',app._done)
        self.assertIn('synthetic exception',app._done)

    def test_finish_recovers_button_and_resets_busy_flag(self):
        app=gui.App.__new__(gui.App)
        app._running=True
        class Status:
            value=None
            def set(self,new):self.value=new
        class Button:
            state=None
            def configure(self,**kw):self.state=kw.get('state')
        app.status=Status();app.go=Button()
        with mock.patch.object(app,'_message') as written:
            app._finish('[HOLD] synthetic error')
        self.assertFalse(app._running)
        self.assertEqual('normal',app.go.state)
        self.assertIn('HOLD',app.status.value)
        written.assert_called_once_with('[HOLD] synthetic error')

    def test_gui_log_queue_caps_large_messages(self):
        app=gui.App.__new__(gui.App)
        app._queue=queue.Queue(maxsize=2)
        app._suppressed=0
        app._thread_message('z'*100000)
        self.assertEqual(gui.MAX_LOG_MESSAGE_BYTES,len(app._queue.get_nowait()))
        self.assertEqual(0,app._suppressed)

if __name__=='__main__':unittest.main()
