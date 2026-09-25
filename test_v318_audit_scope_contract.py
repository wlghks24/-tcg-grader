#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
LEDGER = ROOT / "V318_FULL_REPO_AUDIT_FINDINGS.json"
AUDIT = ROOT / "test_full_repo_structural_audit_v318.py"


class V318AuditScopeContractTests(unittest.TestCase):
    def test_audit_is_fail_closed_and_unexecuted_is_not_pass(self):
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        self.assertTrue(data["principles"]["fail_closed"])
        self.assertFalse(data["principles"]["test_weakening_allowed"])
        self.assertFalse(data["principles"]["unexecuted_is_pass"])
        self.assertFalse(data["principles"]["external_expert_claim"])
        self.assertEqual(data["status"], "REVIEW_PENDING")
        self.assertTrue(AUDIT.is_file())

    def test_audit_covers_structural_runtime_and_data_safety(self):
        source = AUDIT.read_text(encoding="utf-8")
        for token in (
            "duplicate-top-level", "dangerous-call", "shell-true",
            "tls-verify-false", "strict-json", "node", "bash",
        ):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
