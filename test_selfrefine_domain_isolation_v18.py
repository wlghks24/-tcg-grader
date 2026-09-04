#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

import selfrefine_domain_boundary_guard as boundary
import selfrefine_crosscheck_gate as crosscheck
from shared_self_learning.engine import enrich_error, compare_record_sets


ROOT = Path(__file__).resolve().parent


class SelfrefineDomainIsolationV18Tests(unittest.TestCase):
    def test_shared_learning_key_is_namespaced_and_state_is_not_shared(self):
        row = {"stage": "HTTP_429", "path": "collector.py", "evidence": "rate limited", "retry_count": 1}
        main = enrich_error("main", row)
        insta = enrich_error("instagram_content", row)
        self.assertNotEqual(main["shared_learning_key"], insta["shared_learning_key"])
        self.assertEqual(main["shared_retry_bucket"], insta["shared_retry_bucket"])
        self.assertEqual(main["shared_priority_score"], insta["shared_priority_score"])
        self.assertEqual(main["learning_namespace"], "main")
        self.assertEqual(insta["learning_namespace"], "instagram_content")

    def test_crosscheck_agreement_never_promotes_candidate(self):
        common = {
            "information_family": "promo_event",
            "canonical_key": "pokemon|jp|event-1",
            "value": "2026-09-10",
            "currency": "",
            "language": "JP",
            "variant": "",
            "source_code": "A",
            "source_locator": "https://example.invalid/a",
            "checked_at_kst": "2026-09-04T13:00:00+09:00",
            "verification": "verified",
            "confidence": 0.95,
            "lineage_key": "main-a",
        }
        other = dict(common)
        other.update({"source_code": "B", "verification": "candidate", "lineage_key": "insta-b"})
        result = compare_record_sets([common], [other])
        self.assertEqual(result["agree"], 1)
        compared = result["comparisons"][0]
        self.assertFalse(compared["verification_promotion"])
        self.assertEqual(compared["instagram_content"]["verification"], "candidate")
        self.assertFalse(compared["learning_state_merged"])

    def test_conflict_stays_conflict_not_average(self):
        a = {
            "information_family": "market_price", "canonical_key": "op|001",
            "value": "1000", "currency": "KRW", "language": "KR", "variant": "",
            "source_code": "A", "source_locator": "a", "checked_at_kst": "x",
            "verification": "verified", "confidence": 1, "lineage_key": "a",
        }
        b = dict(a)
        b.update({"value": "2000", "source_code": "B", "lineage_key": "b"})
        result = compare_record_sets([a], [b])
        self.assertEqual(result["conflict"], 1)
        self.assertEqual(result["comparisons"][0]["status"], "conflict")

    def test_exchange_directory_has_no_executable_code(self):
        exchange = ROOT / "crosscheck_exchange"
        forbidden = {".py", ".js", ".sh", ".bat", ".cmd", ".pkl", ".pickle", ".joblib"}
        self.assertFalse([p for p in exchange.rglob("*") if p.is_file() and p.suffix.lower() in forbidden])

    def test_shared_engine_has_no_file_or_process_runtime_imports(self):
        forbidden = {"pathlib", "os", "subprocess", "sqlite3", "requests", "instagram_tcg_content"}
        for path in (ROOT / "shared_self_learning").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
            self.assertFalse(imports & forbidden, (path, imports & forbidden))

    def test_domain_ledgers_are_distinct_and_ignored(self):
        policy = json.loads((ROOT / "selfrefine_domain_policy.json").read_text(encoding="utf-8"))
        main = policy["domains"]["main"]["ledger"]
        insta = policy["domains"]["instagram_content"]["ledger"]
        self.assertNotEqual(main, insta)
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(main, ignore)
        self.assertIn(insta, ignore)

    def test_boundary_guard_self_check_passes(self):
        self.assertEqual(boundary.main(), 0)

    def test_crosscheck_self_test(self):
        crosscheck.self_test()


if __name__ == "__main__":
    unittest.main()
