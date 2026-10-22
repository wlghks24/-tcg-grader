"""A CI dependency addition is an exact successor, never a watch exemption."""
from pathlib import Path
import unittest
from unittest.mock import patch
import sync_v376_successor_test_support as sync
class AlignmentDependencyTests(unittest.TestCase):
    def test_exact_immutable_ci_descendant(self):
        sync.assert_v647_ci_successor(self)
        proof=sync.V647_CI_PROOF;name=next(iter(proof['reviewed_sha256']))
        self.assertEqual([],sync.preserve_reviewed_v647_ci_scope([name],proof['base_commit']))
        self.assertEqual([name],sync.preserve_reviewed_v647_ci_scope([name],'6faaea1319623bc378be7209c54ad38cafc66707'))
    def test_unreviewed_workflow_changes_remain_visible(self):
        proof=sync.V647_CI_PROOF;name=next(iter(proof['reviewed_sha256']));original=Path.read_bytes
        def changed(p):return original(p)+b'\n# unreviewed' if p==sync.ROOT/name else original(p)
        with patch.object(Path,'read_bytes',changed):
            with self.assertRaises(AssertionError):sync.assert_v647_ci_successor(self)
            self.assertEqual([name],sync.preserve_reviewed_v647_ci_scope([name],proof['base_commit']))
    def test_existing_dependency_and_every_sync_test_are_kept(self):
        name=next(iter(sync.V647_CI_PROOF['reviewed_sha256']));text=(sync.ROOT/name).read_text()
        self.assertIn('python -m pip install --disable-pip-version-check -r requirements.txt',text)
        self.assertIn('python -m unittest -v "${tests[@]}"',text)
        self.assertIn('Pillow>=13.0,<14',(sync.ROOT/'requirements.txt').read_text())
