#!/usr/bin/env python3
"""V546: immutable, reviewed publish workflow successor preserves historical sync lineage."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as helpers

ROOT = Path(__file__).resolve().parent


class PublishWorkflowSuccessorV546Tests(unittest.TestCase):
    def test_exact_git_blob_and_ancestry(self):
        self.assertEqual(
            "55426f844548c41a8fb4e032ecbec0575bf39791",
            helpers.V546_PUBLISH_BLOB,
        )
        out = subprocess.check_output(
            ["git", "hash-object", "--", helpers.V546_PUBLISH_WORKFLOW],
            cwd=ROOT, text=True,
        ).strip()
        # V546's immutable blob must still be the original baseline, not
        # the newly reviewed V634 descendant on the working tree.
        baseline_blob = subprocess.check_output(
            ["git", "rev-parse", f"{helpers.V634_STATIC_BASE}:{helpers.V546_PUBLISH_WORKFLOW}"],
            cwd=ROOT, text=True,
        ).strip()
        self.assertEqual(helpers.V546_PUBLISH_BLOB, baseline_blob)
        committed_blob = subprocess.check_output(
            ["git", "rev-parse", f"HEAD:{helpers.V546_PUBLISH_WORKFLOW}"],
            cwd=ROOT, text=True,
        ).strip()
        self.assertEqual(committed_blob, out, "working tree differs from HEAD")
        self.assertNotEqual(baseline_blob, out)
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", helpers.V546_PUBLISH_CANDIDATE, "HEAD"],
            cwd=ROOT, check=True,
        )

    def test_only_changes_newer_than_reviewed_base_are_excluded(self):
        self.assertEqual(
            [helpers.V546_PUBLISH_WORKFLOW],
            helpers.preserve_reviewed_v546_publish_scope(
                [helpers.V546_PUBLISH_WORKFLOW], helpers.V546_PUBLISH_BASE,
            ),
        )
        # Only the V634 exact pinned successor may clear this later change;
        # legacy V546 alone must not conceal modified workflow bytes.
        self.assertEqual(
            [],
            helpers.preserve_reviewed_v525_grade_scope(
                [helpers.V546_PUBLISH_WORKFLOW], helpers.V546_PUBLISH_BASE,
            ),
        )
        self.assertEqual(
            ["unrelated_runtime.py"],
            helpers.preserve_reviewed_v546_publish_scope(
                ["unrelated_runtime.py"], helpers.V546_PUBLISH_BASE,
            ),
        )
        # A historical comparison to an explicit immutable commit cannot be hidden.
        self.assertEqual(
            [helpers.V546_PUBLISH_WORKFLOW],
            helpers.preserve_reviewed_v546_publish_scope(
                [helpers.V546_PUBLISH_WORKFLOW], helpers.V546_PUBLISH_BASE,
                head=helpers.V546_PUBLISH_CANDIDATE,
            ),
        )

    def test_preexisting_watched_changes_are_not_erased(self):
        before = subprocess.check_output(
            ["git", "diff", "--name-only",
             f"{helpers.V546_PUBLISH_CANDIDATE}^..{helpers.V546_PUBLISH_BASE}",
             "--", helpers.V546_PUBLISH_WORKFLOW],
            cwd=ROOT, text=True,
        ).splitlines()
        actual = helpers.preserve_reviewed_v546_publish_scope(
            [helpers.V546_PUBLISH_WORKFLOW],
            f"{helpers.V546_PUBLISH_CANDIDATE}^",
        )
        # The original V546 gate sees changed bytes and must fail closed.
        self.assertEqual([helpers.V546_PUBLISH_WORKFLOW], actual)
        # The V634 successor excludes only its pinned delta and still exposes
        # changes that predate the older reviewed V546 baseline.
        newer = helpers.preserve_reviewed_v634_static_scope(
            [helpers.V546_PUBLISH_WORKFLOW],
            f"{helpers.V546_PUBLISH_CANDIDATE}^",
        )
        self.assertEqual([helpers.V546_PUBLISH_WORKFLOW] if before else [], newer)

    def test_unknown_workflow_bytes_fail_closed(self):
        with patch.object(helpers, "V546_PUBLISH_BLOB", "0" * 40):
            self.assertEqual(
                [helpers.V546_PUBLISH_WORKFLOW],
                helpers.preserve_reviewed_v546_publish_scope(
                    [helpers.V546_PUBLISH_WORKFLOW], helpers.V546_PUBLISH_BASE,
                ),
            )


if __name__ == "__main__":
    unittest.main()
