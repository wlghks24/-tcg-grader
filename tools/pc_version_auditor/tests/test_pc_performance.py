"""Responsiveness and code-map regressions without creating a display."""
import ast
import queue
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pc_auditor'))
import audit
# Import the controller with a Tk stub: these tests do not verify rendering.
import importlib.util
from types import ModuleType
_tk = ModuleType('tkinter')
_tk.Tk = object
_tk.filedialog = mock.Mock()
_tk.messagebox = mock.Mock()
_tk.ttk = mock.Mock()
_gui_path = Path(__file__).resolve().parents[1] / 'pc_auditor' / 'gui.py'
_spec = importlib.util.spec_from_file_location('pc_gui_controller_test', _gui_path)
gui = importlib.util.module_from_spec(_spec)
with mock.patch.dict(sys.modules, {'tkinter': _tk}):
    _spec.loader.exec_module(gui)


class PerformanceTests(unittest.TestCase):
    def test_single_ast_traversal_keeps_map_and_security_hints(self):
        source = b'import json\nasync def f(data):\n    exec("pass")\n    return bool(data.get("verified"))\n'
        real_walk = ast.walk
        with mock.patch.object(audit, 'git', return_value=source), mock.patch.object(audit.ast, 'walk', wraps=real_walk) as walk:
            result = audit.code_map(Path('.'), ['example.py'])
        self.assertEqual(1, walk.call_count)
        self.assertEqual([{'name': 'f', 'line': 2, 'async': True}], result['files'][0]['functions'])
        self.assertEqual(['json'], result['files'][0]['imports'])
        self.assertEqual(['bool', 'exec', 'get'], result['files'][0]['called_names'])
        self.assertEqual(['DYNAMIC_CODE_EXECUTION_REVIEW', 'TRUTHY_VERIFICATION_FLAG_REVIEW'], [r['rule'] for r in result['risk_hints']])

    def test_poll_yields_with_pending_events(self):
        events = queue.Queue()
        for i in range(gui.MAX_EVENTS_PER_POLL + 20):
            events.put(('log', str(i)))
        fake = SimpleNamespace(events=events, _line=mock.Mock(), after=mock.Mock(), _poll=mock.Mock())
        gui.AuditGUI._poll(fake)
        self.assertEqual(gui.MAX_EVENTS_PER_POLL, fake._line.call_count)
        self.assertEqual(20, events.qsize())
        fake.after.assert_called_once()

    def test_log_retention_is_bounded(self):
        log = mock.Mock()
        log.index.return_value = '2501.0'
        gui.AuditGUI._line(SimpleNamespace(log=log), 'latest')
        log.delete.assert_called_once_with('1.0', '502.0')
        log.insert.assert_called_once_with('end', 'latest\n')
        log.configure.assert_called_with(state='disabled')

    def test_error_event_restores_controls(self):
        events = queue.Queue()
        events.put(('error', 'failure'))
        fake = SimpleNamespace(events=events, progress=mock.Mock(), start_btn=mock.Mock(), resume_btn=mock.Mock(), stop_btn=mock.Mock(), status=mock.Mock(), _line=mock.Mock(), after=mock.Mock(), _poll=mock.Mock())
        gui.AuditGUI._poll(fake)
        fake.start_btn.configure.assert_called_once_with(state='normal')
        fake.resume_btn.configure.assert_called_once_with(state='normal')
        fake.stop_btn.configure.assert_called_once_with(state='disabled')
        fake.status.set.assert_called_once_with('HOLD: failure')


if __name__ == '__main__':
    unittest.main()
