import unittest

import grading_company_health_diagnostics as diag


class GradingCompanyHealthDiagnosticsV252Tests(unittest.TestCase):
    def test_blocked_provider_is_not_retried_or_guessed(self):
        failure, host = diag.classify_failure('HTTPError: status 403')
        self.assertEqual(failure, 'SOURCE_BLOCKED')
        self.assertIsNone(host)

    def test_exact_beckett_maintenance_redirect_is_classified_without_allowlisting(self):
        failure, host = diag.classify_failure(
            'ValueError: unapproved host: beckett-maintenance-page.s3.amazonaws.com'
        )
        self.assertEqual(failure, 'PROVIDER_MAINTENANCE_REDIRECT')
        self.assertEqual(host, 'beckett-maintenance-page.s3.amazonaws.com')

    def test_canonical_beckett_maintenance_reports_status_only(self):
        failure, host = diag.classify_failure(
            'BeckettMaintenanceRedirect: canonical Beckett source temporarily '
            'redirected to maintenance.beckett.com'
        )
        self.assertEqual(failure, 'PROVIDER_MAINTENANCE_REDIRECT')
        self.assertEqual(host, 'maintenance.beckett.com')

    def test_lookalike_beckett_host_not_classified_as_official_maintenance(self):
        failure, host = diag.classify_failure(
            'BeckettMaintenanceRedirect: canonical Beckett source temporarily '
            'redirected to maintenance.beckett.com.attacker.invalid'
        )
        self.assertEqual(failure, 'ROOT_CAUSE_UNRESOLVED')
        self.assertIsNone(host)

    def test_tag_fallback_incomplete_is_parser_schema_suspected(self):
        failure, host = diag.classify_failure(
            'ValueError: TAG official fallback yielded insufficient verified service tiers'
        )
        self.assertEqual(failure, 'SCHEMA_PARSER_CHANGE_SUSPECTED')
        self.assertIsNone(host)

    def test_new_failure_types_keep_last_good_and_no_bypass(self):
        snapshot = {'checked_at': '2026-10-14T08:52:03+00:00', 'sources': {
            'bgs': {'company': 'BGS', 'status': 'degraded',
                    'last_error': 'BeckettMaintenanceRedirect: canonical Beckett '
                    'source temporarily redirected to maintenance.beckett.com'},
            'tag': {'company': 'TAG', 'status': 'degraded',
                    'last_error': 'ValueError: TAG official fallback yielded '
                    'insufficient verified service tiers'},
        }}
        report = diag.diagnose(snapshot)
        self.assertEqual(report['summary']['degraded'], 2)
        self.assertEqual(report['summary']['healthy'], 0)
        self.assertEqual(
            report['summary']['failure_classes'],
            {'PROVIDER_MAINTENANCE_REDIRECT': 1, 'SCHEMA_PARSER_CHANGE_SUSPECTED': 1},
        )
        self.assertFalse(report['policy']['blocked_source_bypass'])
        self.assertFalse(report['policy']['last_good_promotion'])

    def test_unknown_redirect_stays_unapproved(self):
        failure, host = diag.classify_failure('ValueError: unapproved host: example.invalid')
        self.assertEqual(failure, 'REDIRECT_TARGET_UNAPPROVED')
        self.assertEqual(host, 'example.invalid')

    def test_generic_unapproved_redirect_does_not_invent_target(self):
        failure, host = diag.classify_failure('ValueError: unapproved host')
        self.assertEqual(failure, 'REDIRECT_TARGET_UNAPPROVED')
        self.assertIsNone(host)

    def test_parser_zero_is_schema_change_suspected_not_confirmed_root_cause(self):
        failure, host = diag.classify_failure('ValueError: pricing parser yielded zero verified services')
        self.assertEqual(failure, 'SCHEMA_PARSER_CHANGE_SUSPECTED')
        self.assertIsNone(host)

    def test_transient_and_rate_limit_are_separate(self):
        self.assertEqual(diag.classify_failure('TimeoutError: timed out')[0], 'SOURCE_TRANSIENT')
        self.assertEqual(diag.classify_failure('HTTPError: status 429')[0], 'RATE_LIMIT_PRESSURE')

    def test_snapshot_summary_keeps_provider_isolation(self):
        snapshot = {
            'checked_at': '2026-09-18T00:00:00+00:00',
            'sources': {
                'psa': {'company': 'PSA', 'status': 'degraded', 'market': 'US', 'kind': 'pricing',
                        'error': 'HTTPError: status 403'},
                'bgs': {'company': 'BGS', 'status': 'degraded', 'market': 'US', 'kind': 'pricing',
                        'error': 'ValueError: unapproved host: beckett-maintenance-page.s3.amazonaws.com'},
                'cgc': {'company': 'CGC', 'status': 'ok', 'market': 'US', 'kind': 'pricing'},
                'tag-pricing': {'company': 'TAG', 'status': 'degraded', 'market': 'US', 'kind': 'pricing',
                                'error': 'ValueError: pricing parser yielded zero verified services'},
                'tag-home': {'company': 'TAG', 'status': 'ok', 'market': 'GLOBAL', 'kind': 'news'},
                'brg': {'company': 'BRG', 'status': 'ok', 'market': 'KR', 'kind': 'pricing_news'},
            },
        }
        report = diag.diagnose(snapshot)
        self.assertEqual(report['summary']['sources'], 6)
        self.assertEqual(report['summary']['healthy'], 3)
        self.assertEqual(report['summary']['degraded'], 3)
        self.assertEqual(report['summary']['companies_without_healthy_source'], ['PSA', 'BGS'])
        self.assertEqual(report['providers']['TAG']['healthy_sources'], 1)
        self.assertEqual(report['providers']['TAG']['degraded_sources'], 1)
        self.assertEqual(report['policy']['source_allowlist_mutation'], False)
        self.assertEqual(report['policy']['blocked_source_bypass'], False)


if __name__ == '__main__':
    unittest.main()
