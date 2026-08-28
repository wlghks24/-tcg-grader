#!/usr/bin/env python3
"""ai_code_improver의 네트워크·Docker 비의존 회귀검사."""
from __future__ import annotations

import json
import tempfile
import concurrent.futures
import unittest
from pathlib import Path
from types import SimpleNamespace

import ai_code_improver as module


GOOD_CODE = """\
def normalize_name(value: str) -> str:
    return value.strip().lower()
"""
GOOD_GENERATED_TEST = """\
import unittest
from solution import normalize_name

class TestGenerated(unittest.TestCase):
    def test_trim(self):
        self.assertEqual(normalize_name(" A "), "a")
"""
GOOD_TRUSTED_TEST = """\
import unittest
from solution import normalize_name

class TestRegression(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(normalize_name(""), "")
"""


class FakeResponses:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception):
            raise payload
        return SimpleNamespace(output_text=json.dumps(payload))


class FakeClient:
    def __init__(self, payloads):
        self.responses = FakeResponses(payloads)


class FakeSandbox:
    def __init__(self, results=None, ready=True):
        self.results = list(results or [(True, "OK")])
        self.ready = ready
        self.executions = 0

    def preflight(self):
        return self.ready, "ready" if self.ready else "missing docker"

    def execute(self, code, generated_test, trusted_test):
        self.executions += 1
        return self.results.pop(0)


def candidate(code=GOOD_CODE, test=GOOD_GENERATED_TEST):
    return {"code": code, "test_code": test, "change_summary": "정규화 함수",
            "risk_level": "low", "dependencies": []}


