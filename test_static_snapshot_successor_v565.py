#!/usr/bin/env python3
"""V565: preserve the frozen V545 tree while reviewing one explicit data successor."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import sync_v376_successor_test_support as scope


class ReviewedStaticSnapshotV565(unittest.TestCase):
    def tearDown(self):
        scope._v545_verified_static_snapshot_paths.cache_clear()

    def test_original_seventeen_blobs_are_still_pinned_in_git(self):
        names = sorted(scope.V545_STATIC_BLOBS)
        old = subprocess.check_output(
            ["git", "rev-parse", *(
                f"{scope.V545_STATIC_CANDIDATE}:{name}" for name in names
            )], cwd=scope.ROOT, text=True,
        ).splitlines()
        self.assertEqual(old, [scope.V545_STATIC_BLOBS[p] for p in names])
        self.assertEqual(len(old), 17)

    def test_exact_new_snapshot_is_readonly_audited_successor(self):
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", scope.V565_GRADING_CANDIDATE, "HEAD"],
            cwd=scope.ROOT, check=True,
        )
        self.assertEqual(scope._v545_verified_static_snapshot_paths(),
                         frozenset(scope.V545_STATIC_BLOBS))
        new_file = scope.ROOT / scope.V565_GRADING_PATH
        raw = new_file.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), scope.V565_GRADING_SHA256)
        manifest = json.loads((scope.ROOT / "integrity_manifest.json").read_text())
        self.assertEqual(manifest["files"][scope.V565_GRADING_PATH]["sha256"],
                         scope.V565_GRADING_SHA256)
        self.assertEqual(manifest["files"][scope.V565_GRADING_PATH]["bytes"], len(raw))
        self.assertEqual(
            subprocess.check_output(
                ["git", "diff", "--name-only",
                 f"{scope.V565_GRADING_BASE}..{scope.V565_GRADING_CANDIDATE}"],
                cwd=scope.ROOT, text=True,
            ).splitlines(),
            ["grading_company_updates.json", "integrity_manifest.json"],
        )

    def test_unapproved_future_byte_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            temp_root = Path(folder)
            for name in scope.V545_STATIC_BLOBS:
                shutil.copy2(scope.ROOT / name, temp_root / name)
            actual_run = subprocess.run
            def ancestry_in_historical_fixture(command, *args, **kwargs):
                # Synthetic filesystem has no git history; mock ancestry only.
                # Real git hash-object must still inspect the tampered bytes.
                if command[:3] == ["git", "merge-base", "--is-ancestor"]:
                    return mock.Mock(returncode=0)
                return actual_run(command, *args, **kwargs)
            with mock.patch.object(scope, "ROOT", temp_root), \
                 mock.patch.object(scope.subprocess, "run",
                                   side_effect=ancestry_in_historical_fixture):
                # Non-grading sibling corruption blocks the *entire* generation.
                (temp_root / "market_prices.json").write_text("{}", encoding="utf-8")
                scope._v545_verified_static_snapshot_paths.cache_clear()
                self.assertEqual(scope._v545_verified_static_snapshot_paths(), frozenset())
                shutil.copy2(scope.ROOT / "market_prices.json", temp_root / "market_prices.json")
                # Even a valid JSON change to grading itself is never silently allowed.
                (temp_root / scope.V565_GRADING_PATH).write_text("{}", encoding="utf-8")
                scope._v545_verified_static_snapshot_paths.cache_clear()
                self.assertEqual(scope._v545_verified_static_snapshot_paths(), frozenset())

    def test_old_head_never_inherits_reviewed_latest_data(self):
        changed = [scope.V565_GRADING_PATH]
        self.assertEqual(
            scope.preserve_reviewed_v545_static_scope(
                changed, scope.V545_STATIC_BASE, head=scope.V545_STATIC_CANDIDATE
            ),
            changed,
        )
        with mock.patch.object(scope.subprocess, "run",
                               return_value=mock.Mock(returncode=1)):
            scope._v545_verified_static_snapshot_paths.cache_clear()
            self.assertEqual(scope._v545_verified_static_snapshot_paths(), frozenset())


if __name__ == "__main__":
    unittest.main()
