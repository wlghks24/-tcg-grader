from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import verified_neural_self_refine as neural


class VerifiedNeuralSelfRefineV210Tests(unittest.TestCase):
    def test_safety_contract_and_activation_threshold(self):
        self.assertEqual((4, 8, 12), neural.HIDDEN_SIZES)
        self.assertEqual(1000, neural.MIN_INDEPENDENT_LABELS)
        self.assertFalse(neural.SAFETY["learned_text_executable"])
        self.assertFalse(neural.SAFETY["source_patch_generation"])
        self.assertTrue(neural.SAFETY["allowlisted_rules_only"])
        self.assertTrue(neural.SAFETY["full_regression_required_for_training_label"])
        self.assertTrue(neural.SAFETY["neural_output_is_priority_only"])

    def test_full_regression_ingest_is_independent_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "repair.json"
            labels = root / "labels.json"
            row = {
                "rule_id": neural.RULE_ORDER[0],
                "rule_fingerprint": "a" * 24,
                "path": ".github/workflows/a.yml",
                "stage": "CI_ACTION_RUNTIME_DEPRECATED",
                "outcome": "verified_pass",
                "before_hash": "1" * 20,
                "after_hash": "2" * 20,
            }
            state.write_text(json.dumps({"history": [row]}), encoding="utf-8")
            first = neural.ingest_full_regression_state(state, labels_path=labels)
            second = neural.ingest_full_regression_state(state, labels_path=labels)
            self.assertEqual(1, first["added"])
            self.assertEqual(0, second["added"])
            payload = json.loads(labels.read_text(encoding="utf-8"))
            self.assertEqual(1, len(payload["labels"]))
            self.assertEqual("full_regression", payload["labels"][0]["verification_level"])

    def test_training_compares_all_hidden_sizes_and_respects_rule_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels_path = root / "labels.json"
            model_path = root / "model.json"
            report_path = root / "report.json"
            fingerprints = {rule_id: "f" * 24 for rule_id in neural.RULE_ORDER}
            rows = []
            for i in range(1000):
                rule_id = neural.RULE_ORDER[i % len(neural.RULE_ORDER)]
                sample_id = hashlib.sha256(f"sample-{i}".encode()).hexdigest()[:24]
                rows.append({
                    "sample_id": sample_id,
                    "rule_id": rule_id,
                    "rule_fingerprint": fingerprints[rule_id],
                    "path": f"file-{i % 41}.py",
                    "stage": f"STAGE_{i % 13}",
                    "error_family": "runtime",
                    "learned_solution_reuse": False,
                    "learned_solution_confidence": 0.0,
                    "auto_repair_allowed": True,
                    "outcome": bool((i % 4) in (0, 1)),
                    "verification_level": "full_regression",
                    "recorded_at": f"2026-09-08T00:{i // 60:02d}:{i % 60:02d}+00:00",
                })
            labels_path.write_text(json.dumps({
                "schema": neural.SCHEMA,
                "labels": rows,
                "safety": neural.SAFETY,
            }), encoding="utf-8")
            old_epochs = neural.EPOCHS
            old_acc = neural.ACTIVATION_MIN_ACCURACY
            old_gain = neural.ACTIVATION_MIN_LOGLOSS_GAIN
            try:
                neural.EPOCHS = 2
                neural.ACTIVATION_MIN_ACCURACY = 0.0
                neural.ACTIVATION_MIN_LOGLOSS_GAIN = -100.0
                trained = neural.train_if_ready(
                    labels_path=labels_path,
                    model_path=model_path,
                    report_path=report_path,
                    current_rule_fingerprints=fingerprints,
                )
            finally:
                neural.EPOCHS = old_epochs
                neural.ACTIVATION_MIN_ACCURACY = old_acc
                neural.ACTIVATION_MIN_LOGLOSS_GAIN = old_gain
            self.assertEqual([4, 8, 12], [row["hidden"] for row in trained["candidates"]])
            self.assertTrue(trained["active"])
            self.assertTrue(model_path.is_file())
            issue = {
                "auto_repair_rule": neural.RULE_ORDER[0],
                "path": "file-1.py",
                "stage": "STAGE_1",
                "auto_repair_allowed": True,
            }
            score = neural.score_issue(
                issue,
                current_rule_fingerprints=fingerprints,
                model_path=model_path,
            )
            self.assertTrue(score["active"])
            stale = neural.score_issue(
                issue,
                current_rule_fingerprints={**fingerprints, neural.RULE_ORDER[0]: "0" * 24},
                model_path=model_path,
            )
            self.assertFalse(stale["active"])

    def test_corrupt_primary_labels_recover_verified_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels_path = root / "labels.json"
            backup_path = root / "labels.json.bak"
            sample = {
                "sample_id": hashlib.sha256(b"backup-neural-label").hexdigest()[:24],
                "rule_id": neural.RULE_ORDER[0],
                "rule_fingerprint": "a" * 24,
                "path": "x.py",
                "stage": "RESOURCE_HANDLE_LEAK_RISK",
                "error_family": "runtime",
                "learned_solution_reuse": False,
                "learned_solution_confidence": 0.0,
                "auto_repair_allowed": True,
                "outcome": True,
                "verification_level": "full_regression",
                "recorded_at": "2026-09-08T00:00:00+00:00",
            }
            backup_path.write_text(json.dumps({"schema": neural.SCHEMA, "labels": [sample]}), encoding="utf-8")
            labels_path.write_text("{broken", encoding="utf-8")
            payload, source, recovered = neural._load_labels_with_source(labels_path)
            self.assertEqual(1, len(payload["labels"]))
            self.assertEqual("backup", source)
            self.assertTrue(recovered)

    def test_corrupt_primary_model_recovers_last_known_good_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model_path = root / "model.json"
            backup_path = root / "model.json.bak"
            base = neural._init_model(4, 17)
            payload = {
                "schema": neural.SCHEMA,
                "active": True,
                "feature_count": neural.FEATURE_COUNT,
                "hidden": 4,
                "w1": base["w1"],
                "b1": base["b1"],
                "w2": base["w2"],
                "b2": base["b2"],
                "metrics": {"accuracy": 0.7, "logloss": 0.5},
                "calibration_slope": 1.0,
                "calibration_offset": 0.0,
                "rule_fingerprints": {neural.RULE_ORDER[0]: "a" * 24},
            }
            backup_path.write_text(json.dumps(payload), encoding="utf-8")
            model_path.write_text("{broken", encoding="utf-8")
            model, source, recovered = neural._load_model_with_source(model_path)
            self.assertIsNotNone(model)
            self.assertEqual("backup", source)
            self.assertTrue(recovered)

    def test_stale_rule_labels_do_not_count_toward_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labels_path = root / "labels.json"
            report_path = root / "report.json"
            rows = []
            for i in range(1000):
                rows.append({
                    "sample_id": hashlib.sha256(f"stale-{i}".encode()).hexdigest()[:24],
                    "rule_id": neural.RULE_ORDER[0],
                    "rule_fingerprint": "a" * 24,
                    "path": f"x-{i}.py",
                    "stage": "RESOURCE_HANDLE_LEAK_RISK",
                    "outcome": bool(i % 2),
                    "verification_level": "full_regression",
                    "recorded_at": "2026-09-08T00:00:00+00:00",
                })
            labels_path.write_text(json.dumps({"schema": 1, "labels": rows}), encoding="utf-8")
            status = neural.train_if_ready(
                labels_path=labels_path,
                model_path=root / "model.json",
                report_path=report_path,
                current_rule_fingerprints={neural.RULE_ORDER[0]: "b" * 24},
            )
            self.assertEqual(0, status["label_count"])
            self.assertEqual(1000, status["stale_rule_fingerprint_labels"])
            self.assertFalse(status["active"])


if __name__ == "__main__":
    unittest.main()
