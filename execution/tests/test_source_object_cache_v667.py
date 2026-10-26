"""Only immutable Git objects may be reused; source keys remain exact."""
import unittest
from unittest.mock import patch
from execution import pr814_source_preflight_v665 as p

class ImmutableObjectCacheTests(unittest.TestCase):
    def test_digest_cache_is_scoped_by_checkout_ref_and_path(self):
        p._immutable_source_digest.cache_clear()
        with patch.object(p,'git',return_value=b'git object bytes') as git:
            a=p._immutable_source_digest('/repo-a','a'*40,'file.py')
            self.assertEqual(a,p._immutable_source_digest('/repo-a','a'*40,'file.py'))
            self.assertEqual(1,git.call_count)
            for root,ref,path in (('/repo-b','a'*40,'file.py'),('/repo-a','b'*40,'file.py'),('/repo-a','a'*40,'other.py')):
                p._immutable_source_digest(root,ref,path)
            self.assertEqual(4,git.call_count)
        p._immutable_source_digest.cache_clear()

    def test_scope_cache_never_accepts_an_unexpected_changed_path(self):
        p._immutable_scope.cache_clear()
        def git(root,*args):
            return b'expected.py\nunreviewed.py\n' if args[0]=='diff' else b''
        with patch.object(p,'git',side_effect=git):
            for unused in range(2):
                with self.assertRaisesRegex(p.Hold,'changed_scope_not_exact'):
                    p._immutable_scope('/repo','a'*40,'b'*40,('expected.py',))
        p._immutable_scope.cache_clear()
