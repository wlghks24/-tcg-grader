import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import adaptive_collection_learner as adaptive
import event_gap_learning as event_gap
import verified_collection_job_neural as job_neural
import verified_collection_neural as collection_neural
import verified_neural_self_refine as repair_neural


class LearningStateConcurrencyV280Tests(unittest.TestCase):
    def test_event_gap_stale_learners_merge_counters_and_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = Path(tmp) / "event_gap.json"
            a = event_gap.EventGapLearner(memory)
            b = event_gap.EventGapLearner(memory)
            a.observe({"pokemon|KR|promo": 1})
            a._learn_terms("pokemon", "KR", "promo", {"learning_terms": ["AlphaPromo"]})
            a.save()
            b.observe({"onepiece|JP|promo": 0})
            b._learn_terms("onepiece", "JP", "promo", {"learning_terms": ["BetaPromo"]})
            b.save()
            a.observe({"pokemon|KR|promo": 1})
            a.save()
            final = event_gap.EventGapLearner(memory).data
            self.assertEqual(final["runs"], 3)
            self.assertEqual(final["cells"]["pokemon|KR|promo"]["attempts"], 2)
            self.assertEqual(final["cells"]["pokemon|KR|promo"]["hits"], 2)
            self.assertEqual(final["cells"]["onepiece|JP|promo"]["misses"], 1)
            self.assertIn("pokemon|KR|promo|AlphaPromo", final["terms"])
            self.assertIn("onepiece|JP|promo|BetaPromo", final["terms"])

    def test_adaptive_stale_learners_preserve_same_query_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "memory.json"
            backup = root / "memory.json.bak"
            report = root / "report.json"
            a = adaptive.AdaptiveCollectionLearner(memory_path=memory, backup_path=backup, report_path=report)
            b = adaptive.AdaptiveCollectionLearner(memory_path=memory, backup_path=backup, report_path=report)
            with mock.patch.object(adaptive.verified_collection_neural, "train_if_ready", return_value={"active": False}):
                a.observe_search("포켓몬", "pokemon promo", [], family="web", region="KR")
                a.save()
                b.observe_search("포켓몬", "pokemon promo", [], family="web", region="KR")
                b.save()
                a.observe_search("포켓몬", "pokemon promo", [], family="web", region="KR")
                a.save()
            final = adaptive.AdaptiveCollectionLearner(memory_path=memory, backup_path=backup, report_path=report).memory
            key = adaptive._signature("pokemon promo")
            self.assertEqual(final["totals"]["searches"], 3)
            self.assertEqual(final["query_stats"][key]["runs"], 3)
            self.assertEqual(final["query_stats"][key]["empty"], 3)

    def test_collection_neural_observation_rejects_nonfinite_counts_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            result = collection_neural.observe_search_outcome(
                game="포켓몬", region="KR", family="web", query="q", rows=[],
                relevant_count="NaN", official_count=float("inf"), labels_path=labels,
            )
            self.assertTrue(result["eligible"])
            self.assertEqual(result["added"], 1)
            payload = json.loads(labels.read_text(encoding="utf-8"))
            self.assertEqual(payload["labels"][0]["relevant"], 0)
            self.assertEqual(payload["labels"][0]["official"], 0)

    def test_malformed_model_numeric_contracts_fail_closed(self):
        bad_collection = {
            "schema": collection_neural.SCHEMA,
            "active": True,
            "feature_fingerprint": collection_neural.FEATURE_FINGERPRINT,
            "hidden": "NaN",
            "feature_count": collection_neural.FEATURE_COUNT,
            "label_count": collection_neural.MIN_INDEPENDENT_LABELS,
        }
        self.assertFalse(collection_neural._validate_model_payload(bad_collection))
        self.assertFalse(repair_neural._validate_model_payload({"schema": repair_neural.SCHEMA, "active": True, "hidden": "NaN"}))

    def _assert_training_lock_wraps_inner(self, module, kwargs):
        state = {"held": False}

        @contextmanager
        def lock(*_args, **_kwargs):
            self.assertFalse(state["held"])
            state["held"] = True
            try:
                yield
            finally:
                state["held"] = False

        def inner(**_kwargs):
            self.assertTrue(state["held"])
            return {"reason": "inner-called"}

        with mock.patch.object(module, "exclusive_file_lock", side_effect=lock), \
             mock.patch.object(module, "_train_if_ready_unlocked", side_effect=inner):
            result = module.train_if_ready(**kwargs)
        self.assertEqual(result["reason"], "inner-called")
        self.assertFalse(state["held"])

    def test_all_neural_training_writes_are_cross_process_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._assert_training_lock_wraps_inner(collection_neural, {
                "labels_path": root / "collection-labels.json",
                "model_path": root / "collection-model.json",
                "report_path": root / "collection-report.json",
            })
            self._assert_training_lock_wraps_inner(job_neural, {
                "labels_path": root / "job-labels.json",
                "model_path": root / "job-model.json",
                "report_path": root / "job-report.json",
            })
            self._assert_training_lock_wraps_inner(repair_neural, {
                "labels_path": root / "repair-labels.json",
                "model_path": root / "repair-model.json",
                "report_path": root / "repair-report.json",
                "current_rule_fingerprints": {},
            })


if __name__ == "__main__":
    unittest.main()
