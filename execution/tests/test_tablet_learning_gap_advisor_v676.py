"""V676 no-fabrication training-readiness and Termux single-owner regression."""
from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

from execution import tablet_learning_gap_advisor_v676 as advisor


def status(stored=315, eligible=6, positive=6, negative=0, ready=False):
    return {
        "label_count": stored, "minimum_labels": 1000,
        "eligible_training_labels": eligible,
        "positive_labels": positive, "negative_labels": negative,
        "training_readiness": {"minimum_each_class": 100, "ready": ready},
    }


class AdvisorV676Tests(unittest.TestCase):
    def test_query_deficit_excludes_legacy_unverified_records(self):
        x = advisor.inspect_model("query", status())
        self.assertEqual("WAITING_FOR_VERIFIED_LABELS", x["status"])
        self.assertEqual(994, x["labels_missing"])
        self.assertEqual(94, x["positive_missing"])
        self.assertEqual(100, x["negative_missing"])
        self.assertEqual(309, x["legacy_unverified_excluded"])
        self.assertFalse(x["training_permitted"])

    def test_job_status_uses_verified_job_count_no_fabrication(self):
        s = status(stored=600, eligible=600, positive=476, negative=124)
        s.pop("eligible_training_labels")
        x = advisor.inspect_model("job", s)
        self.assertEqual(400, x["labels_missing"])
        self.assertEqual(0, x["positive_missing"])
        self.assertEqual(0, x["negative_missing"])
        self.assertEqual(0, x["legacy_unverified_excluded"])
        self.assertFalse(x["training_permitted"])

    def test_native_temporal_gate_cannot_be_bypassed_by_counts(self):
        s = status(1000, 1000, 500, 500, False)
        result = advisor.inspect_model("query", s)
        self.assertEqual("WAITING_FOR_TEMPORAL_EVIDENCE", result["status"])
        self.assertFalse(result["training_permitted"])

    def test_own_readiness_gate_and_independent_counts_both_required(self):
        s = status(1100, 1100, 600, 500, True)
        result = advisor.inspect_model("query", s)
        self.assertEqual("READY_FOR_EXISTING_GUARDED_TRAINER", result["status"])
        self.assertTrue(result["training_permitted"])
        s["eligible_training_labels"] = 990
        self.assertFalse(advisor.inspect_model("query", s)["training_permitted"])

    def test_inconsistent_counts_fail_closed(self):
        for delta in (
            {"eligible_training_labels": 400},
            {"positive_labels": True},
            {"negative_labels": -1},
            {"minimum_labels": 0},
            {"training_readiness": {"ready": True}},
            {"label_count": "1000"},
        ):
            s = status()
            s.update(delta)
            with self.subTest(delta=delta):
                x = advisor.inspect_model("query", s)
                self.assertFalse(x["training_permitted"])
                self.assertEqual("HOLD", x["status"])

    def test_image_never_promoted_and_no_second_scheduler(self):
        x = advisor.assess({"query": status()}, {
            "status": "WAITING_FOR_REVIEWED_RAW_PHOTOS",
        })
        self.assertTrue(x["image_training"]["requires_verified_raw_photos"])
        self.assertFalse(x["image_training"]["training_permitted_by_advisor"])
        self.assertFalse(x["automatic_accumulation"]["fake_labels_generated"])
        self.assertFalse(x["automatic_accumulation"]["new_scheduler_installed"])
        self.assertFalse(x["automatic_accumulation"]["unverified_social_candidates_are_training_labels"])
        self.assertFalse(x["physical_tablet_verified"])

    def test_snapshot_calls_only_status_never_trains(self):
        def never_train(*args, **kwargs):
            raise AssertionError("train_if_ready unexpectedly called")
        query = types.SimpleNamespace(status=lambda: status(), train_if_ready=never_train)
        job = types.SimpleNamespace(
            status=lambda: status(600, 600, 476, 124),
            train_if_ready=never_train,
        )
        with patch.dict(sys.modules, {
            "verified_collection_neural": query, "verified_collection_job_neural": job,
        }), patch("execution.tablet_image_autonomy.run", return_value={
            "status": "WAITING_FOR_REVIEWED_RAW_PHOTOS",
        }) as image:
            result = advisor.snapshot()
        image.assert_called_once_with(train=False)
        self.assertEqual(994, result["models"]["query"]["labels_missing"])
        self.assertEqual(400, result["models"]["job"]["labels_missing"])


if __name__ == "__main__":
    unittest.main()
