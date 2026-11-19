"""Guard the exact V525 -> V652 -> V653 proof order against duplicate work."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch

import sync_v376_successor_test_support as successor


class V525SuccessorDedupTests(unittest.TestCase):
    def test_v525_invokes_unchanged_v653_proof_once_via_v652(self):
        # Read-only test: unrelated downstream gates keep their names and order,
        # but are isolated to measure the V653 call count without live Git.
        function = successor.preserve_reviewed_v525_grade_scope
        other = {
            name for name in function.__code__.co_names
            if name.startswith('preserve_reviewed_v')
            and name not in ('preserve_reviewed_v652_scope',
                             'preserve_reviewed_v653_scope')
        }
        self.assertIn('preserve_reviewed_v661_scope', other)
        self.assertIn('preserve_reviewed_v1013_workflow_scope', other)
        with ExitStack() as stack:
            for name in sorted(other):
                stack.enter_context(patch.object(
                    successor, name, side_effect=lambda paths, *args, **kwargs: paths))
            gate = stack.enter_context(patch.object(
                successor, 'preserve_reviewed_v653_scope',
                side_effect=lambda paths, *args, **kwargs: paths))
            result = function([], 'a' * 40, 'HEAD')
        self.assertEqual([], result)
        gate.assert_called_once_with([], 'a' * 40, 'HEAD')

    def test_public_v652_still_invokes_v653_proof(self):
        with patch.object(successor, 'preserve_reviewed_v653_scope',
                          side_effect=lambda paths, *args, **kwargs: paths) as gate:
            result = successor.preserve_reviewed_v652_scope([], 'b' * 40, 'HEAD')
        self.assertEqual([], result)
        gate.assert_called_once_with([], 'b' * 40, 'HEAD')

    def test_non_head_path_still_checks_v653_once(self):
        function = successor.preserve_reviewed_v525_grade_scope
        other = {
            name for name in function.__code__.co_names
            if name.startswith('preserve_reviewed_v')
            and name not in ('preserve_reviewed_v652_scope',
                             'preserve_reviewed_v653_scope')
        }
        with ExitStack() as stack:
            for name in sorted(other):
                stack.enter_context(patch.object(
                    successor, name, side_effect=lambda paths, *args, **kwargs: paths))
            gate = stack.enter_context(patch.object(
                successor, 'preserve_reviewed_v653_scope',
                side_effect=lambda paths, *args, **kwargs: paths))
            result = function([], 'c' * 40, 'd' * 40)
        self.assertEqual([], result)
        gate.assert_called_once_with([], 'c' * 40, 'd' * 40)


if __name__ == '__main__':
    unittest.main()
