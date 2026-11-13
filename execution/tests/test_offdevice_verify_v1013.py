import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'offdevice_verify_v1013.py'

class TestBackup(unittest.TestCase):
    def runcheck(self, a, b):
        proc = subprocess.run([sys.executable, str(SCRIPT), str(a), str(b)], capture_output=True, text=True, timeout=15)
        return proc.returncode, json.loads(proc.stdout)

    def roots(self, root):
        a, b = root / 'a', root / 'b'
        a.mkdir(); b.mkdir()
        return a, b

    def test_matching_and_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.roots(Path(tmp))
            (a/'data.json').write_text('one'); (b/'data.json').write_text('one')
            code, report = self.runcheck(a, b)
            self.assertEqual(code, 0)
            self.assertTrue(report['comparison_pass'])
            self.assertFalse(report['offdevice_copy_verified'])
            self.assertFalse(report['ready_for_migration'])
            (b/'data.json').write_text('two')
            self.assertEqual(self.runcheck(a, b)[0], 2)

    def test_nested_and_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp)/'a'; b = a/'b'; b.mkdir(parents=True)
            self.assertEqual(self.runcheck(a, b)[0], 2)
            c = Path(tmp)/'c'; c.mkdir()
            (a/'x').write_text('x'); (c/'x').symlink_to(a/'x')
            self.assertEqual(self.runcheck(a, c)[0], 2)

    def test_empty_and_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.roots(Path(tmp))
            self.assertEqual(self.runcheck(a, b)[1]['reason'], 'empty_inventory')
            (a/'x').write_text('x')
            self.assertEqual(self.runcheck(a, b)[0], 2)
            self.assertEqual(self.runcheck(a, Path(tmp)/'missing')[0], 2)

    def test_extra_file_and_nested_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.roots(Path(tmp))
            (a/'nested').mkdir(); (b/'nested').mkdir()
            (a/'nested'/'x').write_bytes(b'123'); (b/'nested'/'x').write_bytes(b'123')
            self.assertEqual(self.runcheck(a, b)[0], 0)
            (b/'extra').write_bytes(b'')
            self.assertEqual(self.runcheck(a, b)[0], 2)

    def test_symlink_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.roots(Path(tmp))
            (a/'x').write_text('x'); (b/'x').write_text('x')
            (b/'linked').symlink_to(a, target_is_directory=True)
            self.assertEqual(self.runcheck(a, b)[1]['reason'], 'unsafe_directory')

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO requires POSIX')
    def test_fifo_rejected_without_hanging(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self.roots(Path(tmp))
            (a/'x').write_text('x')
            os.mkfifo(b/'x')
            self.assertEqual(self.runcheck(a, b)[1]['reason'], 'nonregular_file')

if __name__ == '__main__':
    unittest.main()
