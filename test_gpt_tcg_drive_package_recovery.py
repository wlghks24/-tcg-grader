from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / ".github/workflows/gpt-tcg-drive-package.yml"


class GptTcgDrivePackageRecoveryTests(unittest.TestCase):
    def test_freshness_only_recovery_covers_all_known_stale_sources_without_weakening_gate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            'recoverable = {"STALE_AUTO_UPDATE_REPORT", "STALE_SOCIAL_SNAPSHOT"}',
            workflow,
        )
        self.assertIn("critical and critical <= recoverable", workflow)
        self.assertIn("FRESH_STATIC_REFRESH_DISPATCHED", workflow)
        self.assertIn("tcg-static-data-refresh.yml/dispatches", workflow)
        self.assertIn('exit "${rc}"', workflow)
        self.assertIn("never widen the two-hour report freshness gate", workflow)
        self.assertNotIn("publish_allowed = true", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
