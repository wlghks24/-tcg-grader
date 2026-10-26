"""Offline regressions for V676 gap reporter. No real training or disk mutations."""
import copy
import unittest

from execution.tablet_learning_gap_v676 import assess, assess_model


class GapReviewTests(unittest.TestCase):
    def make(self, eligible=6, labels=315, minimum=1000, ready=False,
             positive=94, negative=100):
        return {
            "label_count": labels,
            "eligible_training_labels": eligible,
            "minimum_labels": minimum,
            "training_readiness": {
                "ready": ready,
                "positive_labels_remaining": positive,
                "negative_labels_remaining": negative,
            },
            "training_requested": False,
            "training_attempted": False,
        }

    def test_query_unverified_legacy_309_not_counted(self):
        query = self.make()
        data = assess({"models": {"query": query, "job": self.make(600, 600, 1000, False, 0, 0)}})
        self.assertEqual(994, data["models"]["query"]["remaining_verified_labels"])
        self.assertEqual(400, data["models"]["job"]["remaining_verified_labels"])
        self.assertEqual(94, data["models"]["query"]["positive_labels_remaining"])
        self.assertEqual(100, data["models"]["query"]["negative_labels_remaining"])
        self.assertFalse(data["training_permitted"])
        self.assertFalse(data["model_promotion_permitted"])
        self.assertEqual("HOLD", data["overall"])

    def test_never_mutates_input_or_starts_training(self):
        value = {"models": {"query": self.make(), "job": self.make()}}
        before = copy.deepcopy(value)
        report = assess(value)
        self.assertEqual(before, value)
        self.assertNotIn("trained", str(report).lower())
        self.assertEqual("OFFLINE_ADVISORY_GAPS_ONLY", report["scope"])

    def test_invalid_counts_never_authorize_training(self):
        for eligible in (True, -1, 1.3, "1000", None, 10**50):
            with self.subTest(eligible=eligible):
                row = self.make(eligible=eligible, ready=True, positive=0, negative=0)
                result = assess_model(row)
                self.assertFalse(result["training_permitted"])
                self.assertTrue(result["blockers"])

    def test_training_ready_contradictions_detected(self):
        for row in (
            self.make(999, 999, ready=True, positive=0, negative=0),
            self.make(1000, 1000, ready=True, positive=1, negative=0),
            self.make(1000, 1000, ready=True, positive=0, negative=1),
            self.make(1001, 1000, ready=True, positive=0, negative=0),
            self.make(1000, 1000, minimum=0, ready=True, positive=0, negative=0),
        ):
            with self.subTest(row=row):
                report = assess_model(row)
                self.assertFalse(report["training_permitted"])
                self.assertTrue(report["blockers"])

    def test_fully_eligible_remains_advisory_only(self):
        report = assess_model(self.make(1000, 1000, 1000, True, 0, 0))
        self.assertEqual("ELIGIBLE_FOR_EXISTING_GATE_REVIEW", report["state"])
        self.assertFalse(report["training_permitted"])
        self.assertFalse(report["model_promotion_permitted"])
        self.assertEqual([], report["blockers"])

    def test_empty_malformed_inputs_fail_closed(self):
        for value in (None, [], {}, {"models": []}, {"models": {"query": 3}}):
            with self.subTest(value=value):
                result = assess(value)
                self.assertTrue(result["models"]["query"]["blockers"])
                self.assertFalse(result["training_permitted"])

    def test_outcome_failure_requires_existing_scheduler_review(self):
        query = self.make(1000, 1000, 1000, True, 0, 0)
        query.update(training_attempted=True, training_result={
            "active": False, "training_skipped": False, "reason": "PRIVATE_ERROR_STRING",
        })
        report = assess({"models": {"query": query}})
        self.assertIn("PRIOR_TRAINING_RESULT_UNSUCCESSFUL", report["models"]["query"]["blockers"])
        self.assertNotIn("PRIVATE_ERROR_STRING", str(report))


if __name__ == "__main__":
    unittest.main()
