"""Scope filtering validates exact live evidence once, after eligibility is known."""
from __future__ import annotations

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import sync_v376_successor_test_support as sync
from execution.tests import test_deployment_repairs_successor_v1001 as proof

ROOT = Path(__file__).resolve().parents[2]
BASE = proof.EXPECTED["baseline_commit"]
CANDIDATE = proof.EXPECTED["candidate_commit"]
REVIEWED = sorted(proof.EXPECTED["reviewed_files"])
EARLIER_UI = "ce4def1b5f57fdf8729e5e7ec0a3582f524b2a4d"
OLDER_SOURCE = "742751dce03c711f7a4ca7a882d2fec69fb3ac55"


def earlier_paths(source):
    return subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-only", source, BASE,
         "--", *REVIEWED], cwd=ROOT, text=True, timeout=30,
    ).splitlines()


class ScopeValidationPerformanceV1002Tests(unittest.TestCase):
    def test_five_removable_paths_share_one_real_full_live_validation(self):
        real_validator = proof.validate_deployment_repairs_v1001
        real_read = Path.read_bytes
        live_reads = []

        def observed_read(path):
            if path in {ROOT / name for name in REVIEWED}:
                live_reads.append(path)
            return real_read(path)

        with patch.object(proof, "validate_deployment_repairs_v1001", wraps=real_validator) as checked, \
                patch.object(Path, "read_bytes", observed_read):
            self.assertEqual([], sync.preserve_reviewed_v1001_scope(REVIEWED, BASE))
        self.assertEqual(1, checked.call_count)
        self.assertCountEqual([ROOT / name for name in REVIEWED], live_reads)

    def test_mixed_scope_retains_earlier_changes_and_unknown_paths(self):
        self.assertEqual(["index.html"], earlier_paths(EARLIER_UI))
        visible = ["unknown.js", *REVIEWED]
        with patch.object(proof, "validate_deployment_repairs_v1001",
                          wraps=proof.validate_deployment_repairs_v1001) as checked:
            self.assertEqual(["unknown.js", "index.html"],
                             sync.preserve_reviewed_v1001_scope(visible, EARLIER_UI))
        self.assertEqual(1, checked.call_count)

    def test_no_removable_path_does_not_scan_current_proof_or_runtime(self):
        visible = earlier_paths(OLDER_SOURCE)
        self.assertTrue(visible)
        self.assertTrue(set(visible).issubset(REVIEWED))
        with patch.object(proof, "validate_deployment_repairs_v1001",
                          wraps=proof.validate_deployment_repairs_v1001) as checked:
            self.assertEqual(visible, sync.preserve_reviewed_v1001_scope(visible, OLDER_SOURCE))
        self.assertEqual(0, checked.call_count)

    def test_each_new_scope_request_revalidates_current_evidence(self):
        with patch.object(proof, "validate_deployment_repairs_v1001",
                          wraps=proof.validate_deployment_repairs_v1001) as checked:
            self.assertEqual([], sync.preserve_reviewed_v1001_scope(REVIEWED, BASE))
            self.assertEqual(1, checked.call_count)
            self.assertEqual([], sync.preserve_reviewed_v1001_scope(REVIEWED, BASE))
            self.assertEqual(2, checked.call_count)

    def test_warm_history_never_hides_any_changed_live_file(self):
        self.assertEqual([], sync.preserve_reviewed_v1001_scope(REVIEWED, BASE))
        real_read = Path.read_bytes
        real_validator = proof.validate_deployment_repairs_v1001
        for name in REVIEWED:
            target = ROOT / name

            def tampered(path):
                data = real_read(path)
                return data + b"unreviewed" if path == target else data

            with self.subTest(name=name), patch.object(Path, "read_bytes", tampered), \
                    patch.object(proof, "validate_deployment_repairs_v1001", wraps=real_validator) as checked:
                self.assertEqual(REVIEWED, sync.preserve_reviewed_v1001_scope(REVIEWED, BASE))
                self.assertEqual(1, checked.call_count)

    def test_warm_history_never_hides_changed_proof(self):
        self.assertEqual([], sync.preserve_reviewed_v1001_scope(REVIEWED, BASE))
        real_read = Path.read_text

        def tampered(path, *args, **kwargs):
            text = real_read(path, *args, **kwargs)
            return text.replace('"deployment_allowed": false', '"deployment_allowed": true') if path == proof.PROOF else text

        with patch.object(Path, "read_text", tampered), \
                patch.object(proof, "validate_deployment_repairs_v1001",
                             wraps=proof.validate_deployment_repairs_v1001) as checked:
            self.assertEqual(REVIEWED, sync.preserve_reviewed_v1001_scope(REVIEWED, BASE))
            self.assertEqual(1, checked.call_count)

    def test_unknown_paths_explicit_head_and_unverifiable_ancestry_stay_visible(self):
        # Unknown Git source is rejected by the real ancestry command. The
        # explicit-head case must not silently be answered for current HEAD.
        cases = [(["unknown.js"], BASE, "HEAD"), ([], BASE, "HEAD"),
                 (REVIEWED, BASE, CANDIDATE), (REVIEWED, "0" * 40, "HEAD")]
        for visible, source, head in cases:
            with self.subTest(source=source, head=head), \
                    patch.object(proof, "validate_deployment_repairs_v1001",
                                 wraps=proof.validate_deployment_repairs_v1001) as checked:
                self.assertEqual(visible, sync.preserve_reviewed_v1001_scope(visible, source, head))
                self.assertEqual(0, checked.call_count)

    def test_denied_divergent_ancestry_never_delegates_live_trust(self):
        source = "d" * 40
        real_run = sync._git_validation_run

        def ancestry_denied(args, **kwargs):
            if args == ["git", "merge-base", "--is-ancestor", source, CANDIDATE]:
                return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"")
            return real_run(args, **kwargs)

        with patch.object(sync, "_git_validation_run", side_effect=ancestry_denied), \
                patch.object(proof, "validate_deployment_repairs_v1001",
                             wraps=proof.validate_deployment_repairs_v1001) as checked:
            self.assertEqual(REVIEWED, sync.preserve_reviewed_v1001_scope(REVIEWED, source))
            self.assertEqual(0, checked.call_count)


if __name__ == "__main__":
    unittest.main()
