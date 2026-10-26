from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import adaptive_collection_learner as adaptive
import collection_learning_hardening_v142 as hardened
import verified_collection_neural as query
import verified_collection_job_neural as job


def observations(module, count=1000):
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [{
        "sample_id": hashlib.sha256(str(i).encode()).hexdigest()[:24],
        "game": "포켓몬", "region": "KR", "family": "official-site",
        "job_key": "releases.json", "outcome": bool(i % 2),
        "feature_history_timing": "pre_outcome",
        "evidence": "official_result_observed" if i % 2 else "successful_empty_search",
        "result_fingerprint": hashlib.sha256(str(i).encode()).hexdigest()[:16],
        "observed_at": (start + timedelta(minutes=i)).isoformat(),
    } for i in range(count)]


class TabletLearningProgressTests(unittest.TestCase):
    def test_base_and_hardened_query_features_exclude_current_outcome(self):
        original = hardened._ORIGINAL_OBSERVE_SEARCH or adaptive.AdaptiveCollectionLearner.observe_search
        for observe in (original, hardened._hardened_observe_search):
            with self.subTest(observe=observe.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                learner = adaptive.AdaptiveCollectionLearner(root / "memory.json", report_path=root / "report.json")
                with patch.object(learner, "_result_features", return_value=(5.0, True)), \
                     patch.object(query, "observe_search_outcome", return_value={}) as record:
                    observe(learner, "포켓몬", "포켓몬 카드 프로모", [
                        {"title": "포켓몬 프로모", "url": "https://pokemon.com/news"}
                    ])
                    first = record.call_args.kwargs["query_stats"]
                    self.assertEqual(0, first["runs"])
                    self.assertEqual(0, first["official"])
                    observe(learner, "포켓몬", "포켓몬 카드 프로모", [])
                    second = record.call_args.kwargs["query_stats"]
                    self.assertEqual(1, second["runs"])
                    self.assertEqual(1, second["official"])
                    self.assertEqual(0, first["official"])

    def test_no_history_does_not_copy_target_into_query_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            result = query.observe_search_outcome(
                game="포켓몬", region="KR", family="official-site", query="promo",
                rows=[{"url": "https://pokemon.com/news"}], relevant_count=1,
                official_count=1, labels_path=path,
            )
            self.assertEqual(1, result["added"])
            row = json.loads(path.read_text())["labels"][0]
            self.assertTrue(row["outcome"])
            self.assertEqual(0, row["official"])
            self.assertEqual(0, row["relevant"])

    def test_readiness_explains_total_class_and_temporal_gates(self):
        for module in (query, job):
            with self.subTest(module=module.__name__):
                rows = observations(module)
                self.assertEqual("waiting_for_independent_labels", module.learning_readiness(rows[:285])["reason"])
                one_class = [{**row, "outcome": True, "evidence": "official_result_observed"} for row in rows]
                progress = module.learning_readiness(one_class)
                self.assertEqual("waiting_for_class_balance", progress["reason"])
                self.assertEqual(100, progress["negative_labels_remaining"])
                one_batch = [{**row, "observed_at": rows[0]["observed_at"]} for row in rows]
                self.assertEqual("insufficient_temporal_protocol_split", module.learning_readiness(one_batch)["reason"])
                progress = module.learning_readiness(rows)
                self.assertTrue(progress["ready"])
                self.assertEqual({"train": 500, "tune": 150, "calibration": 150, "final_test": 200}, progress["split_counts"])

    def test_same_rejected_snapshot_skips_cpu_but_new_data_and_force_retry(self):
        for module in (query, job):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                rows = observations(module)
                labels = root / "labels.json"
                labels.write_text(json.dumps({"feature_fingerprint": module.FEATURE_FINGERPRINT, "labels": rows}))
                clean = module._load_labels(labels)["labels"]
                report = root / "report.json"
                report.write_text(json.dumps({
                    "training_snapshot_fingerprint": module._training_snapshot_fingerprint(clean),
                    "reason": "holdout_gate_not_met", "active": False,
                }))
                kwargs = dict(labels_path=labels, model_path=root / "model.json", report_path=report)
                with patch.object(module, "_train", side_effect=RuntimeError("training entered")) as train:
                    result = module.train_if_ready(**kwargs)
                    self.assertTrue(result["training_skipped"])
                    train.assert_not_called()
                    with self.assertRaisesRegex(RuntimeError, "training entered"):
                        module.train_if_ready(**kwargs, force=True)
                    rows[-1]["outcome"] = not rows[-1]["outcome"]
                    rows[-1]["evidence"] = "official_result_observed" if rows[-1]["outcome"] else "successful_empty_search"
                    labels.write_text(json.dumps({"feature_fingerprint": module.FEATURE_FINGERPRINT, "labels": rows}))
                    with self.assertRaisesRegex(RuntimeError, "training entered"):
                        module.train_if_ready(**kwargs)

    def test_snapshot_changes_on_feature_and_protocol_change(self):
        for module in (query, job):
            rows = observations(module)
            before = module._training_snapshot_fingerprint(rows)
            rows[-1]["runs"] = 10
            self.assertNotEqual(before, module._training_snapshot_fingerprint(rows))
            with patch.object(module, "EPOCHS", module.EPOCHS + 1):
                self.assertNotEqual(before, module._training_snapshot_fingerprint(observations(module)))

    def test_stale_and_rolling_full_label_store_can_retrain_without_count_growth(self):
        for module in (query, job):
            with self.subTest(module=module.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                rows = observations(module)
                labels = root / "labels.json"
                labels.write_text(json.dumps({"feature_fingerprint": module.FEATURE_FINGERPRINT, "labels": rows}))
                clean = module._load_labels(labels)["labels"]
                kwargs = dict(labels_path=labels, model_path=root / "model.json", report_path=root / "report.json")
                existing = {"label_count": 1000, "protocol_version": module.PROTOCOL_VERSION,
                            "training_snapshot_fingerprint": module._training_snapshot_fingerprint(clean)}
                with patch.object(module, "_load_model_with_source", return_value=(existing, "primary", False)), \
                     patch.object(module, "_runtime_model_reason", return_value=None), \
                     patch.object(module, "MAX_LABELS", 1000), \
                     patch.object(module, "_train", side_effect=RuntimeError("training entered")) as train:
                    self.assertEqual("active_model_reused_until_retrain_delta", module.train_if_ready(**kwargs)["reason"])
                    train.assert_not_called()
                    existing["training_snapshot_fingerprint"] = "prior-rolling-window"
                    with self.assertRaisesRegex(RuntimeError, "training entered"):
                        module.train_if_ready(**kwargs)

                with patch.object(module, "_load_model_with_source", return_value=(existing, "primary", False)), \
                     patch.object(module, "_runtime_model_reason", return_value="model_stale"), \
                     patch.object(module, "_train", side_effect=RuntimeError("training entered")):
                    with self.assertRaisesRegex(RuntimeError, "training entered"):
                        module.train_if_ready(**kwargs)

    def test_query_legacy_rows_preserved_but_cannot_satisfy_training_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "labels.json"
            rows = observations(query, 1015)
            for row in rows[:20]:
                row.pop("feature_history_timing")
            path.write_text(json.dumps({"feature_fingerprint": query.FEATURE_FINGERPRINT, "labels": rows}))
            kwargs = dict(labels_path=path, model_path=root / "model.json", report_path=root / "report.json")
            original = path.read_bytes()
            with patch.object(query, "_train", side_effect=RuntimeError("training entered")) as train:
                result = query.train_if_ready(**kwargs)
                train.assert_not_called()
                self.assertFalse(result["active"])
                self.assertEqual(1015, result["label_count"])
                self.assertEqual(995, result["eligible_training_labels"])
                self.assertEqual(20, result["legacy_feature_history_unverified_count"])
                self.assertEqual(5, result["labels_remaining"])
                self.assertEqual(original, path.read_bytes())
                for i in range(5):
                    query.observe_search_outcome(
                        game="포켓몬", region="KR", family="official-site", query=f"new search {i}",
                        rows=[{"url": "https://pokemon.com/news"}], relevant_count=1, official_count=1,
                        labels_path=path,
                    )
                state = query.status(labels_path=path, model_path=root / "model.json")
                self.assertEqual(1020, state["label_count"])
                self.assertEqual(1000, state["eligible_training_labels"])
                self.assertTrue(state["training_readiness"]["ready"])
                with self.assertRaisesRegex(RuntimeError, "training entered"):
                    query.train_if_ready(**kwargs)

    def test_query_unattested_history_not_marked_eligible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "labels.json"
            query.observe_search_outcome(
                game="포켓몬", region="KR", family="official-site", query="unattested",
                rows=[{"url": "https://pokemon.com/news"}], relevant_count=1, official_count=1,
                query_stats={"official": 5}, labels_path=path,
            )
            state = query.status(labels_path=path, model_path=Path(tmp) / "model.json")
            self.assertEqual(1, state["label_count"])
            self.assertEqual(0, state["eligible_training_labels"])
            self.assertEqual(1000, state["training_readiness"]["labels_remaining"])
            self.assertEqual(0.0, state["training_readiness"]["progress_percent"])
            # A new genuine observation in the same window can replace the old
            # timing-unknown sample without inflating the independent count.
            updated = query.observe_search_outcome(
                game="포켓몬", region="KR", family="official-site", query="unattested",
                rows=[{"url": "https://pokemon.com/news"}], relevant_count=1, official_count=1,
                query_stats={"official": 5}, history_is_pre_outcome=True, labels_path=path,
            )
            self.assertEqual(0, updated["added"])
            self.assertEqual(1, updated["updated"])
            state = query.status(labels_path=path, model_path=Path(tmp) / "model.json")
            self.assertEqual(1, state["eligible_training_labels"])

    def test_query_legacy_protocol_model_stays_inactive_during_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = {**query._init_model(4, 42), "schema": query.SCHEMA, "active": True,
                     "feature_fingerprint": query.FEATURE_FINGERPRINT, "feature_count": query.FEATURE_COUNT,
                     "label_count": 1000, "protocol_version": 2,
                     "trained_at": datetime.now(timezone.utc).isoformat(),
                     "metrics": {"accuracy": 0.9, "logloss": 0.1}}
            model_path = root / "model.json"
            model_path.write_text(json.dumps(model))
            before = model_path.read_bytes()
            score = query.score_query({}, model_path=model_path)
            self.assertFalse(score["active"])
            self.assertEqual("protocol_version_mismatch", score["reason"])
            result = query.train_if_ready(labels_path=root / "labels.json", model_path=model_path,
                                          report_path=root / "report.json")
            self.assertFalse(result["active"])
            self.assertEqual(before, model_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
