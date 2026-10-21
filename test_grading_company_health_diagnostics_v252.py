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

    def test_standard_python_http_error_formats_are_classified(self):
        pairs = (
            ('HTTP Error 403: Forbidden', 'SOURCE_BLOCKED'),
            ('HTTPError 451', 'SOURCE_BLOCKED'),
            ('HTTP Error 429: Too Many Requests', 'RATE_LIMIT_PRESSURE'),
            ('HTTP Error 503: Service Unavailable', 'SOURCE_TRANSIENT'),
            ('HTTPError: status 408', 'SOURCE_TRANSIENT'),
            ('HTTP Error 404: Not Found', 'ROOT_CAUSE_UNRESOLVED'),
        )
        for message, expected in pairs:
            with self.subTest(message=message):
                self.assertEqual(diag.classify_failure(message), (expected, None))

    def test_blocked_http_code_overrides_timeout_in_same_diagnostic(self):
        self.assertEqual(
            diag.classify_failure('HTTP Error 403: Forbidden; TimeoutError: timed out')[0],
            'SOURCE_BLOCKED',
        )
        self.assertEqual(
            diag.classify_failure('HTTP Error 404: Not Found; timed out')[0],
            'ROOT_CAUSE_UNRESOLVED',
        )

    def test_unapproved_redirect_is_not_incorrectly_marked_transient(self):
        result = diag.classify_failure(
            'ValueError: unapproved host: example.invalid; TimeoutError: timed out'
        )
        self.assertEqual(result, ('REDIRECT_TARGET_UNAPPROVED', 'example.invalid'))

    def test_current_beckett_maintenance_diagnostic_is_not_unknown(self):
        error = ('BeckettMaintenanceRedirect: canonical Beckett source temporarily '
                 'redirected to maintenance.beckett.com')
        self.assertEqual(diag.classify_failure(error),
                         ('PROVIDER_MAINTENANCE_REDIRECT', None))
        report = diag.diagnose({'sources': {
            'bgs-pricing': {'company': 'BGS', 'status': 'degraded',
                            'last_error': error, 'failure_class': 'planned_maintenance'}
        }})
        self.assertEqual(
            report['providers']['BGS']['failure_classes'],
            {'PROVIDER_MAINTENANCE_REDIRECT': 1},
        )
        self.assertIn('BGS', report['summary']['companies_without_healthy_source'])
        self.assertFalse(report['policy']['last_good_promotion'])

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
