"""Synthetic schema fixtures only; never fabricate labels in a production store."""
from __future__ import annotations

import unittest
from unittest.mock import patch
from execution import tablet_learning_readiness_v676 as review


def query(ready=False):
    return {
        "label_count": 315, "eligible_training_labels": 6,
        "minimum_labels": 1000, "scope": "adaptive_public_search_priority_only",
        "training_readiness": {
            "ready": ready, "reason": "waiting_for_independent_labels",
            "positive_labels_remaining": 94,
            "negative_labels_remaining": 100,
            "automatic_training_on_collection": True,
        },
    }


def job():
    return {
        "label_count": 600, "minimum_labels": 1000,
        "training_readiness": {
            "ready": False, "reason": "waiting_for_independent_labels",
            "positive_labels_remaining": 0,
            "negative_labels_remaining": 0,
            "automatic_training_on_collection": True,
        },
    }


def snapshot():
    return {"local_only": True, "fabricated_labels": False,
            "models": {"query": query(), "job": job()}, "errors": []}


class V676ReadinessTests(unittest.TestCase):
    def test_query_ineligible_legacy_cannot_be_used_to_complete_target(self):
        report = review.summarize(snapshot())
        self.assertTrue(report["ok"])
        self.assertEqual(994, report["models"]["query"]["total_remaining"])
        self.assertEqual(309, report["models"]["query"]["legacy_unverified_excluded"])
        self.assertEqual(94, report["models"]["query"]["positive_remaining"])
        self.assertEqual(100, report["models"]["query"]["negative_remaining"])
        self.assertFalse(report["models"]["query"]["training_allowed"])
        self.assertFalse(report["training_executed"])

    def test_job_stays_waiting_despite_both_classes_sufficient(self):
        r = review.summarize(snapshot())
        self.assertEqual(400, r["models"]["job"]["total_remaining"])
        self.assertFalse(r["models"]["job"]["training_allowed"])

    def test_ready_status_is_only_advisory_not_a_training_action(self):
        s = snapshot()
        s["models"]["query"] = {
            **query(),
            "label_count": 1200, "eligible_training_labels": 1100,
            "training_readiness": {
                "ready": True, "reason": "ready_for_guarded_training",
                "positive_labels_remaining": 0, "negative_labels_remaining": 0,
                "automatic_training_on_collection": True,
            },
        }
        r = review.summarize(s)
        self.assertTrue(r["models"]["query"]["training_allowed"])
        self.assertFalse(r["training_executed"])
        self.assertFalse(r["production_model_changed"])

    def test_false_ready_cannot_approve_training(self):
        s = snapshot()
        s["models"]["query"]["training_readiness"]["ready"] = True
        r = review.summarize(s)
        self.assertFalse(r["ok"])
        self.assertEqual("HOLD_FALSE_READY", r["models"]["query"]["status"])

    def test_poisoned_status_is_fail_closed(self):
        for value in ("6", True, -5, 1.2, 10_000_001):
            with self.subTest(value=value):
                s = snapshot()
                s["models"]["query"]["eligible_training_labels"] = value
                self.assertFalse(review.summarize(s)["ok"])

    def test_ineligible_count_missing_not_guessed(self):
        s = snapshot()
        del s["models"]["query"]["eligible_training_labels"]
        self.assertFalse(review.summarize(s)["ok"])

    def test_invalid_class_remaining_and_policy_fail_closed(self):
        for field, value in (
            ("positive_labels_remaining", False),
            ("negative_labels_remaining", -1),
            ("automatic_training_on_collection", "yes"),
        ):
            s = snapshot()
            s["models"]["query"]["training_readiness"][field] = value
            with self.subTest(field=field):
                self.assertFalse(review.summarize(s)["ok"])

    def test_errors_or_fabricated_label_snapshot_not_authorized(self):
        s = snapshot()
        s["errors"] = [{"model": "query", "error": "ValueError"}]
        self.assertFalse(review.summarize(s)["ok"])
        s = snapshot()
        s["fabricated_labels"] = True
        self.assertFalse(review.summarize(s)["ok"])

    def test_run_uses_existing_read_only_status_not_train(self):
        s = snapshot()
        with patch("execution.tablet_local_learning.run", return_value=s) as stub:
            r = review.run()
        stub.assert_called_once_with(train=False)
        self.assertEqual(0, r["new_labels_created"])

    def test_models_missing_never_counted_as_complete(self):
        s = snapshot()
        del s["models"]["job"]
        self.assertFalse(review.summarize(s)["ok"])


if __name__ == "__main__":
    unittest.main()
