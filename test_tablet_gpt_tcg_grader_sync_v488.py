#!/usr/bin/env python3
"""V488: exact reviewed package retry, preserving historical sync boundaries."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import unittest

from sync_v376_successor_test_support import (
    V488_PACKAGE_BASE, V488_PACKAGE_CANDIDATE,
    V488_PACKAGE_PATH, V488_PACKAGE_SHA256,
)

ROOT = Path(__file__).resolve().parent


class PackageSnapshotSuccessorV488(unittest.TestCase):
    def test_exact_reviewed_implementation_and_historical_boundary(self):
        for sha in (V488_PACKAGE_BASE, V488_PACKAGE_CANDIDATE):
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                cwd=ROOT, check=True, timeout=15,
            )
        touched = set(subprocess.check_output(
            ["git", "diff", "--name-only",
             V488_PACKAGE_BASE + ".." + V488_PACKAGE_CANDIDATE],
            cwd=ROOT, text=True, timeout=15,
        ).splitlines())
        self.assertEqual({
            V488_PACKAGE_PATH,
            "test_gpt_tcg_drive_package_recovery.py",
            "integrity_manifest.json",
        }, touched)
        raw = (ROOT / V488_PACKAGE_PATH).read_bytes()
        self.assertEqual(V488_PACKAGE_SHA256, hashlib.sha256(raw).hexdigest())

    def test_recovery_cannot_promote_invalid_or_partially_collected_snapshots(self):
        workflow = (ROOT / V488_PACKAGE_PATH).read_text(encoding="utf-8")
        gate = (ROOT / "static_data_publish_gate.py").read_text(encoding="utf-8")
        for term in (
            "critical and critical <= recoverable",
            "TOPIC_EXPECTED_CELL_MISMATCH",
            "SOCIAL_TOPIC_ATTEMPT_CONTRACT_MISMATCH",
            "stale_with_drift",
            "tcg_updater.update_cycle('gpt-drive-package-refresh')",
            'if: steps.package.outputs.ready == \'true\'',
        ):
            self.assertIn(term, workflow)
        for token in (
            "EXPECTED_TOPIC_CELLS = len(update_promo_events.social_topic_expected_keys())",
            "TOPIC_COLLECTION_NOT_FULLY_ATTEMPTED",
            "SOCIAL_TOPIC_ATTEMPT_CONTRACT_MISMATCH",
            "STALE_SUPPLEMENTARY_SNAPSHOT",
        ):
            self.assertIn(token, gate)


if __name__ == "__main__":
    unittest.main()
