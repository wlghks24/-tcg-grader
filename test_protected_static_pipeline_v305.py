import unittest
from pathlib import Path


class ProtectedStaticPipelineV305Tests(unittest.TestCase):
    def setUp(self):
        self.refresh = Path('.github/workflows/tcg-static-data-refresh.yml').read_text(encoding='utf-8')
        self.package = Path('.github/workflows/gpt-tcg-drive-package.yml').read_text(encoding='utf-8')

    def test_static_refresh_never_direct_pushes_main(self):
        self.assertNotIn('git push origin HEAD:main', self.refresh)
        self.assertIn('auto/static-data-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}', self.refresh)
        self.assertIn('pull-requests: write', self.refresh)
        self.assertIn('actions: write', self.refresh)
        self.assertIn('checks: read', self.refresh)

    def test_write_capable_static_refresh_is_not_push_triggered(self):
        trigger_block = self.refresh.split('on:\n', 1)[1].split('\npermissions:', 1)[0]
        self.assertIn('  workflow_dispatch:', trigger_block)
        self.assertIn('  schedule:', trigger_block)
        self.assertNotIn('  push:', trigger_block)

    def test_exact_required_checks_gate_merge(self):
        for value in (
            'tablet-gpt-tcg-grader-main-alignment.yml', 'Repository Integrity Guard',
            'selfrefine-full-repo.yml', 'Main SELFREFINE',
            'deep-selfrefine-guard.yml', 'Deep SELFREFINE Guard',
            'exhaustive-selfrefine-guard.yml', 'Exhaustive SELFREFINE Guard',
            'tablet-termux-main-guard.yml', 'Tablet Termux Main Guard',
            'android-updater-guard.yml', 'Android Updater Guard',
            'Tablet GPT TCG Grader Main Alignment',
        ):
            self.assertIn(value, self.refresh)
        self.assertIn('$(git rev-parse origin/main)', self.refresh)
        self.assertIn('-f merge_method=merge -f sha="${CANDIDATE_SHA}"', self.refresh)

    def test_drive_package_push_trigger_is_exact_data_surface(self):
        push = self.package.split('  push:\n', 1)[1].split('  workflow_dispatch:\n', 1)[0]
        for forbidden in ('tablet_gdrive_publish.py', 'tablet_gdrive_sync.py', 'tablet_collection_publish.py', '.github/workflows/gpt-tcg-drive-package.yml'):
            self.assertNotIn(forbidden, push)
        for required in tuple('releases.json promo_events.json supplementary_candidates.json social_event_candidates.json purchase_signals.json social_stock_signals.json market_prices.json market_watch.json purchase_sources.json exchange_rates.json grading_company_updates.json graded_photo_candidates.json source_collection_stats.json adaptive_collection_stats.json auto_update_report.json auto_update_issues.json tcg_live_data.json'.split()):
            self.assertIn(required, push)
        self.assertIn('  workflow_dispatch:', self.package)

    def test_fail_closed_fallback_and_no_bypass(self):
        self.assertIn('PENDING_EXTERNAL_PR', self.refresh)
        self.assertIn('REQUIRED_CHECK_FAILED', self.refresh)
        self.assertIn('REQUIRED_CHECK_TIMEOUT', self.refresh)
        self.assertIn('BASE_ADVANCED', self.refresh)
        self.assertNotIn('--admin', self.refresh)
        self.assertNotIn('--force', self.refresh)
        self.assertIn('gpt-tcg-drive-package.yml/dispatches', self.refresh)


if __name__ == '__main__':
    unittest.main()
