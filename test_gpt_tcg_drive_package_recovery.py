from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/gpt-tcg-drive-package.yml"


class GptTcgDrivePackageRecoveryTests(unittest.TestCase):
    def test_freshness_only_recovery_covers_all_known_stale_sources_without_weakening_gate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for code in (
            "STALE_AUTO_UPDATE_REPORT",
            "STALE_SOCIAL_SNAPSHOT",
            "STALE_SUPPLEMENTARY_SNAPSHOT",
        ):
            self.assertIn(code, workflow)
        self.assertIn("critical and critical <= recoverable", workflow)
        self.assertIn("tcg_updater.update_cycle('gpt-drive-package-refresh')", workflow)
        self.assertIn("python tablet_gdrive_publish.py --output-dir .tcg_drive_outbox", workflow)
        self.assertIn('if [ "${retry_rc}" -ne 0 ]', workflow)
        self.assertIn('echo "ready=true"', workflow)
        self.assertIn("FRESH_LOCAL_COLLECTION_RETRY", workflow)
        self.assertIn("for recovery_attempt in 1 2", workflow)
        self.assertIn("after 2 bounded attempts", workflow)
        self.assertIn('"findings": [', workflow)
        self.assertIn("--fail-on-degraded", workflow)
        self.assertIn("steps.package.outputs.ready == 'true'", workflow)
        self.assertIn("never widen freshness gates", workflow)
        self.assertIn("Stale inputs are never uploaded", workflow)
        self.assertNotIn("publish_allowed = true", workflow)
        self.assertNotIn("actions: write", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
