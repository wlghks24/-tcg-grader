"""V99 fail-closed regression: malformed defect evidence must never yield Gem Mint."""
from __future__ import annotations

import math
import unittest

import grading_accuracy_v99 as grading


class InvalidDefectEvidenceTests(unittest.TestCase):
    def test_each_negative_input_is_rejected_not_clamped_to_clean(self):
        for i in range(3):
            with self.subTest(index=i):
                risks = [0.0, 0.0, 0.0]
                risks[i] = -0.01
                self.assertEqual(grading.combine_defect_risk(*risks), 100.0)
                self.assertEqual(
                    grading.estimate_raw_grade(50, 50, *risks, "PSA"), 1.0
                )

    def test_malformed_or_missing_input_is_conservative(self):
        for invalid in (None, "", "  ", True, math.nan, math.inf, -math.inf, 101, "bad"):
            with self.subTest(invalid=repr(invalid)):
                self.assertEqual(grading.combine_defect_risk(invalid, 0, 0), 100.0)

    def test_valid_zero_and_positive_values_remain_supported(self):
        self.assertEqual(grading.combine_defect_risk(0, 0, 0), 0)
        self.assertAlmostEqual(grading.combine_defect_risk(30, 50, 70), 66.5)
        self.assertEqual(grading.estimate_raw_grade(50, 50, 0, 0, 0, "PSA"), 10.0)

    def test_missing_defect_never_exceeds_complete_evidence_grade(self):
        baseline = grading.estimate_raw_grade(50, 50, 1, 2, 3, "BGS")
        for invalid in (-1, None, 101, True):
            with self.subTest(invalid=repr(invalid)):
                predicted = grading.estimate_raw_grade(50, 50, invalid, 2, 3, "BGS")
                self.assertLessEqual(predicted, baseline)
                self.assertEqual(predicted, 1.0)

    def test_invalid_centering_and_defect_inputs_remain_fail_closed(self):
        self.assertEqual(grading.estimate_raw_grade(50, 50, -1, 0, 0, "INVALID"), 1.0)
        self.assertEqual(grading.estimate_raw_grade(None, 50, 0, 0, 0, "PSA"), 1.0)
        self.assertEqual(grading.estimate_raw_grade(50, 50, 0, 0, 0, "CGC"), 10.0)


if __name__ == "__main__":
    unittest.main()
