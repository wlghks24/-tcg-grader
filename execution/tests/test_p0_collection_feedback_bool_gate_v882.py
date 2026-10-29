"""Only literal booleans may elevate feedback-derived official/cross-check trust."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from adaptive_collection_learner import AdaptiveCollectionLearner


class FeedbackBooleanGateV882Tests(unittest.TestCase):
    def _learn(self, verified, cross_checked):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            feedback = root / 'feedback.json'
            feedback.write_text(json.dumps({'items': [{
                'id': 'feedback-1', 'game': 'pokemon', 'region': 'KR',
                'source': 'https://example.invalid/notice',
                'title': 'Pokemon sample event card',
                'verdict': 'missed',
                'verified': verified, 'cross_checked': cross_checked,
            }]}), encoding='utf-8')
            learner = AdaptiveCollectionLearner(
                memory_path=root / 'memory.json',
                backup_path=root / 'memory.json.bak',
                report_path=root / 'report.json',
            )
            self.assertEqual(learner.learn_feedback_file(feedback), 1)
            stat = learner.memory['host_stats']['example.invalid']
            return stat['official'], stat['cross_checked']

    def test_string_false_never_counts_as_official_or_cross_checked(self):
        self.assertEqual((0, 0), self._learn('false', 'false'))

    def test_numeric_and_truthy_container_flags_do_not_elevate(self):
        for value in (1, 'true', {'evidence': True}, ['true']):
            with self.subTest(value=value):
                self.assertEqual((0, 0), self._learn(value, value))

    def test_actual_true_flags_remain_supported(self):
        self.assertEqual((1, 1), self._learn(True, True))
        self.assertEqual((0, 0), self._learn(False, False))


if __name__ == '__main__':
    unittest.main()
