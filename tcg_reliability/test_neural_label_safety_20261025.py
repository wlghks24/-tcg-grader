"""Offline safety checks for Query neural training eligibility."""
import unittest

from verified_collection_neural import _eligible_training_labels, learning_readiness, _sanitize_labels_payload, FEATURE_FINGERPRINT


class NeuralLabelSafetyTests(unittest.TestCase):
    def test_legacy_rows_are_never_eligible(self):
        rows = [
            {"sample_id": "legacy", "outcome": True},
            {"sample_id": "late", "outcome": False, "feature_history_timing": "post_outcome"},
            {"sample_id": "verified", "outcome": True, "feature_history_timing": "pre_outcome", "evidence":"official_result_observed", "observed_at":"2026-10-25T01:00:00+09:00", "result_fingerprint":"a"*16},
        ]
        self.assertEqual([row["sample_id"] for row in _eligible_training_labels(rows)], ["verified"])
        readiness = learning_readiness(rows)
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["stored_label_count"], 3)
        self.assertEqual(readiness["eligible_training_labels"], 1)
        self.assertEqual(readiness["legacy_feature_history_unverified_count"], 2)

    def test_incomplete_evidence_is_retained_but_never_eligible(self):
        valid={"sample_id":"a"*24,"game":"포켓몬","region":"KR","outcome":True,"feature_history_timing":"pre_outcome","evidence":"official_result_observed","observed_at":"2026-10-25T01:00:00+09:00","result_fingerprint":"b"*16}
        for change in ({"evidence":""},{"evidence":"successful_empty_search"},{"observed_at":"not-a-date"},{"observed_at":"2026-10-25T01:00:00"},{"result_fingerprint":""},{"result_fingerprint":"z"*16}):
            with self.subTest(change=change):
                cleaned=_sanitize_labels_payload({"feature_fingerprint":FEATURE_FINGERPRINT,"labels":[dict(valid,**change)]})
                self.assertEqual(1,len(cleaned["labels"]))
                self.assertEqual([], _eligible_training_labels(cleaned["labels"]))
        cleaned=_sanitize_labels_payload({"feature_fingerprint":FEATURE_FINGERPRINT,"labels":[valid]})
        self.assertEqual(1,len(_eligible_training_labels(cleaned["labels"])))

    def test_large_legacy_collection_does_not_unlock_training(self):
        rows = [{"sample_id": str(i), "outcome": bool(i % 2)} for i in range(1200)]
        readiness = learning_readiness(rows)
        self.assertFalse(readiness["ready"])
        self.assertEqual(readiness["eligible_training_labels"], 0)
        self.assertEqual(readiness["reason"], "waiting_for_independent_labels")


if __name__ == "__main__":
    unittest.main()
