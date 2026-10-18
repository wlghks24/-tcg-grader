#!/usr/bin/env python3
"""Structural regression: Drive publish can never bypass a verified package."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VerifiedDrivePublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/gpt-tcg-drive-package.yml").read_text(encoding="utf-8")
        cls.publisher = (ROOT / "tablet_gdrive_publish.py").read_text(encoding="utf-8")

    def test_publish_never_runs_on_pr_or_failed_package(self):
        self.assertIn("if: steps.package.outputs.ready == 'true' && github.ref == 'refs/heads/main'", self.workflow)
        self.assertIn("TCG_RCLONE_CONFIG_B64: ${{ secrets.TCG_RCLONE_CONFIG_B64 }}", self.workflow)
        self.assertIn("HOLD_MISSING_DRIVE_CREDENTIAL", self.workflow)
        self.assertNotIn("echo \"$TCG_RCLONE_CONFIG_B64\"", self.workflow)

    def test_verifies_single_manifest_and_hashes_before_remote(self):
        for phrase in ("len(manifests) != 1 or len(bundles) != 1", "sync.load_manifest(manifests[0])",
                       'sync.extract_bundle(bundles[0], stage, manifest)',
                       'sync.sha256(stage / record["name"])', "publish.upload_package("):
            self.assertIn(phrase, self.workflow)

    def test_remote_commit_marker_written_last_and_read_back(self):
        pub = self.publisher
        self.assertLess(pub.index("_upload_one(remote, bundle, remote_root)"),
                        pub.index("_upload_one(remote, manifest_path, remote_root)"))
        for phrase in ("read_bundle.stat().st_size", "sync.sha256(read_bundle)",
                       "sync.extract_bundle(read_bundle, stage, loaded)", '"--immutable"'):
            self.assertIn(phrase, pub)

    def test_workflow_reports_delivery_status_not_artifact_presence(self):
        self.assertIn("Drive delivery: ${{ steps.drive.outputs.state || 'NOT_RUN' }}", self.workflow)
        self.assertIn('state=DRIVE_READBACK_VERIFIED', self.workflow)
        self.assertIn('HOLD_MISSING_DRIVE_CREDENTIAL', self.workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