class ImproverTests(unittest.TestCase):
    def test_markdown_single_fence_and_syntax(self):
        result = module.validate_python_source("```python\n" + GOOD_CODE + "\n```")
        self.assertTrue(result.ok)
        self.assertIn("normalize_name", result.clean_code)
        mixed = module.validate_python_source("설명\n```python\nx=1\n```")
        self.assertFalse(mixed.ok)

    def test_static_security_blocks_dynamic_and_network_code(self):
        for source in ("import subprocess\n", "eval('1+1')\n", "import requests\n", "import os\n"):
            with self.subTest(source=source):
                self.assertFalse(module.validate_python_source(source).ok)
        self.assertTrue(module.validate_python_source("import json\ndata=[]\ndata.remove(1)\njson.loads('{}')\n").ok)

    def test_test_quality_requires_test_and_assertion(self):
        self.assertFalse(module.validate_python_source("x=1\n", require_tests=True).ok)
        self.assertTrue(module.validate_python_source(GOOD_TRUSTED_TEST, require_tests=True).ok)

    def test_strict_payload_rejects_extra_and_duplicate_keys(self):
        raw = json.dumps({**candidate(), "extra": 1})
        with self.assertRaises(module.CodeImproverError):
            module.parse_candidate_payload(raw)
        duplicate = '{"code":"x=1","code":"x=2","test_code":"assert True","change_summary":"x","risk_level":"low","dependencies":[]}'
        with self.assertRaises(module.CodeImproverError):
            module.parse_candidate_payload(duplicate)
        with self.assertRaises(module.CodeImproverError):
            module.parse_candidate_payload(json.dumps(candidate() | {"dependencies": ["requests"]}))

    def test_docker_command_has_required_isolation_and_no_install(self):
        command = module.DockerSandbox().build_command("/tmp/work", "safe-name")
        joined = " ".join(command)
        for token in ("--network none", "--read-only", "--cap-drop ALL", "no-new-privileges:true",
                      "--pids-limit 64", "--memory 256m", "--user 65534:65534", "readonly"):
            self.assertIn(token, joined)
        self.assertNotIn("pip install", joined)
        self.assertNotIn("bash -c", joined)

    def test_no_sandbox_stops_before_api_call(self):
        client = FakeClient([candidate()])
        with tempfile.TemporaryDirectory() as temp:
            store = module.CodeLearningStore(Path(temp) / "learning.json")
            result = module.SecureAICodeImprover(
                client=client, sandbox=FakeSandbox(ready=False), learning_store=store,
                proposal_root=Path(temp) / "proposals",
            ).run("정규화", GOOD_TRUSTED_TEST)
        self.assertEqual(result["status"], "SANDBOX_UNAVAILABLE")
        self.assertEqual(client.responses.calls, [])

    def test_passed_candidate_saved_for_review_only(self):
        client = FakeClient([candidate()])
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            production = base / "production.py"
            production.write_text("SAFE=1\n", encoding="utf-8")
            before = production.read_bytes()
            store = module.CodeLearningStore(base / "learning.json")
            result = module.SecureAICodeImprover(
                client=client, sandbox=FakeSandbox(), learning_store=store,
                proposal_root=base / "proposals",
            ).run("정규화", GOOD_TRUSTED_TEST)
            manifest = json.loads((Path(result["proposal_path"]) / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(production.read_bytes(), before)
            self.assertFalse(result["production_files_modified"])
            self.assertEqual(manifest["status"], "READY_FOR_HUMAN_REVIEW")
            self.assertFalse(manifest["security"]["automatic_application"])
            self.assertEqual(store.load()["successful_proposals"], 1)

    def test_retry_feedback_and_failure_deduplication(self):
        bad = candidate(code="def broken(:\n")
        client = FakeClient([bad, bad, candidate()])
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            store = module.CodeLearningStore(base / "learning.json")
            result = module.SecureAICodeImprover(
                client=client, sandbox=FakeSandbox(), learning_store=store,
                proposal_root=base / "proposals",
            ).run("정규화", GOOD_TRUSTED_TEST, max_retries=5)
            memory = store.load()
        self.assertEqual(result["status"], "FAILED")
        self.assertTrue(result["stopped_duplicate_failure"])
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(len(memory["failure_groups"]), 1)
        self.assertEqual(next(iter(memory["failure_groups"].values()))["occurrences"], 2)
        self.assertEqual(len(client.responses.calls), 2)
        self.assertIn("이전 후보 검증 결과", client.responses.calls[1]["input"][1]["content"])

    def test_responses_api_and_structured_schema_used(self):
        client = FakeClient([candidate()])
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            improver = module.SecureAICodeImprover(
                client=client, sandbox=FakeSandbox(),
                learning_store=module.CodeLearningStore(base / "learning.json"),
                proposal_root=base / "proposals",
            )
            improver.run("정규화", GOOD_TRUSTED_TEST)
        call = client.responses.calls[0]
        self.assertEqual(call["model"], "gpt-4o")
        self.assertTrue(call["text"]["format"]["strict"])
        self.assertEqual(call["text"]["format"]["type"], "json_schema")

    def test_secret_redaction_and_retry_cap(self):
        self.assertNotIn("secret", module._redact("api_key=secret"))
        payloads = [RuntimeError(name) for name in ("alpha", "bravo", "charlie", "delta", "echo", "foxtrot")]
        client = FakeClient(payloads)
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            result = module.SecureAICodeImprover(
                client=client, sandbox=FakeSandbox(),
                learning_store=module.CodeLearningStore(base / "learning.json"),
                proposal_root=base / "proposals",
            ).run("정규화", GOOD_TRUSTED_TEST, max_retries=999)
        self.assertEqual(result["attempts"], 5)

    def test_learning_store_concurrent_updates_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            store = module.CodeLearningStore(Path(temp) / "learning.json")
            def write(index):
                store.record(phase="fixture", ok=False, detail=f"failure {index % 2}",
                             resolution="검토", attempt=1)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write, range(24)))
            memory = store.load()
        self.assertEqual(memory["total_attempts"], 24)
        self.assertEqual(sum(row["occurrences"] for row in memory["failure_groups"].values()), 24)

    def test_corrupt_learning_file_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "learning.json"
            path.write_text("{broken", encoding="utf-8")
            store = module.CodeLearningStore(path)
            with self.assertRaises(module.CodeImproverError):
                store.record(phase="fixture", ok=False, detail="failure", resolution="stop", attempt=1)
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ImproverTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"ok": result.wasSuccessful(), "tests": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors)}, ensure_ascii=False))
    raise SystemExit(0 if result.wasSuccessful() else 1)
