#!/usr/bin/env python3
"""V547: reviewed grading-watch update must preserve immutable historical sync scopes."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as helper

ROOT = Path(__file__).resolve().parent


class GradingWatchSuccessorV547Tests(unittest.TestCase):
    def test_pinned_workflow_blob_and_ancestor(self):
        self.assertEqual(
            "1fdc7327d358ed6644d2d57a0b94ae29be717433",
            helper.V547_GRADING_BLOB,
        )
        sha = subprocess.check_output(
            ["git", "hash-object", "--", helper.V547_GRADING_WORKFLOW],
            cwd=ROOT, text=True,
        ).strip()
        self.assertEqual(sha, helper.V547_GRADING_BLOB)
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", helper.V547_GRADING_CANDIDATE, "HEAD"],
            cwd=ROOT, check=True,
        )

    def test_clears_only_newly_reviewed_grading_workflow(self):
        path = helper.V547_GRADING_WORKFLOW
        self.assertEqual(
            [], helper.preserve_reviewed_v547_grading_scope([path], helper.V547_GRADING_BASE)
        )
        self.assertEqual(
            [path], helper.preserve_reviewed_v547_grading_scope(
                [path], helper.V547_GRADING_BASE, head=helper.V547_GRADING_CANDIDATE,
            ),
        )
        self.assertEqual(
            ["unrelated.py"], helper.preserve_reviewed_v547_grading_scope(
                ["unrelated.py"], helper.V547_GRADING_BASE,
            ),
        )

    def test_keeps_preexisting_historical_diffs(self):
        previous_sha = subprocess.check_output(
            ["git", "rev-parse", f"{helper.V547_GRADING_BASE}^"],
            cwd=ROOT, text=True,
        ).strip()
        previous = subprocess.check_output(
            ["git", "diff", "--name-only",
             f"{previous_sha}..{helper.V547_GRADING_BASE}", "--",
             helper.V547_GRADING_WORKFLOW],
            cwd=ROOT, text=True,
        ).splitlines()
        expected = [helper.V547_GRADING_WORKFLOW] if previous else []
        self.assertEqual(
            expected, helper.preserve_reviewed_v547_grading_scope(
                [helper.V547_GRADING_WORKFLOW], previous_sha
            ),
        )

    def test_tamper_or_unverified_commit_is_not_allowed(self):
        path = helper.V547_GRADING_WORKFLOW
        with patch.object(helper, "V547_GRADING_BLOB", "0" * 40):
            self.assertEqual(
                [path], helper.preserve_reviewed_v547_grading_scope([path], helper.V547_GRADING_BASE)
            )
        with patch.object(helper, "V547_GRADING_CANDIDATE", "0" * 40):
            self.assertEqual(
                [path], helper.preserve_reviewed_v547_grading_scope([path], helper.V547_GRADING_BASE)
            )


if __name__ == "__main__":
    unittest.main()
