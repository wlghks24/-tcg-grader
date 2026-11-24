"""Regression coverage for both immutable diff option orders."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from execution import git_validation_cache as cache

class DiffOptionOrderTests(unittest.TestCase):
    def test_real_git_both_orders_and_cache_hits(self):
        with tempfile.TemporaryDirectory() as folder:
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=folder, text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            p = Path(folder) / 'sample.txt'
            p.write_text('first')
            git('add', 'sample.txt')
            git('commit', '-qm', 'first')
            first = git('rev-parse', 'HEAD')
            p.write_text('second')
            git('commit', '-qam', 'second')
            second = git('rev-parse', 'HEAD')
            for flags in (['--no-renames', '--name-only'], ['--name-only', '--no-renames']):
                command = ['git', 'diff', *flags, first+'..'+second, '--', 'sample.txt']
                before = cache._cached_object_read.cache_info()
                expected = subprocess.check_output(command, cwd=folder, text=True)
                for _ in range(2):
                    self.assertEqual(expected, cache.git_validation_output(command, cwd=folder, text=True))
                after = cache._cached_object_read.cache_info()
                self.assertEqual(1, after.hits-before.hits)
                self.assertEqual(1, after.misses-before.misses)

    def test_unsafe_forms_not_accepted(self):
        a, b = 'a'*40, 'b'*40
        for args in (['git','diff','--name-only',a,b],
                     ['git','diff','--name-only','--name-only',a,b],
                     ['git','diff','--name-only','--no-renames','main',b],
                     ['git','diff','--name-only','--no-renames',a+'...'+b]):
            self.assertIsNone(cache._immutable_command(args, '.', subprocess.run, allow_head=False))

if __name__ == '__main__':
    unittest.main()
