#!/usr/bin/env python3
"""V547: grading-provider verified data cannot be reported as published after GitHub 403."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as successor

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/grading-company-watch.yml"


class GradingWatchPermissionDeniedV547Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml = WORKFLOW.read_text(encoding="utf-8")

    def _create_pr_block(self):
        start = self.yaml.index('            if ! pr_json="$(gh api --method POST')
        end = self.yaml.index('\n            fi', start) + len('\n            fi')
        return self.yaml[start:end]

    def test_candidate_denial_fails_and_retains_evidence(self):
        block = self._create_pr_block()
        self.assertIn("status=PENDING_EXTERNAL_PR", block)
        self.assertIn('exit 1', block)
        self.assertNotIn('exit 0', block)
        self.assertIn("NOT published to main", block)
        self.assertIn("::error::", block)
        self.assertIn("if: always()", self.yaml)
        self.assertNotIn("git push origin HEAD:main", self.yaml)

    def test_denied_pr_mock_is_not_a_successful_run(self):
        if not Path('/bin/bash').exists():
            self.skipTest('bash required')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "github-output"
            err = Path(tmp) / "create-pr.err"
            snippet = self._create_pr_block().replace("/tmp/create-pr.err", str(err))
            mock = (
                'set -euo pipefail\n'
                'gh() { echo "GitHub Actions PR creation blocked (HTTP 403)" >&2; return 1; }\n'
                'title=test; body=test; REPO=owner/repo; CANDIDATE_BRANCH=validated;\n'
                + snippet + '\n'
            )
            result = subprocess.run(
                ["bash", "-c", mock],
                cwd=ROOT, env={"PATH": "/usr/bin:/bin", "GITHUB_OUTPUT": str(output)},
                text=True, capture_output=True, check=False, timeout=8,
            )
            self.assertEqual(1, result.returncode, result.stderr + result.stdout)
            self.assertIn("status=PENDING_EXTERNAL_PR", output.read_text(encoding="utf-8"))
            self.assertIn("NOT published", result.stderr + result.stdout)
            self.assertIn("HTTP 403", result.stderr)

    def test_exact_reviewed_workflow_does_not_hide_earlier_edits(self):
        name = successor.V547_GRADING_WORKFLOW
        blob = subprocess.check_output(
            ["git", "hash-object", "--", name], cwd=ROOT, text=True,
        ).strip()
        self.assertEqual(successor.V547_GRADING_BLOB, blob)
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", successor.V547_GRADING_CANDIDATE, "HEAD"],
            cwd=ROOT, check=True,
        )
        self.assertEqual(
            [], successor.preserve_reviewed_v547_grading_scope([name], successor.V547_GRADING_BASE),
        )
        self.assertEqual(
            [name], successor.preserve_reviewed_v547_grading_scope(
                [name], successor.V547_GRADING_BASE, head=successor.V547_GRADING_CANDIDATE,
            ),
        )
        before = subprocess.check_output(
            ["git", "diff", "--name-only",
             f"{successor.V546_PUBLISH_BASE}..{successor.V547_GRADING_BASE}", "--", name],
            cwd=ROOT, text=True,
        ).splitlines()
        got = successor.preserve_reviewed_v547_grading_scope([name], successor.V546_PUBLISH_BASE)
        self.assertEqual([name] if before else [], got)
        with patch.object(successor, "V547_GRADING_BLOB", "0" * 40):
            self.assertEqual(
                [name], successor.preserve_reviewed_v547_grading_scope([name], successor.V547_GRADING_BASE),
            )


if __name__ == "__main__":
    unittest.main()
