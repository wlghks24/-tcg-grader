"""Catch the exact v0.9.1 syntax regression before release or installation."""
import ast
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import local_gui
import preflight
from install_global import InstallHold


class PreflightRegression(unittest.TestCase):
    def test_all_shipped_python_files_parse_and_compile(self):
        result=preflight.verify(ROOT)
        self.assertGreaterEqual(result['python_sources'],10)

    def test_fixed_log_append_writes_one_newline(self):
        app=local_gui.App.__new__(local_gui.App)
        class Text:
            value=''
            def insert(self,where,text): self.value+=text
            def index(self,where): return str(self.value.count('\n')+1)+'.0'
            def delete(self,*args): raise AssertionError('too short to trim')
            def see(self,*args): pass
        app.log=Text()
        app.append('hello')
        self.assertEqual('hello\n',app.log.value)

    def test_exact_v091_corrupted_string_is_detected(self):
        broken = "def append(self,s):\n    self.log.insert('end',s+'\n');lines=2\n"
        with self.assertRaises(SyntaxError):
            compile(broken, 'local_gui.py', 'exec')

    def test_preflight_blocks_syntax_error_even_with_forged_manifest(self):
        required = ('local_gui.py','local_review.py','full_repo_engine.py','full_repo_gui.py')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in required:
                (root/name).write_text('x = 1\n', encoding='utf-8')
            (root/'local_gui.py').write_text("x = 'unfinished\n", encoding='utf-8')
            with mock.patch.object(preflight,'check',return_value={'files': {name: {} for name in required}}):
                with self.assertRaisesRegex(InstallHold,'python_source_invalid:local_gui.py'):
                    preflight.verify(root)

    def test_required_gui_is_importable_without_running_mainloop(self):
        self.assertTrue(callable(local_gui.App))
        self.assertTrue(callable(local_gui.review))
        self.assertTrue(callable(local_gui.run_global))

    def test_new_installer_folder_and_batch_scripts(self):
        from install_global import INSTALL_FOLDER
        self.assertEqual('TCG_PC_Reviewer_v0100',INSTALL_FOLDER)
        b=(ROOT/'START_HERE.cmd').read_bytes()
        self.assertIn(b'preflight.py',b)
        self.assertEqual(b.count(b'\n'),b.count(b'\r\n'))

if __name__=='__main__':unittest.main()
