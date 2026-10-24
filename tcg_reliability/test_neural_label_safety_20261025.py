"""Offline safety checks for Query neural training eligibility."""
import unittest

from verified_collection_neural import _eligible_training_labels, learning_readiness


class NeuralLabelSafetyTests(unittest.TestCase):
    def test_legacy_rows_are_never_eligible(self):
        rows = [
            {"sample_id": "legacy", "outcome": True},
            {"sample_id": "late", "outcome": False, "feature_history_timing": "post_outcome"},
            {"sample_id": "verified", "outcome": True, "feature_history_timing": "pre_outcome"},
        ]
        self.assertEqual([row["sample_id"] for row in _eligible_training_labels(rows)], ["verified"])
        readiness = learning_readiness(rows)
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["stored_label_count"], 3)
        self.assertEqual(readiness["eligible_training_labels"], 1)
        self.assertEqual(readiness["legacy_feature_history_unverified_count"], 2)

    def test_large_legacy_collection_does_not_unlock_training(self):
        rows = [{"sample_id": str(i), "outcome": bool(i % 2)} for i in range(1200)]
        readiness = learning_readiness(rows)
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["eligible_training_labels"], 0)
        self.assertEqual(readiness["reason"], "waiting_for_independent_labels")


if __name__ == "__main__":
    unittest.main()
