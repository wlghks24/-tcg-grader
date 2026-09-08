from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import verified_collection_neural as neural
from adaptive_collection_learner import AdaptiveCollectionLearner


class VerifiedCollectionNeuralV211Tests(unittest.TestCase):
    def test_safety_contract_and_activation_threshold(self):
        self.assertEqual((4, 8, 12), neural.HIDDEN_SIZES)
        self.assertEqual(1000, neural.MIN_INDEPENDENT_LABELS)
        self.assertTrue(neural.SAFETY["learns_strategy_not_facts"])
        self.assertTrue(neural.SAFETY["verified_observed_outcomes_only"])
        self.assertFalse(neural.SAFETY["official_trust_auto_promotion"])
        self.assertFalse(neural.SAFETY["candidate_database_auto_promotion"])
        self.assertFalse(neural.SAFETY["query_text_generation"])
        self.assertFalse(neural.SAFETY["verification_bypass"])
        self.assertTrue(neural.SAFETY["neural_output_is_priority_only"])
        self.assertTrue(neural.SAFETY["reserved_exploration_slots_unchanged"])

    def test_real_search_labels_are_bounded_verified_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            labels = Path(tmp) / "labels.json"
            now = datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc)
            official_rows = [{
                "title": "Pokemon official promo event",
                "url": "https://www.pokemon.com/us/pokemon-news/test",
            }]
            first = neural.observe_search_outcome(
                game="포켓몬",
                region="US",
                family="official-site",
                query="Pokemon TCG promo event",
                rows=official_rows,
                relevant_count=1,
                official_count=1,
                query_stats={"runs": 1, "hits": 1, "relevant": 1, "official": 1},
                labels_path=labels,
                now=now,
            )
            duplicate = neural.observe_search_outcome(
                game="포켓몬",
                region="US",
                family="official-site",
                query="Pokemon TCG promo event",
                rows=official_rows,
                relevant_count=1,
                official_count=1,
                query_stats={"runs": 2, "hits": 2, "relevant": 2, "official": 2},
                labels_path=labels,
                now=now,
            )
            empty = neural.observe_search_outcome(
                game="원피스",
                region="KR",
                family="topic:movie",
                query="원피스 카드 영화 특전",
                rows=[],
                relevant_count=0,
                official_count=0,
                query_stats={"runs": 1, "hits": 0, "empty": 1},
                labels_path=labels,
                now=now,
            )
            ambiguous = neural.observe_search_outcome(
                game="나루토",
                region="US",
                family="social:x.com",
                query="Naruto card event",
                rows=[{"title": "fan event lead", "url": "https://example.com/event"}],
                relevant_count=1,
                official_count=0,
                labels_path=labels,
                now=now,
            )
            errored = neural.observe_search_outcome(
                game="나루토",
                region="US",
                family="regional",
                query="Naruto card event",
                rows=[],
                relevant_count=0,
                official_count=0,
                error="TimeoutError",
                labels_path=labels,
                now=now,
            )
            self.assertEqual(1, first["added"])
            self.assertEqual(0, duplicate["added"])
            self.assertEqual("duplicate_same_collection_window", duplicate["reason"])
            self.assertEqual(1, empty["added"])
            self.assertFalse(ambiguous["eligible"])
            self.assertFalse(errored["eligible"])
            payload = json.loads(labels.read_text(encoding="utf-8"))
            self.assertEqual(2, len(payload["labels"]))
            self.assertEqual({True, False}, {row["outcome"] for row in payload["labels"]})

    def test_adaptive_plan_uses_neural_only_for_priority_and_keeps_reserved_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            learner = AdaptiveCollectionLearner(
                memory_path=root / "memory.json",
                backup_path=root / "memory.json.bak",
                report_path=root / "report.json",
            )

            def fake_score(row, **_kwargs):
                family = str(row.get("family") or "")
                score = 0.99 if family == "official-site" else 0.75 if family.startswith("social:") else 0.55
                return {
                    "active": True,
                    "score": score,
                    "reason": "test_priority_only",
                    "neural_output_is_priority_only": True,
                }

            with patch("adaptive_collection_learner.verified_collection_neural.score_query", side_effect=fake_score):
                plan = learner.plan_queries("나루토", max_queries=8)

            regional = [row for row in plan if row.get("family") == "regional"]
            self.assertEqual({"KR", "JP", "US"}, {row["region"] for row in regional})
            self.assertTrue(any(str(row.get("family") or "").startswith("topic:") for row in plan))
            self.assertTrue(any(str(row.get("family") or "").startswith("social:") for row in plan))
            self.assertTrue(any(row.get("family") in {"exploration", "official-site"} for row in plan))
            self.assertTrue(any(row.get("neural_priority_active") is True for row in plan))
            self.assertTrue(all("query" in row for row in plan))

    def test_training_compares_hidden_sizes_and_model_remains_priority_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels_path = root / "labels.json"
            model_path = root / "model.json"
            report_path = root / "report.json"
            rows = []
            for index in range(1000):
                positive = index % 2 == 0
                family = "official-site" if positive else "topic"
                rows.append({
                    "sample_id": hashlib.sha256(f"collection-{index}".encode()).hexdigest()[:24],
                    "game": neural.GAMES[index % len(neural.GAMES)],
                    "region": neural.REGIONS[index % 3],
                    "family": family,
                    "runs": 1 + index % 20,
                    "hits": 3 if positive else 0,
                    "relevant": 2 if positive else 0,
                    "official": 1 if positive else 0,
                    "errors": 0,
                    "empty": 0 if positive else 1,
                    "learned_score": 3.0 if positive else -0.5,
                    "verified_gap_priority": 0.0,
                    "coverage_gap_score": 0.0,
                    "outcome": positive,
                    "evidence": "official_result_observed" if positive else "successful_empty_search",
                    "observed_at": "2026-09-08T00:00:00+00:00",
                })
            labels_path.write_text(json.dumps({
                "schema": neural.SCHEMA,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "labels": rows,
                "safety": neural.SAFETY,
            }, ensure_ascii=False), encoding="utf-8")

            old_epochs = neural.EPOCHS
            old_accuracy = neural.ACTIVATION_MIN_ACCURACY
            old_gain = neural.ACTIVATION_MIN_LOGLOSS_GAIN
            try:
                neural.EPOCHS = 2
                neural.ACTIVATION_MIN_ACCURACY = 0.0
                neural.ACTIVATION_MIN_LOGLOSS_GAIN = -100.0
                trained = neural.train_if_ready(
                    labels_path=labels_path,
                    model_path=model_path,
                    report_path=report_path,
                    force=True,
                )
            finally:
                neural.EPOCHS = old_epochs
                neural.ACTIVATION_MIN_ACCURACY = old_accuracy
                neural.ACTIVATION_MIN_LOGLOSS_GAIN = old_gain

            self.assertEqual([4, 8, 12], [item["hidden"] for item in trained["candidates"]])
            self.assertTrue(trained["active"])
            scored = neural.score_query({
                "game": "포켓몬",
                "region": "US",
                "family": "official-site",
                "runs": 4,
                "hits": 8,
                "relevant": 4,
                "official": 3,
                "errors": 0,
                "empty": 0,
                "learned_score": 3.0,
            }, model_path=model_path)
            self.assertTrue(scored["active"])
            self.assertTrue(scored["neural_output_is_priority_only"])
            self.assertGreaterEqual(scored["score"], 0.0)
            self.assertLessEqual(scored["score"], 1.0)

    def test_less_than_1000_labels_never_activates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels = root / "labels.json"
            labels.write_text(json.dumps({
                "schema": neural.SCHEMA,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "labels": [],
            }), encoding="utf-8")
            result = neural.train_if_ready(
                labels_path=labels,
                model_path=root / "model.json",
                report_path=root / "report.json",
            )
            self.assertFalse(result["active"])
            self.assertEqual("waiting_for_independent_labels", result["reason"])

    def test_corrupt_label_primary_recovers_last_known_good_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels_path = root / "labels.json"
            backup_path = root / "labels.json.bak"
            sample = {
                "sample_id": hashlib.sha256(b"backup-label").hexdigest()[:24],
                "game": "포켓몬",
                "region": "KR",
                "family": "regional",
                "runs": 1,
                "hits": 1,
                "relevant": 1,
                "official": 1,
                "errors": 0,
                "empty": 0,
                "learned_score": 1.0,
                "verified_gap_priority": 0.0,
                "coverage_gap_score": 0.0,
                "outcome": True,
                "evidence": "official_result_observed",
                "observed_at": "2026-09-08T00:00:00+00:00",
            }
            backup_path.write_text(json.dumps({
                "schema": neural.SCHEMA,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "labels": [sample],
            }, ensure_ascii=False), encoding="utf-8")
            labels_path.write_text("{broken", encoding="utf-8")
            state = neural.status(labels_path=labels_path, model_path=root / "model.json")
            self.assertEqual(1, state["label_count"])
            self.assertEqual("backup", state["label_source"])
            self.assertTrue(state["label_recovered_from_backup"])

    def test_corrupt_or_nonfinite_model_is_rejected_and_valid_backup_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "model.json"
            backup_path = root / "model.json.bak"
            base = neural._init_model(4, 19)
            payload = {
                "schema": neural.SCHEMA,
                "active": True,
                "feature_fingerprint": neural.FEATURE_FINGERPRINT,
                "feature_count": neural.FEATURE_COUNT,
                "trained_at": "2026-09-08T00:00:00+00:00",
                "label_count": 1000,
                "hidden": 4,
                "w1": base["w1"],
                "b1": base["b1"],
                "w2": base["w2"],
                "b2": base["b2"],
                "metrics": {"accuracy": 0.7, "logloss": 0.5},
                "safety": neural.SAFETY,
            }
            backup_path.write_text(json.dumps(payload), encoding="utf-8")
            broken = dict(payload)
            broken["w1"] = [[float("nan")] * neural.FEATURE_COUNT for _ in range(4)]
            model_path.write_text(json.dumps(broken), encoding="utf-8")
            state = neural.status(labels_path=root / "labels.json", model_path=model_path)
            self.assertTrue(state["active"])
            self.assertEqual("backup", state["model_source"])
            self.assertTrue(state["model_recovered_from_backup"])

            backup_path.unlink()
            state = neural.status(labels_path=root / "labels.json", model_path=model_path)
            self.assertFalse(state["active"])
            self.assertEqual("none", state["model_source"])

    def test_status_exposes_training_progress_and_safe_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = neural.status(labels_path=root / "labels.json", model_path=root / "model.json")
            self.assertEqual(1000, state["labels_remaining"])
            self.assertEqual(0.0, state["progress_percent"])
            self.assertEqual("adaptive_public_search_priority_only", state["scope"])
            self.assertIn("official_release_fetch", state["deterministic_collectors"])
            self.assertIn("graded_photo_final_verification", state["deterministic_collectors"])


if __name__ == "__main__":
    unittest.main()
