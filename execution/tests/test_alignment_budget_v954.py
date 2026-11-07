"""Offline, fail-closed V954 CI budget successor; no source writes or device claims."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import sync_v376_successor_test_support as sync


class AlignmentBudgetV954Tests(unittest.TestCase):
    def test_exact_budget_successor_preserves_shards_and_historical_proof(self):
        sync.assert_v954_alignment_budget_successor(self)
        sync.assert_v659_ci_successor(self)
        sync.assert_v647_ci_successor(self)

    def test_immutable_v659_blob_remains_beside_bounded_v954_live_workflow(self):
        path = sync.V954_ALIGNMENT_PROOF['watched_path']
        original = subprocess.check_output([
            'git', 'show',
            f"{sync.V659_CI_PROOF['candidate_commit']}:{path}",
        ], cwd=sync.ROOT)
        historical = hashlib.sha256(original).hexdigest()
        live = hashlib.sha256((sync.ROOT / path).read_bytes()).hexdigest()
        self.assertEqual(
            historical, sync.V659_CI_PROOF['reviewed_sha256'][path])
        self.assertEqual(
            live, sync.V954_ALIGNMENT_PROOF['reviewed_sha256'])
        self.assertNotEqual(historical, live)

    def test_unknown_live_bytes_and_forged_proof_fail_closed(self):
        sync.assert_v954_alignment_budget_successor(self)
        path = sync.ROOT / sync.V954_ALIGNMENT_PROOF['watched_path']
        original = Path.read_bytes
        with patch.object(
            Path, 'read_bytes',
            lambda target: (
                original(target) + b'\\n# unreviewed safety bypass'
                if target == path else original(target)
            ),
        ):
            with self.assertRaises(AssertionError):
                sync.assert_v954_alignment_budget_successor(self)
            with self.assertRaises(AssertionError):
                sync.assert_v659_ci_successor(self)
        with patch.dict(
            sync.V954_ALIGNMENT_PROOF,
            {'candidate_commit': '0' * 40},
        ):
            with self.assertRaises(AssertionError):
                sync.assert_v954_alignment_budget_successor(self)


if __name__ == '__main__':
    unittest.main()
