#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path

from instagram_tcg_content.cardinfo_quality_learning import (
    BASE_PROFILE,
    FEATURES,
    PROJECT,
    TASK_ID,
    append_quality_label,
    audit_labels,
    build_rule_profile,
    load_model,
    rank_variant,
    train_quality_model,
    issue_tags_from_features,
)


class CardInfoQualityLearningTests(unittest.TestCase):
    def _row(self, index, *, label=0, issues=None, owner="owner-a"):
        return {
            "project": PROJECT,
            "task_id": TASK_ID,
            "artifact_id": f"artifact-{index}",
            "origin_group": f"origin-{index}",
            "owner_group": owner,
            "label_source": "user_feedback",
            "label_reference": f"chat-{index}",
            "synthetic": False,
            "natural_quality_label": label,
            "observed_at": f"2026-09-{1 + index:02d}T10:00:00+09:00",
            "labeled_at": f"2026-09-{1 + index:02d}T10:01:00+09:00",
            "issue_tags": list(issues or []),
            "features": {name: 0.45 for name in FEATURES},
        }

    def test_early_phase_repeated_feedback_builds_bounded_profile(self):
        rows = [
            self._row(0, issues=["crowded_text", "low_whitespace", "unnatural_copy"]),
            self._row(1, issues=["crowded_text", "low_whitespace", "unnatural_copy"]),
            self._row(2, issues=["crowded_text", "low_whitespace", "unnatural_copy"]),
        ]
        profile = build_rule_profile(rows)
        self.assertEqual(profile["mode"], "RULES_ONLY_EARLY_PHASE")
        self.assertFalse(profile["locked_master_mutation_allowed"])
        self.assertLess(profile["max_text_density"], BASE_PROFILE["max_text_density"])
        self.assertGreater(profile["min_whitespace_ratio"], BASE_PROFILE["min_whitespace_ratio"])
        self.assertIn("crowded_text", profile["recurring_issue_counts"])
        self.assertTrue(any("자연스러운" in line for line in profile["guidance"]))

    def test_low_quality_metrics_generate_deterministic_issue_tags(self):
        features = {name: 0.9 for name in FEATURES}
        features["text_density_fit"] = 0.4
        features["whitespace_balance"] = 0.5
        features["hierarchy_clarity"] = 0.6
        tags = issue_tags_from_features(features)
        self.assertIn("crowded_text", tags)
        self.assertIn("low_whitespace", tags)
        self.assertIn("weak_hierarchy", tags)
        self.assertNotIn("poor_number_readability", tags)

    def test_single_unverified_pattern_does_not_mutate_profile(self):
        rows = [self._row(0, issues=["crowded_text"])]
        profile = build_rule_profile(rows)
        self.assertEqual(profile["max_text_density"], BASE_PROFILE["max_text_density"])
        self.assertEqual(profile["guidance"], [])

    def test_atomic_append_rejects_duplicate_artifact_and_origin(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "quality_labels.json"
            first = append_quality_label(self._row(0), path)
            self.assertEqual(first["status"], "QUALITY_REAL_LABEL_APPENDED")
            self.assertEqual(first["label_count"], 1)
            with self.assertRaisesRegex(ValueError, "DUPLICATE_ARTIFACT_ID"):
                append_quality_label(self._row(0), path)
            duplicate_origin = self._row(1)
            duplicate_origin["origin_group"] = "origin-0"
            with self.assertRaisesRegex(ValueError, "DUPLICATE_ORIGIN_GROUP"):
                append_quality_label(duplicate_origin, path)
            stored = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(stored["rows"]), 1)
            self.assertTrue(stored["synthetic_labels_forbidden"])

    def test_ai_self_or_synthetic_labels_fail_closed(self):
        synthetic = self._row(0)
        synthetic["synthetic"] = True
        audit = audit_labels([synthetic])
        self.assertEqual(audit["valid_real_rows"], 0)
        self.assertIn("QUALITY_LABEL_SCHEMA_ERROR", audit["readiness_reasons"])

        ai = self._row(1)
        ai["label_source"] = "ai_self_label"
        audit = audit_labels([ai])
        self.assertEqual(audit["valid_real_rows"], 0)

    def test_positive_label_cannot_smuggle_issue_tags(self):
        row = self._row(0, label=1, issues=["crowded_text"])
        audit = audit_labels([row])
        self.assertEqual(audit["valid_real_rows"], 0)
        self.assertIn("QUALITY_LABEL_SCHEMA_ERROR", audit["readiness_reasons"])

    def test_below_1000_never_trains_and_never_authorizes_production(self):
        rows = [self._row(i, label=i % 2, issues=[] if i % 2 else ["weak_focus"]) for i in range(20)]
        report = train_quality_model(rows)
        self.assertEqual(report["status"], "QUALITY_MODEL_UPDATE_SKIPPED_KEEP_RULES")
        self.assertIsNone(report["model"])
        ranked = rank_variant({name: 0.8 for name in FEATURES}, None)
        self.assertEqual(ranked["status"], "QUALITY_RULES_ONLY")
        self.assertFalse(ranked["can_verify"])
        self.assertFalse(ranked["can_authorize_production"])

    def test_missing_or_rejected_model_loads_as_none(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.json"
            self.assertIsNone(load_model(path))
            path.write_text(json.dumps({"status": "QUALITY_MODEL_REJECTED_KEEP_RULES"}), encoding="utf-8")
            self.assertIsNone(load_model(path))


if __name__ == "__main__":
    unittest.main()
