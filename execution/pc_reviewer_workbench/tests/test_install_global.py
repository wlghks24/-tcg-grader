import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from install_global import check,install,InstallHold

class InstallerTests(unittest.TestCase):
    def test_installs_separate_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'new_app'
            result=install(ROOT,dest)
            self.assertEqual('COPIED_ONLY_NO_AUDIT_PERFORMED',result['status'])
            self.assertTrue((dest/'START_GLOBAL.cmd').exists())
            with self.assertRaisesRegex(InstallHold,'existing_install_not_overwritten'):
                install(ROOT,dest)
    def test_manifest_expected_bytes(self):
        result=check(ROOT)
        self.assertTrue(result['files'])
    def test_crlf_and_ascii(self):
        for file in ROOT.glob('*.cmd'):
            with self.subTest(file=file.name):
                data=file.read_bytes()
                self.assertTrue(data.isascii());self.assertEqual(data.count(b'\n'),data.count(b'\r\n'))
    def test_source_git_never_modified_by_installer(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'new_app'
            original={x.name:x.read_bytes() for x in ROOT.glob('*.py')}
            install(ROOT,dest)
            self.assertEqual(original,{x.name:x.read_bytes() for x in ROOT.glob('*.py')})

if __name__=='__main__':unittest.main()
