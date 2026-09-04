#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import verified_code_repair_rules as repairs


ROOT = Path(__file__).resolve().parent


class VerifiedCodeRepairRulesV19Tests(unittest.TestCase):
    def test_current_guarded_files_have_no_known_regression(self):
        guarded = set(repairs.CORE_WORKFLOWS) | {repairs.RESOURCE_GUARD_PATH}
        failures = {}
        for relative in sorted(guarded):
            path = ROOT / relative
            if not path.exists():
                continue
            issues = repairs.detect_text_issues(relative, path.read_text(encoding="utf-8"))
            if issues:
                failures[relative] = issues
        self.assertFalse(failures, failures)

    def test_rules_are_idempotent_and_path_allowlisted(self):
        text = (
            "steps:\n"
            "  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n"
        )
        rel = ".github/workflows/selfrefine-full-repo.yml"
        first = repairs.transform_for_rule(repairs.ACTION_RULE_ID, rel, text)
        second = repairs.transform_for_rule(repairs.ACTION_RULE_ID, rel, first)
        self.assertEqual(first, second)
        self.assertIn(repairs.NODE24_ACTION_PINS["actions/checkout"], first)
        self.assertEqual(
            repairs.transform_for_rule(repairs.ACTION_RULE_ID, "not-allowlisted.yml", text),
            text,
        )

    def test_failed_rule_is_quarantined_after_two_consecutive_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            item = {
                "rule_id": repairs.RESOURCE_RULE_ID,
                "path": repairs.RESOURCE_GUARD_PATH,
                "stage": "RESOURCE_HANDLE_LEAK_RISK",
                "before_hash": "a",
                "after_hash": "b",
            }
            remaining = [{
                "stage": "RESOURCE_HANDLE_LEAK_RISK",
                "path": repairs.RESOURCE_GUARD_PATH,
                "state": "open",
            }]
            repairs.record_verification([item], remaining, state_path=state)
            result = repairs.record_verification([item], remaining, state_path=state)
            self.assertEqual(result["quarantined"], 1)

    def test_learned_text_cannot_select_or_create_patch(self):
        malicious = {
            "stage": "exec('bad')",
            "path": repairs.RESOURCE_GUARD_PATH,
            "fix_rule": "eval('bad')",
        }
        self.assertIsNone(repairs.rule_for_issue(malicious))


if __name__ == "__main__":
    unittest.main()
