#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from instagram_tcg_content.persisted_learning_export import export_snapshot
from shared_self_learning.contracts import PEER_LEARNING_FIELDS


def lesson(lesson_id: str) -> dict:
    return {
        "lesson_id": lesson_id,
        "subsystem": "factual_crosscheck_runtime",
        "issue_class": "nondeterministic_freshness_regression",
        "trigger_condition": "persisted snapshot freshness test depends on wall clock",
        "symptom_summary": "fixture becomes stale over time although production logic is unchanged",
        "root_cause_class": "wall_clock_coupled_test_fixture",
        "fix_pattern": "inject a fixed timezone-aware now into freshness regression tests",
        "prevention_rule_id": f"PREV-{lesson_id}",
        "verification_result": "passed",
        "regression_pass": True,
        "recurrence_count": 1,
        "applicable_scope": "both",
        "confidence_level": "high",
    }


class PeerLearningManifestContractV28Tests(unittest.TestCase):
    def test_manifest_learning_fields_match_runtime_exactly(self):
        manifest = json.loads(Path("TCG_CROSSCHECK/exchange_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(manifest["learning_fields"]), PEER_LEARNING_FIELDS)
        self.assertEqual(len(set(manifest["learning_fields"])), len(PEER_LEARNING_FIELDS))

    def test_instagram_learning_snapshot_uses_exact_fields(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "learning_snapshot.json"
            result = export_snapshot([lesson("IG-V28")], output)
            self.assertEqual(result["status"], "finalized")
            self.assertEqual(set(result["lessons"][0]), set(PEER_LEARNING_FIELDS))
            self.assertTrue(result["validation"]["learning_fields_only"])
            self.assertTrue(result["validation"]["write_readback_verified"])
            self.assertFalse(result["validation"]["learning_isolation_breach"])

    def test_empty_learning_run_preserves_last_good(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "learning_snapshot.json"
            first = export_snapshot([lesson("IG-LAST-GOOD")], output)
            self.assertEqual(first["status"], "finalized")
            second = export_snapshot([], output)
            self.assertEqual(second["status"], "finalized")
            self.assertTrue(second["preserved_last_good"])
            reread = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(reread["lessons"][0]["lesson_id"], "IG-LAST-GOOD")

    def test_forbidden_raw_state_fails_closed(self):
        bad = lesson("IG-RAW")
        bad["raw_log"] = "must not cross domain"
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(ValueError):
                export_snapshot([bad], Path(td) / "learning_snapshot.json")


if __name__ == "__main__":
    unittest.main()
