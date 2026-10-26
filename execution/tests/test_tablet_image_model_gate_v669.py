"""Adversarial regression tests for local advisory model promotion metrics."""
import unittest
from execution.tablet_image_model_gate import acceptable, choose


class ImageGateMetricSafety(unittest.TestCase):
    def setUp(self):
        self.g = dict(mae=.4, overgrade_rate=.07, bias=.1)
        self.gb = dict(mae=.65, overgrade_rate=.12, bias=.3)
        self.i = dict(accuracy=.95, brier=.12, ece=.06)
        self.ib = dict(accuracy=.88, brier=.22, ece=.13)

    def test_valid_grade_and_identity(self):
        self.assertTrue(acceptable('grade', self.g, self.gb))
        self.assertTrue(acceptable('identity', self.i, self.ib))

    def test_unknown_tasks_not_identity(self):
        for task in ('unknown', 'Grade', 'identity ', None, ''):
            self.assertFalse(acceptable(task, self.i, self.ib))

    def test_missing_metric_rejected(self):
        for task, row, baseline in [('grade', self.g, self.gb), ('identity', self.i, self.ib)]:
            for key in row:
                self.assertFalse(acceptable(task, {k:v for k,v in row.items() if k!=key}, baseline))
                self.assertFalse(acceptable(task, row, {k:v for k,v in baseline.items() if k!=key}))

    def test_invalid_types_and_non_finite_rejected(self):
        for bad in (None, [], 'text', False):
            self.assertFalse(acceptable('identity', bad, self.ib))
            self.assertFalse(acceptable('grade', self.g, bad))
        for bad in (float('nan'), float('inf'), float('-inf'), True, '0.95'):
            self.assertFalse(acceptable('identity', dict(self.i, accuracy=bad), self.ib))
            self.assertFalse(acceptable('grade', self.g, dict(self.gb, mae=bad)))

    def test_invalid_extra_metric_rejected(self):
        self.assertFalse(acceptable('identity', dict(self.i, extra='x'), self.ib))
        self.assertFalse(acceptable('grade', dict(self.g, extra=True), self.gb))

    def test_invalid_metric_domains_rejected(self):
        self.assertFalse(acceptable('identity', dict(self.i, accuracy=1.2), self.ib))
        self.assertFalse(acceptable('identity', self.i, dict(self.ib, ece=-.1)))
        self.assertFalse(acceptable('identity', self.i, dict(self.ib, brier=2.2)))
        self.assertFalse(acceptable('grade', dict(self.g, overgrade_rate=-.1), self.gb))
        self.assertFalse(acceptable('grade', self.g, dict(self.gb, mae=-1)))
        self.assertFalse(acceptable('grade', dict(self.g, bias=11), self.gb))

    def test_grade_thresholds_preserved(self):
        self.assertFalse(acceptable('grade', dict(self.g, mae=.51), self.gb))
        self.assertFalse(acceptable('grade', dict(self.g, overgrade_rate=.101), self.gb))
        self.assertFalse(acceptable('grade', dict(self.g, bias=.251), self.gb))
        self.assertFalse(acceptable('grade', dict(self.g, mae=.64), self.gb))

    def test_identity_thresholds_preserved(self):
        self.assertFalse(acceptable('identity', dict(self.i, accuracy=.89), self.ib))
        self.assertFalse(acceptable('identity', dict(self.i, brier=.151), self.ib))
        self.assertFalse(acceptable('identity', dict(self.i, ece=.101), self.ib))

    def test_both_holdouts_required(self):
        self.assertTrue(choose('identity', self.i, self.i, self.ib, self.ib))
        bad = dict(self.i, accuracy=.87)
        self.assertFalse(choose('identity', self.i, bad, self.ib, self.ib))
        self.assertFalse(choose('identity', bad, self.i, self.ib, self.ib))

    def test_bad_baseline_rejected(self):
        self.assertFalse(acceptable('grade', self.g, dict(self.gb, overgrade_rate=1.1)))
        self.assertFalse(acceptable('identity', self.i, dict(self.ib, accuracy=-.1)))


if __name__ == '__main__':
    unittest.main()
