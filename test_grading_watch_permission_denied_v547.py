#!/usr/bin/env python3
"""V547: a failed grading-provider PR creation must not be reported as a successful publish."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/grading-company-watch.yml"


def denial_branch(yaml: str) -> str:
    marker = '            if ! pr_json="$(gh api --method POST'
    start = yaml.index(marker)
    end = yaml.index("\n            fi", start) + len("\n            fi")
    return yaml[start:end]


class GradingWatchDeniedV547Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_denied_publish_is_not_green(self):
        branch = denial_branch(self.workflow)
        self.assertIn("status=PENDING_EXTERNAL_PR", branch)
        self.assertIn("NOT published to main", branch)
        self.assertIn("::error::", branch)
        self.assertIn("exit 1", branch)
        self.assertNotIn("exit 0", branch)
        self.assertIn("echo 'status=MERGED'", self.workflow)
        self.assertIn("git push origin --delete", self.workflow)
        self.assertNotIn("git push origin HEAD:main", self.workflow)
        self.assertIn("if: always()", self.workflow.split("- name: Write watcher summary", 1)[1])
        self.assertIn("if: always()", self.workflow.split("- name: Upload provider RCA diagnostics", 1)[1])

    def test_live_denied_shell_exit_and_evidence(self):
        if not Path("/bin/bash").exists():
            self.skipTest("bash unavailable")
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "GITHUB_OUTPUT"
            err = Path(temp) / "pr-error"
            script = (
                'set -euo pipefail\n'
                'gh() { printf "GitHub Actions is not permitted to create or approve pull requests. (HTTP 403)\\n" >&2; return 1; }\n'
                'pr_number=; title=candidate; body=proof; REPO=example/repo; CANDIDATE_BRANCH=auto/grading-watch;\n'
                + denial_branch(self.workflow).replace("/tmp/create-pr.err", str(err))
                + "\n"
            )
            proc = subprocess.run(
                ["/bin/bash", "-c", script],
                cwd=ROOT, env={"GITHUB_OUTPUT": str(out), "PATH": os.environ.get("PATH", "/usr/bin:/bin")},
                text=True, capture_output=True, timeout=10, check=False,
            )
            self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
            evidence = out.read_text(encoding="utf-8")
            self.assertIn("status=PENDING_EXTERNAL_PR", evidence)
            self.assertIn("NOT published to main", evidence)
            self.assertIn("HTTP 403", proc.stderr)
            self.assertIn("::error::", proc.stdout + proc.stderr)

    def test_fail_closed_merge_controls_unchanged(self):
        for expected in (
            'merge_method=merge -f sha="${CANDIDATE_SHA}"',
            "status=REQUIRED_CHECK_FAILED", "status=REQUIRED_CHECK_TIMEOUT",
            "status=BASE_ADVANCED", "status=MERGE_REJECTED",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected.replace("\\$", "$"), self.workflow)


if __name__ == "__main__":
    unittest.main()
