"""Static security regression for trusted-main GPT -> Drive artifact handoff."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
YAML = ROOT / ".github/workflows/tcg-verified-gpt-drive-handoff.yml"


class TrustedPackageHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = YAML.read_text(encoding="utf-8")

    def test_only_successful_same_repo_main_producer_triggers(self):
        for required in (
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.head_repository.full_name == github.repository",
            "github.event.workflow_run.event != 'pull_request'",
        ):
            self.assertIn(required, self.text)

    def test_untrusted_or_missing_secret_fails_closed(self):
        self.assertIn("secrets.TCG_RCLONE_CONFIG_B64", self.text)
        self.assertIn("HOLD_MISSING_DRIVE_SECRET", self.text)
        self.assertIn("steps.credential.outputs.state == 'READY'", self.text)
        self.assertNotIn("permissions:\n  contents: write", self.text)

    def test_missing_secret_is_reported_as_failure_not_false_green(self):
        # The operator must not mistake an Actions success for a Drive upload.
        body = self.text.split("Check Drive credentials before any transfer", 1)[1]
        hold = body.split("      - uses: actions/checkout@", 1)[0]
        self.assertIn("HOLD_MISSING_DRIVE_SECRET", hold)
        self.assertIn("::error::HOLD_MISSING_DRIVE_SECRET", hold)
        self.assertIn("exit 1", hold)
        self.assertNotIn("exit 0", hold)

    def test_exact_artifact_from_producer_run(self):
        self.assertIn('gh run download "$SOURCE_RUN_ID"', self.text)
        self.assertIn('--name tcg-gdrive-package', self.text)
        self.assertIn('ref: ${{ github.event.workflow_run.head_sha }}', self.text)
        self.assertIn('"$(git rev-parse FETCH_HEAD)" = "$EXPECTED_MAIN_SHA"', self.text)

    def test_exact_file_schema_and_hashes(self):
        for required in (
            "len(manifests) != 1 or len(bundles) != 1",
            'm.get("main_sha") != os.environ["EXPECTED_MAIN_SHA"]',
            'len(m["files"]) != len(sync.OUTPUTS)',
            'sync.sha256(dst / f["name"]) != f["sha256"]',
            "sync.extract_bundle(bundles[0], dst, m)",
        ):
            self.assertIn(required, self.text)

    def test_readback_verification_and_receipt_not_assumed(self):
        self.assertIn("pub.upload_package(bundle, mpath, m)", self.text)
        self.assertIn("DRIVE_READBACK_VERIFIED", self.text)
        self.assertIn("Tablet apply receipt: not confirmed here", self.text)

    def test_secret_not_in_artifacts(self):
        self.assertIn("chmod 600", self.text)
        self.assertIn('rm -rf -- "$RUNNER_TEMP/tcg-rclone"', self.text)
        self.assertIn("RCLONE_CONFIG=$config", self.text)


if __name__ == "__main__":
    unittest.main()
