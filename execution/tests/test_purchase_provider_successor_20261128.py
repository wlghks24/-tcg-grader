"""Exact descendant tests: do not accept unknown paths or live mutations."""
import unittest
from pathlib import Path
from unittest.mock import patch

from execution import purchase_provider_successor_20261128 as proof


class PurchaseProviderSuccessorTests(unittest.TestCase):
    def test_exact_source_and_all_three_historical_pins(self):
        for name, pin in proof.EXPECTED['baseline'].items():
            with self.subTest(name=name):
                self.assertTrue(proof.validate_boundary_successor(name, pin['sha256']))

    def test_wrong_prior_digest_and_unknown_path_rejected(self):
        name = 'update_purchase_sources.py'
        with self.assertRaises(AssertionError):
            proof.validate_boundary_successor(name, '0' * 64)
        with self.assertRaises(AssertionError):
            proof.validate_boundary_successor('unknown.py', '0' * 64)

    def test_each_mutated_runtime_byte_remains_unapproved_after_warmup(self):
        name = 'grading_company_watch.py'
        digest = proof.EXPECTED['baseline'][name]['sha256']
        self.assertTrue(proof.validate_boundary_successor(name, digest))
        original = Path.read_bytes
        for path in proof.NAMES:
            with self.subTest(path=path), patch.object(
                    Path, 'read_bytes', lambda p: original(p) + b'x'
                    if p == proof.ROOT / path else original(p)):
                with self.assertRaises(AssertionError):
                    proof.validate_boundary_successor(name, digest)
                self.assertEqual([name], proof.preserve_base_grading_scope(
                    [name], proof.EXPECTED['baseline_commit']))

    def test_earlier_diff_and_other_paths_preserved(self):
        name = 'grading_company_watch.py'
        visible = [name, 'unknown.py']
        base = proof.EXPECTED['baseline_commit']
        self.assertEqual(['unknown.py'], proof.preserve_base_grading_scope(visible, base))
        self.assertEqual(visible, proof.preserve_base_grading_scope(visible, base, head=base))
        original = proof._git
        def earlier(root, *args):
            if args[:4] == ('diff', '--no-renames', '--name-only', '-z') and args[-1] == name:
                return (name + '\0').encode()
            return original(root, *args)
        with patch.object(proof, '_git', side_effect=earlier):
            self.assertEqual(visible, proof.preserve_base_grading_scope(visible, base))

    def test_wrong_candidate_ancestry_rejected(self):
        name = 'grading_company_watch.py'
        digest = proof.EXPECTED['baseline'][name]['sha256']
        original = proof._git
        def divergent(root, *args):
            if args == ('merge-base', '--is-ancestor', proof.EXPECTED['candidate_commit'], 'HEAD'):
                raise AssertionError('divergent head')
            return original(root, *args)
        with patch.object(proof, '_git', side_effect=divergent):
            with self.assertRaises(AssertionError):
                proof.validate_boundary_successor(name, digest)


    def test_historical_diff_short_circuits_new_proof(self):
        import sync_v376_successor_test_support as support
        from unittest.mock import Mock
        visible = [support.V562_PURCHASE_PATH, 'unknown.py']
        with patch.object(support, '_git_validation_run', return_value=Mock(returncode=0)), \
             patch.object(support, '_git_validation_output', return_value=support.V562_PURCHASE_PATH + '\n'), \
             patch.object(proof, 'validate_boundary_successor', side_effect=AssertionError) as newer:
            self.assertEqual(visible, support.preserve_reviewed_v562_purchase_scope(visible, 'historic'))
            newer.assert_not_called()

    def test_invalid_text_diff_type_is_never_approved(self):
        import sync_v376_successor_test_support as support
        from unittest.mock import Mock
        visible = [support.V562_PURCHASE_PATH, 'unknown.py']
        for raw in (b'', None, [], False):
            with self.subTest(raw=raw), \
                 patch.object(support, '_git_validation_run', return_value=Mock(returncode=0)), \
                 patch.object(support, '_git_validation_output', return_value=raw), \
                 patch.object(proof, 'validate_boundary_successor') as newer:
                self.assertEqual(visible, support.preserve_reviewed_v562_purchase_scope(visible, 'historic'))
                newer.assert_not_called()

    def test_git_byte_contract_rejects_nonbytes(self):
        for raw in ('', None, [], False):
            with self.subTest(raw=raw), patch.object(proof, 'read', return_value=raw):
                with self.assertRaises(ValueError):
                    proof._git(proof.ROOT, 'diff')
        with patch.object(proof, 'read', return_value=b''):
            self.assertEqual(b'', proof._git(proof.ROOT, 'diff'))


if __name__ == '__main__':
    unittest.main()
