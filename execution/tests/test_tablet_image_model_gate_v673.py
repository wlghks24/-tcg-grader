"""Invalid external metric inputs reject promotion without raising exceptions."""
import unittest

from execution.tablet_image_model_gate import acceptable, choose


class ImageGateInvalidInputRejection(unittest.TestCase):
    def setUp(self):
        self.examples = {
            'grade': ({'mae': .4, 'overgrade_rate': .07, 'bias': .1},
                      {'mae': .65, 'overgrade_rate': .12, 'bias': .3}),
            'identity': ({'accuracy': .95, 'brier': .12, 'ece': .06},
                         {'accuracy': .88, 'brier': .22, 'ece': .13}),
        }

    def test_unhashable_and_non_string_tasks_are_rejected(self):
        candidate, baseline = self.examples['grade']
        for task in ([], {}, set(), ['grade'], {'task': 'grade'},
                     0, True, b'grade', ('grade',), None):
            with self.subTest(task=task):
                self.assertIs(acceptable(task, candidate, baseline), False)
                self.assertIs(choose(task, candidate, candidate, baseline, baseline), False)

    def test_oversized_required_metrics_reject_candidate_and_baseline(self):
        for task, (candidate, baseline) in self.examples.items():
            for key in candidate:
                for number in (10**400, -(10**400)):
                    with self.subTest(task=task, key=key, positive=number > 0):
                        self.assertIs(acceptable(task, dict(candidate, **{key: number}), baseline), False)
                        self.assertIs(acceptable(task, candidate, dict(baseline, **{key: number})), False)

    def test_oversized_extra_metric_cannot_abort_selection(self):
        for task, (candidate, baseline) in self.examples.items():
            for number in (10**400, -(10**400)):
                with self.subTest(task=task, positive=number > 0):
                    self.assertIs(acceptable(task, dict(candidate, diagnostic=number), baseline), False)
                    self.assertIs(acceptable(task, candidate, dict(baseline, diagnostic=number)), False)

    def test_invalid_number_in_any_split_blocks_selection(self):
        for task, (candidate, baseline) in self.examples.items():
            values = [candidate, candidate, baseline, baseline]
            for index in range(4):
                bad_values = list(values)
                bad_values[index] = dict(values[index], diagnostic=10**400)
                with self.subTest(task=task, index=index):
                    self.assertIs(choose(task, *bad_values), False)

    def test_reviewed_metric_improvement_still_selects(self):
        for task, (candidate, baseline) in self.examples.items():
            with self.subTest(task=task):
                self.assertIs(acceptable(task, candidate, baseline), True)
                self.assertIs(choose(task, candidate, candidate, baseline, baseline), True)


if __name__ == '__main__':
    unittest.main()
