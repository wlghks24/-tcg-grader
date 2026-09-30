import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WORKFLOW = ROOT / '.github/workflows/gpt-tcg-drive-package.yml'


class GptDrivePackageStaleRecoveryV364Tests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding='utf-8')

    def test_dual_freshness_staleness_dispatches_refresh_without_upload(self):
        self.assertIn('"STALE_SOCIAL_SNAPSHOT", "STALE_AUTO_UPDATE_REPORT"', self.text)
        self.assertIn('critical and critical <= freshness', self.text)
        self.assertIn('FRESH_STATIC_REFRESH_DISPATCHED', self.text)
        self.assertIn('tcg-static-data-refresh.yml/dispatches', self.text)
        self.assertIn('echo "ready=false"', self.text)
        self.assertIn("if: steps.package.outputs.ready == 'true'", self.text)

    def test_recovery_does_not_widen_or_ignore_nonfreshness_critical_findings(self):
        self.assertIn('exit "${rc}"', self.text)
        self.assertIn('freshness = {"STALE_SOCIAL_SNAPSHOT", "STALE_AUTO_UPDATE_REPORT"}', self.text)
        self.assertNotIn('critical <= freshness or', self.text)
        self.assertIn('never widen report/social freshness gates', self.text)

    def test_empty_critical_set_is_not_treated_as_stale_only(self):
        self.assertIn('critical and critical <= freshness', self.text)


if __name__ == '__main__':
    unittest.main()
