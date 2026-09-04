#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

import selfrefine_domain_boundary_guard as boundary
import selfrefine_crosscheck_gate as crosscheck
from shared_self_learning.contracts import assert_passive_exchange_payload
from shared_self_learning.engine import (
    bounded_retry_decision,
    classify_conflict,
    classify_regression_result,
    compare_record_sets,
    confidence_score,
    enrich_error,
    evidence_fingerprint,
    normalize_error_signature,
    rank_candidates,
)

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
        self.assertEqual(main["shared_error_signature"], insta["shared_error_signature"])
        self.assertEqual(main["shared_evidence_fingerprint"], insta["shared_evidence_fingerprint"])

    def test_pure_shared_algorithm_contracts(self):
        a = normalize_error_signature("HTTP_429", "A\\B.py", "failed at line 10 id 0xabc")
        b = normalize_error_signature("HTTP_429", "a/b.py", "failed at line 99 id 0xdef")
        self.assertEqual(a, b)
        self.assertEqual(
            evidence_fingerprint({"b": 2, "a": 1}),
            evidence_fingerprint({"a": 1, "b": 2}),
        )
        self.assertEqual(confidence_score([0.9, 0.8], [0.1]), 0.7)
        ranked = rank_candidates([
            {"canonical_key": "b", "verification": "candidate", "confidence": 0.99},
            {"canonical_key": "a", "verification": "verified", "confidence": 0.70},
        ])
        self.assertEqual(ranked[0]["canonical_key"], "a")
        self.assertEqual(classify_regression_result(4, 0), "passed")
        self.assertEqual(classify_regression_result(4, 2), "improved")
        self.assertEqual(classify_regression_result(2, 4), "regressed")
        self.assertEqual(classify_conflict("1000", "2000"), "conflict")
        retry = bounded_retry_decision("HTTP_429", 5, max_retries=5)
        self.assertFalse(retry["retry_allowed"])
        self.assertEqual(retry["action"], "quarantine_review")

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
        self.assertFalse(compared["values_averaged"])

    def test_conflict_stays_conflict_not_average_and_requires_reverification(self):
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
        compared = result["comparisons"][0]
        self.assertEqual(compared["status"], "conflict")
        self.assertTrue(compared["requires_reverification"])
        self.assertFalse(compared["values_averaged"])

    def test_only_matching_canonical_key_is_compared(self):
        base = {
            "information_family": "market_price", "canonical_key": "op|001",
            "value": "1000", "currency": "KRW", "language": "KR", "variant": "",
            "source_code": "A", "source_locator": "a", "checked_at_kst": "x",
            "verification": "candidate", "confidence": 0.5, "lineage_key": "a",
        }
        other = dict(base)
        other.update({"canonical_key": "op|002", "source_code": "B", "lineage_key": "b"})
        self.assertEqual(compare_record_sets([base], [other])["comparisons"], [])

    def test_exchange_payload_fails_closed_on_execution_markers(self):
        markers = [
            "exec('x')", "eval('1+1')", "importlib.import_module('x')",
            "runpy.run_module('x')", "pickle.loads(blob)", "__import__('x')",
            "compile('x','','exec')", "marshal.loads(blob)", "subprocess.run(cmd)",
            "os.system('x')",
        ]
        for marker in markers:
            with self.subTest(marker=marker):
                with self.assertRaises(ValueError):
                    assert_passive_exchange_payload({"value": marker})

    def test_crosscheck_loader_rejects_outside_path_and_malicious_json(self):
        original = crosscheck.EXCHANGE
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                exchange = root / "crosscheck_exchange"
                exchange.mkdir()
                crosscheck.EXCHANGE = exchange

                bad = exchange / "bad.json"
                bad.write_text(json.dumps({"records": [{"value": "eval('x')"}]}), encoding="utf-8")
                with self.assertRaises(ValueError):
                    crosscheck._load_records(bad)

                outside = root / "outside.json"
                outside.write_text("[]", encoding="utf-8")
                with self.assertRaises(ValueError):
                    crosscheck._load_records(outside)
        finally:
            crosscheck.EXCHANGE = original

    def test_exchange_directory_has_no_executable_code(self):
        exchange = ROOT / "crosscheck_exchange"
        forbidden = {".py", ".js", ".sh", ".bat", ".cmd", ".pkl", ".pickle", ".joblib"}
        self.assertFalse([p for p in exchange.rglob("*") if p.is_file() and p.suffix.lower() in forbidden])

    def test_shared_engine_has_no_file_network_or_process_runtime_imports(self):
        forbidden = {
            "pathlib", "os", "subprocess", "sqlite3", "requests", "urllib", "http",
            "socket", "tempfile", "shelve", "pickle", "dbm", "shutil",
            "instagram_tcg_content",
        }
        for path in (ROOT / "shared_self_learning").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imports = set()
            calls = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
            self.assertFalse(imports & forbidden, (path, imports & forbidden))
            self.assertFalse(calls & {"open", "exec", "eval", "compile", "__import__"})

    def test_domain_state_files_are_disjoint_and_ignored(self):
        policy = json.loads((ROOT / "selfrefine_domain_policy.json").read_text(encoding="utf-8"))
        main = set(policy["domains"]["main"]["state_files"].values())
        insta = set(policy["domains"]["instagram_content"]["state_files"].values())
        self.assertFalse(main & insta)
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for name in main | insta:
            self.assertIn(name, ignore)

    def test_formal_crosscheck_schema_exists(self):
        schema = json.loads((ROOT / "crosscheck_exchange" / "schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertIn("record", schema["$defs"])
        self.assertFalse(schema["$defs"]["record"]["additionalProperties"])

    def test_shared_change_triggers_both_domain_ci(self):
        instagram = (ROOT / ".github/workflows/instagram-tcg-selfrefine.yml").read_text(encoding="utf-8")
        main = (ROOT / ".github/workflows/selfrefine-full-repo.yml").read_text(encoding="utf-8")
        self.assertIn("'shared_self_learning/**'", instagram)
        self.assertIn("  pull_request:\n", main)

    def test_boundary_guard_self_check_passes(self):
        self.assertEqual(boundary.main(), 0)

    def test_crosscheck_self_test(self):
        crosscheck.self_test()


if __name__ == "__main__":
    unittest.main()
