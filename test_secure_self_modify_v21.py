#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import verified_code_repair_rules as repairs


ROOT = Path(__file__).resolve().parent


class SecureSelfModifyV21Tests(unittest.TestCase):
    def _stale_workflow(self, root: Path) -> tuple[str, Path, dict]:
        relative = ".github/workflows/selfrefine-full-repo.yml"
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        original = (
            "steps:\n"
            "  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n"
        )
        target.write_text(original, encoding="utf-8")
        diagnostic = repairs.detect_text_issues(relative, original)[0]
        issue = {
            "path": relative,
            "state": "open",
            "error_signature": "c" * 20,
            "error_code": "SELFREFINE.CI_RUNTIME.CI_ACTION_RUNTIME_DEPRECATED",
            "error_family": "ci_runtime",
            "auto_repair_allowed": True,
            **diagnostic,
        }
        return original, target, issue

    def test_successful_self_modify_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, target, issue = self._stale_workflow(root)
            state = root / "repair-state.json"
            result = repairs.apply_issues([issue], root=root, state_path=state)
            self.assertEqual(result["applied_count"], 1)
            self.assertNotEqual(target.read_text(encoding="utf-8"), original)
            final = repairs.rollback_failed_repairs(
                result["applied"], [issue], [], root=root
            )
            self.assertEqual(final["verified_kept"], 1)
            self.assertEqual(final["restored"], 0)
            verified = repairs.record_verification(result["applied"], [], state_path=state)
            self.assertEqual(verified["verified_pass"], 1)
            self.assertNotEqual(target.read_text(encoding="utf-8"), original)

    def test_failed_self_modify_rolls_back_to_exact_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, target, issue = self._stale_workflow(root)
            state = root / "repair-state.json"
            result = repairs.apply_issues([issue], root=root, state_path=state)
            remaining = [dict(issue)]
            final = repairs.rollback_failed_repairs(
                result["applied"], [issue], remaining, root=root
            )
            self.assertEqual(final["restored"], 1)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            verified = repairs.record_verification(
                result["applied"], remaining, state_path=state
            )
            self.assertEqual(verified["verification_failed"], 1)

    def test_new_regression_rolls_back_even_when_original_error_disappears(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original, target, issue = self._stale_workflow(root)
            state = root / "repair-state.json"
            result = repairs.apply_issues([issue], root=root, state_path=state)
            regression = [{
                "stage": "PYTHON_SYNTAX",
                "path": "new_regression.py",
                "state": "open",
            }]
            final = repairs.rollback_failed_repairs(
                result["applied"], [issue], regression, root=root
            )
            self.assertEqual(final["restored"], 1)
            self.assertEqual(len(final["new_regressions"]), 1)
            self.assertEqual(target.read_text(encoding="utf-8"), original)
            verified = repairs.record_verification(
                result["applied"], regression, state_path=state
            )
            self.assertEqual(verified["verification_failed"], 1)

    def test_changed_rule_fingerprint_cannot_inherit_old_confidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "repair-state.json"
            state.write_text(json.dumps({
                "schema": 1,
                "rules": {
                    repairs.ACTION_RULE_ID: {
                        "fingerprint": "stale-definition",
                        "attempts": 999,
                        "successes": 999,
                        "failures": 0,
                        "consecutive_failures": 0,
                        "quarantined": False,
                    }
                },
                "history": [],
            }), encoding="utf-8")
            loaded = repairs._load_state(state)
            stats = loaded["rules"][repairs.ACTION_RULE_ID]
            self.assertEqual(stats["attempts"], 0)
            self.assertEqual(stats["successes"], 0)
            self.assertEqual(
                stats["fingerprint"], repairs.rule_fingerprint(repairs.ACTION_RULE_ID)
            )

    def test_policy_requires_fail_closed_secure_self_modify(self):
        policy = json.loads((ROOT / "selfrefine_domain_policy.json").read_text(encoding="utf-8"))
        rules = policy["rules"]
        self.assertTrue(rules["failed_self_modify_auto_rollback"])
        self.assertTrue(rules["new_regression_auto_rollback"])
        self.assertTrue(rules["repair_rule_fingerprint_required"])
        self.assertTrue(rules["process_safe_selfrefine_state"])
        self.assertFalse(rules["unknown_error_auto_repair"])
        self.assertFalse(rules["self_modify_git_write"])
        self.assertLessEqual(rules["self_modify_max_files_per_run"], 3)


if __name__ == "__main__":
    unittest.main()
