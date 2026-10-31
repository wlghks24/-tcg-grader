"""Read-only scanner regression tests."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / 'external_skill_review.py'
spec = importlib.util.spec_from_file_location('external_skill_review', MODULE)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class ReviewTests(unittest.TestCase):
    def test_duplicate_and_ui_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'a.py').write_text('def alpha(x):\n    a = x + 1\n    b = a * 2\n    return b\n')
            (root / 'b.py').write_text('def beta(x):\n    a = x + 1\n    b = a * 2\n    return b\n')
            (root / 'index.html').write_text('<html><img src="x.png"></html>')
            kinds = {x['kind'] for x in scanner.audit(root)['findings']}
            self.assertTrue({'duplicate_candidate', 'viewport_review', 'image_alt_review'} <= kinds)

    def test_does_not_follow_symlink_or_execute_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / 'executed'
            (root / 'unsafe.py').write_text('open(' + repr(str(marker)) + ', "w").write("bad")\n')
            (root / 'alias.py').symlink_to(root / 'unsafe.py')
            (root / 'ignored').mkdir()
            (root / 'ignored' / 'link').symlink_to(root, target_is_directory=True)
            result = scanner.audit(root)
            self.assertEqual(result['inspected_files'], 1)
            self.assertFalse(marker.exists())

    def test_invalid_python_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'bad.py').write_text('def broken(:\n')
            self.assertEqual(scanner.audit(root)['findings'][0]['kind'], 'python_syntax')

    def test_per_image_alt_and_comment_not_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index.html').write_text('<html><head><meta name="viewport" content="width=device-width"></head>'
                                             '<!-- <img src="fake"> --><img alt="ok"><img src="missing">'
                                             '</html>')
            findings = scanner.audit(root)['findings']
            self.assertEqual([f['kind'] for f in findings], ['image_alt_review'])
            self.assertEqual(findings[0]['line'], 1)

    def test_pruned_directory_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'node_modules').mkdir()
            (root / 'node_modules' / 'ignored.py').write_text('bad')
            (root / 'a.py').write_text('pass\n')
            (root / 'b.py').write_text('pass\n')
            result = scanner.audit(root, max_files=1)
            self.assertEqual(result['inspected_files'], 1)
            self.assertIn('limit', {x['kind'] for x in result['findings']})


if __name__ == '__main__':
    unittest.main()
