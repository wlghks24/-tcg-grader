#!/usr/bin/env python3
"""V562: execute the actual embedded retry gate with synthetic, offline files."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/gpt-tcg-drive-package.yml"


def embedded_gate() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    body = text.split("transient_degraded_only() {", 1)[1].split(
        "print_failure_diagnostics() {", 1
    )[0]
    return textwrap.dedent(body.split("python - <<'PY'", 1)[1].split("          PY", 1)[0])


class TransientProviderRetryV562(unittest.TestCase):
    @staticmethod
    def scenario(*, provider_errors=("TimeoutError: The read operation timed out",
                                     "HTTPError: status 502"),
                 sample_count=None, sample_failure="SOURCE_TRANSIENT",
                 output_error=None, source_ok=False, extra_high=False,
                 missing_source=False, source_error_mismatch=False):
        source_names = ["cgc-pricing", "cgc-news"]
        samples = []
        sources = {}
        for i, key in enumerate(source_names):
            error = provider_errors[i]
            samples.append({"company": "CGC", "source": key,
                            "failure_class": sample_failure, "error": error})
            sources[key] = {"company": "CGC", "source_id": key,
                            "status": "ok" if source_ok else "degraded",
                            "verified_official_source": False,
                            "last_error": ("HTTPError: status 403" if source_error_mismatch else error)}
        if missing_source:
            samples.pop()
        provider = {
            "severity": "high",
            "code": "GRADING_COMPANY_NO_HEALTHY_SOURCE",
            "target": "grading_company_updates.json",
            "companies": ["CGC"],
            "degraded_samples_by_company": {"CGC": samples},
            "degraded_sample_counts_by_company": {
                "CGC": len(source_names) if sample_count is None else sample_count
            },
        }
        findings = [provider]
        results = []
        if output_error is not None:
            findings.append({
                "severity": "high", "code": "DEGRADED_COLLECTION_OUTPUT",
                "target": "releases.json",
            })
            results.append({"file": "releases.json", "ok": False,
                            "remaining_collection_errors": [output_error]})
        if extra_high:
            findings.append({"severity": "high", "code": "INVALID_OUTPUT",
                             "target": "promo_events.json"})
        return {"findings": findings}, {"results": results}, {"sources": sources}

    def run_gate(self, *, scenario=None, omit_file=None):
        verification, update, grading = scenario or self.scenario()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for path, value in (
                ("COLLECTION_VERIFICATION_REPORT.json", verification),
                ("auto_update_report.json", update),
                ("grading_company_updates.json", grading),
            ):
                if path != omit_file:
                    (root / path).write_text(json.dumps(value), encoding="utf-8")
            # The exact job allowlist comes from the actual collector only in
            # production. This offline test mocks only the job list.
            (root / "auto_update_all.py").write_text(
                "JOBS = [(None, None, 'releases.json')]\n", encoding="utf-8"
            )
            return subprocess.run(
                [sys.executable, "-c", embedded_gate()],
                cwd=root, capture_output=True, text=True, timeout=8,
            )

    def test_all_sources_confirmed_transient_allows_one_retry_not_publication(self):
        proc = self.run_gate()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('"transient_provider_companies": ["CGC"]', proc.stdout)
        self.assertIn("steps.package.outputs.ready == 'true'",
                      WORKFLOW.read_text(encoding="utf-8"))

    def test_provider_plus_transient_collection_output_is_retryable(self):
        proc = self.run_gate(scenario=self.scenario(
            output_error="URLError: Connection reset by peer"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn('"file": "releases.json"', proc.stdout)

    def test_blocked_permanent_or_structural_failures_are_not_retried(self):
        scenarios = (
            self.scenario(provider_errors=("HTTPError: status 403", "HTTPError: status 502")),
            self.scenario(provider_errors=("HTTPError: status 410", "HTTPError: status 502")),
            self.scenario(provider_errors=("HTTPError: status 429", "HTTPError: status 502")),
            self.scenario(provider_errors=("ValueError: schema malformed", "HTTPError: status 502")),
            self.scenario(provider_errors=("TimeoutError: read timed out", "HTTPError: status 502"),
                          output_error="HTTPError: status 410"),
            self.scenario(extra_high=True),
            self.scenario(sample_failure="unclassified"),
            self.scenario(missing_source=True),
            self.scenario(sample_count=1),
            self.scenario(source_ok=True),
            self.scenario(source_error_mismatch=True),
        )
        for case in scenarios:
            with self.subTest(case=case):
                proc = self.run_gate(scenario=case)
                self.assertNotEqual(proc.returncode, 0, proc.stdout)

    def test_missing_same_cycle_source_snapshot_is_fail_closed(self):
        proc = self.run_gate(omit_file="grading_company_updates.json")
        self.assertNotEqual(proc.returncode, 0)

    def test_existing_workflow_keeps_publish_gate_and_bounded_cycle(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("if not high or len(high) > 4", workflow)
        self.assertIn("GRADING_COMPANY_NO_HEALTHY_SOURCE", workflow)
        self.assertIn("degraded_samples_by_company", workflow)
        self.assertIn("FRESH_LOCAL_COLLECTION_PLUS_TRANSIENT_RETRY", workflow)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-transient-recovery')", workflow)
        self.assertIn("steps.package.outputs.ready == 'true'", workflow)
        self.assertIn("python tablet_gdrive_publish.py --output-dir .tcg_drive_outbox", workflow)


if __name__ == "__main__":
    unittest.main()
