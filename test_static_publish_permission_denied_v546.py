#!/usr/bin/env python3
"""V546: a validated candidate must not look published when Actions PR creation fails."""
from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/tcg-static-data-refresh.yml"


class StaticPublishDeniedV546Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.yaml = WORKFLOW.read_text(encoding="utf-8")

    def test_unpublished_candidate_is_a_hard_workflow_failure(self):
        start = self.yaml.index('            if ! pr_json="$(gh api --method POST')
        end = self.yaml.index('\n            fi', start) + len('\n            fi')
        block = self.yaml[start:end]
        self.assertIn("status=PENDING_EXTERNAL_PR", block)
        self.assertIn("validated data NOT published to main", block)
        self.assertIn('exit 1', block)
        self.assertNotIn('exit 0', block)
        self.assertIn('::error::', block)
        self.assertNotIn('git push origin HEAD:main', self.yaml)
        self.assertIn('if: always()', self.yaml.split('      - name: Upload publish evidence', 1)[1])
        self.assertIn('if: always()', self.yaml.split('      - name: Write refresh summary', 1)[1])

    def test_mock_403_cannot_exit_success(self):
        if not Path('/bin/bash').exists():
            self.skipTest('bash required for workflow simulation')
        marker = '            if ! pr_json="$(gh api --method POST'
        start = self.yaml.index(marker)
        end = self.yaml.index('\n            fi', start) + len('\n            fi')
        with tempfile.TemporaryDirectory() as tmp:
            evidence = Path(tmp) / 'outputs'
            error = Path(tmp) / 'create-pr.err'
            block = self.yaml[start:end].replace('/tmp/create-pr.err', str(error))
            script = (
                'set -euo pipefail\n'
                'gh() { printf "GitHub Actions is not permitted to create or approve pull requests. (HTTP 403)\\n" >&2; return 1; }\n'
                'pr_number=; title=candidate; body=evidence; REPO=owner/repo; CANDIDATE_BRANCH=auto/validated;\n'
                + block + '\n'
            )
            result = subprocess.run(
                ['bash', '-c', script],
                cwd=ROOT, text=True, capture_output=True,
                env={'GITHUB_OUTPUT': str(evidence), 'PATH': '/usr/bin:/bin'},
                check=False, timeout=8,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('status=PENDING_EXTERNAL_PR', evidence.read_text(encoding='utf-8'))
            self.assertIn('NOT published', result.stdout + result.stderr)
            self.assertIn('HTTP 403', result.stderr)

    def test_no_change_or_already_merged_paths_stay_distinct(self):
        self.assertIn('reason=no validated data or integrity changes', self.yaml)
        self.assertIn("echo 'status=MERGED'", self.yaml)
        self.assertIn("echo 'status=BASE_ADVANCED'", self.yaml)
        self.assertIn('auto/static-data-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}', self.yaml)


if __name__ == '__main__':
    unittest.main()
