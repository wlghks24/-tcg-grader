#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import selfrefine_error_quarantine as quarantine
import verified_code_repair_rules as repairs

ROOT = Path(__file__).resolve().parent


class SelfrefineErrorQuarantineV20Tests(unittest.TestCase):
    def _issue(self):
        return {
            "error_signature": "a" * 20,
            "stage": "CI_ACTION_RUNTIME_DEPRECATED",
            "path": ".github/workflows/selfrefine-full-repo.yml",
            "evidence": "old action runtime",
            "state": "open",
        }

    def test_error_code_is_isolated_then_full_regression_promotes_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "q.json"
            first = quarantine.observe_open_errors([self._issue()], state_path=state)
            row = first["errors"][0]
            self.assertEqual(
                row["error_code"],
                "SELFREFINE.CI_RUNTIME.CI_ACTION_RUNTIME_DEPRECATED",
            )
            self.assertEqual(row["isolation_state"], "isolated")
            self.assertTrue(row["auto_repair_allowed"])
            self.assertFalse(row["learned_solution_reuse"])

            applied = [{
                "error_signature": row["error_signature"],
                "rule_id": repairs.ACTION_RULE_ID,
                "path": row["path"],
                "stage": row["stage"],
            }]
            local = quarantine.record_repair_outcomes(
                applied, [], state_path=state
            )
            self.assertEqual(local["local_resolution_passed"], 1)
            self.assertEqual(local["verified_resolution_learned"], 0)

            recurrent_before_full = quarantine.observe_open_errors(
                [self._issue()], state_path=state
            )["errors"][0]
            self.assertFalse(recurrent_before_full["learned_solution_reuse"])

            promoted = quarantine.promote_full_regression_resolution(
                row["error_signature"],
                repairs.ACTION_RULE_ID,
                state_path=state,
            )
            self.assertEqual(promoted["promoted"], 1)

            recurrent = quarantine.observe_open_errors(
                [self._issue()], state_path=state
            )
            rerow = recurrent["errors"][0]
            self.assertTrue(rerow["learned_solution_reuse"])
            self.assertGreater(rerow["learned_solution_confidence"], 0.5)
            self.assertEqual(recurrent["summary"]["learned_solution_reuse"], 1)

    def test_two_failed_verifications_quarantine_error_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "q.json"
            row = quarantine.observe_open_errors([self._issue()], state_path=state)["errors"][0]
            applied = [{
                "error_signature": row["error_signature"],
                "rule_id": repairs.ACTION_RULE_ID,
                "path": row["path"],
                "stage": row["stage"],
            }]
            remaining = [dict(row, state="open")]
            quarantine.record_repair_outcomes(applied, remaining, state_path=state)
            quarantine.record_repair_outcomes(applied, remaining, state_path=state)
            later = quarantine.observe_open_errors([self._issue()], state_path=state)["errors"][0]
            self.assertEqual(later["isolation_state"], "quarantined")
            self.assertFalse(later["auto_repair_allowed"])

    def test_unknown_error_is_isolated_but_never_auto_patched(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "q.json"
            issue = {
                "error_signature": "b" * 20,
                "stage": "PYTHON_SYNTAX",
                "path": "unknown_module.py",
                "evidence": "SyntaxError: arbitrary",
                "state": "open",
                "fix_rule": "eval('bad')",
            }
            row = quarantine.observe_open_errors([issue], state_path=state)["errors"][0]
            self.assertEqual(row["error_family"], "syntax")
            self.assertFalse(row["auto_repair_allowed"])
            self.assertIsNone(row["auto_repair_rule"])

    def test_past_verified_feature_contract_and_ocr_fixes_are_replayable(self):
        old_feature = (
            '    page = safe_read_text(base / "index.html")\n'
            + repairs.STALE_FEATURE_BLOCK
        )
        fixed_feature = repairs.transform_for_rule(
            repairs.FEATURE_VISION_RULE_ID, repairs.FEATURE_CONTRACT_PATH, old_feature
        )
        self.assertIn('vision_engine = safe_read_text(base / "grading_vision_engine.js")', fixed_feature)
        self.assertIn('"eightZoneWorst"', fixed_feature)
        self.assertFalse(repairs.detect_text_issues(repairs.FEATURE_CONTRACT_PATH, fixed_feature))

        old_ocr = '    assert contract["ok"] and contract["implemented"] == contract["total"] == 25\n'
        fixed_ocr = repairs.transform_for_rule(
            repairs.OCR_COUNT_RULE_ID, repairs.OCR_CONTRACT_PATH, old_ocr
        )
        self.assertIn('len(contract["features"])', fixed_ocr)
        self.assertFalse(repairs.detect_text_issues(repairs.OCR_CONTRACT_PATH, fixed_ocr))

    def test_current_repository_has_no_known_repair_regression(self):
        paths = set(repairs.CORE_WORKFLOWS) | {
            repairs.RESOURCE_GUARD_PATH,
            repairs.FEATURE_CONTRACT_PATH,
            repairs.OCR_CONTRACT_PATH,
        }
        failures = {}
        for relative in sorted(paths):
            path = ROOT / relative
            if not path.is_file():
                continue
            issues = repairs.detect_text_issues(relative, path.read_text(encoding="utf-8"))
            if issues:
                failures[relative] = issues
        self.assertFalse(failures, failures)

    def test_schema_v2_local_success_is_not_inherited_as_full_verified_learning(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "q.json"
            state.write_text(json.dumps({
                "schema": 2,
                "entries": {
                    "a" * 20: {
                        "error_code": "SELFREFINE.CI_RUNTIME.CI_ACTION_RUNTIME_DEPRECATED",
                        "family": "ci_runtime",
                        "stage": "CI_ACTION_RUNTIME_DEPRECATED",
                        "path": ".github/workflows/selfrefine-full-repo.yml",
                        "occurrences": 1,
                        "resolved_count": 1,
                        "verified_successes": 3,
                        "verified_failures": 0,
                        "consecutive_verification_failures": 0,
                        "last_verified_rule": repairs.ACTION_RULE_ID,
                        "status": "resolved",
                        "quarantined": False,
                    }
                },
                "history": [],
            }), encoding="utf-8")
            loaded = quarantine._load(state)
            row = loaded["entries"]["a" * 20]
            self.assertEqual(row["local_successes"], 3)
            self.assertEqual(row["verified_successes"], 0)
            self.assertIsNone(row["last_verified_rule"])
            self.assertEqual(row["last_local_rule"], repairs.ACTION_RULE_ID)
            self.assertEqual(row["status"], "resolved_local")

    def test_domain_state_files_are_separate_and_ignored(self):
        policy = json.loads((ROOT / "selfrefine_domain_policy.json").read_text(encoding="utf-8"))
        main_state = policy["domains"]["main"]["state_files"]["error_quarantine"]
        insta_state = policy["domains"]["instagram_content"]["state_files"]["error_quarantine"]
        self.assertNotEqual(main_state, insta_state)
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(main_state, ignored)
        self.assertIn(insta_state, ignored)


if __name__ == "__main__":
    unittest.main()
