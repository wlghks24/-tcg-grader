"""Revision tags and redacted diagnostics; synthetic data and mocked Git only."""
import json
import subprocess
import unittest
from unittest.mock import patch

from execution import tablet_collection_receipt_v901 as receipt
from execution import tablet_collection_report_v899 as report

SHA = 'e' * 40
START = '2026-11-04T00:00:00+00:00'
END = '2026-11-04T00:03:00+00:00'


class ReceiptTests(unittest.TestCase):
    def stamp(self, **kwargs):
        return receipt.stamp(kwargs.get('result', {'saved': 31, 'errors': 5}),
                             kwargs.get('revision', SHA), kwargs.get('start', START),
                             kwargs.get('end', END), kwargs.get('active', True))

    def test_old_receipt_is_not_promoted_by_healthy_current_checkout(self):
        result = receipt.summarize({'saved': 31, 'errors': 5}, SHA)
        self.assertEqual('LEGACY_UNVERSIONED_RECEIPT', result['status'])
        self.assertFalse(result['generation_recorded'])
        self.assertFalse(result['revision_matches_current'])

    def test_new_receipt_retains_outcomes_but_revision_is_not_cycle_training_proof(self):
        stamped = self.stamp()
        self.assertEqual(31, stamped['saved']); self.assertEqual(5, stamped['errors'])
        result = receipt.summarize(stamped, SHA)
        self.assertTrue(result['revision_matches_current'])
        self.assertTrue(result['generation_recorded'])
        self.assertTrue(result['provider_json_v900_active'])
        self.assertFalse(result['collector_verified'])
        self.assertFalse(result['identity_or_training_verified'])
        self.assertFalse(result['revision_is_loaded_source_attestation'])

    def test_mismatched_checkout_and_unknown_startup_revision_stay_distinct(self):
        self.assertFalse(receipt.summarize(self.stamp(), 'f' * 40)['revision_matches_current'])
        unknown = receipt.summarize(self.stamp(revision=None), SHA)
        self.assertTrue(unknown['generation_recorded'])
        self.assertIsNone(unknown['collector_revision'])
        self.assertFalse(unknown['revision_matches_current'])

    def test_inactive_adapter_is_retained_as_false_not_hidden(self):
        self.assertFalse(receipt.summarize(self.stamp(active=False), SHA)['provider_json_v900_active'])

    def test_malformed_revision_times_order_and_nonboolean_adapter_are_rejected(self):
        for kwargs in ({'revision': 'PRIVATE'}, {'start': '2026-11-04'},
                       {'end': '2026-11-03T00:00:00Z'}, {'active': 1}, {'start': None}):
            with self.assertRaises(ValueError): self.stamp(**kwargs)
        with self.assertRaises(ValueError): receipt.summarize(self.stamp(), 'bad')

    def test_unknown_schema_is_unversioned_not_current_revision(self):
        value = dict(self.stamp(), receipt_schema=902)
        self.assertFalse(receipt.summarize(value, SHA)['generation_recorded'])

    def test_revision_is_read_once_from_fixed_git_and_errors_are_unknown(self):
        with patch.object(receipt.subprocess, 'check_output', return_value=SHA+'\n') as git:
            self.assertEqual(SHA, receipt.startup_revision('/fixed/repo'))
            self.assertEqual(['git', '-C', '/fixed/repo', 'rev-parse', 'HEAD'], git.call_args.args[0])
        for error in (OSError('PRIVATE'), subprocess.TimeoutExpired('git', 3)):
            with patch.object(receipt.subprocess, 'check_output', side_effect=error):
                self.assertIsNone(receipt.startup_revision('/fixed/repo'))
        with patch.object(receipt.subprocess, 'check_output', return_value='PRIVATE'):
            self.assertIsNone(receipt.startup_revision('/fixed/repo'))


class DiagnosticTests(unittest.TestCase):
    def test_automatic_collection_enablement_and_quotas_are_reported_without_enabling(self):
        result = report._auto({'auto_enabled': False, 'last_result': None,
                              'collection_policy': {'period_seconds': 21600, 'daily_limit': 144,
                                                    'private_unknown': 'PRIVATE'}}, set())
        self.assertIs(result['auto_enabled'], False)
        self.assertEqual({'period_seconds': 21600, 'daily_limit': 144}, result['collection_policy'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertIsNone(report._auto({'last_result': None}, set())['auto_enabled'])
        with self.assertRaises(report.SnapshotError): report._auto({'auto_enabled': 1}, set())

    def test_known_source_attempt_is_visible_without_promoting_undeclared_edition(self):
        value = {'last_result': {'per_source': {'onepiece|CN-T': {'source': 'PunkRecords', 'errors': 1}}}}
        result = report._auto(value, {('onepiece', 'CN-T')}, SHA, {('onepiece', 'JP')})
        self.assertEqual(1, result['per_source'][0]['errors'])
        self.assertEqual('CN-T', result['per_source'][0]['region'])
        self.assertFalse(result['per_source'][0]['region_declared_in_registry'])
        self.assertFalse(result['source_statistics_are_edition_verification'])
        self.assertEqual(0, result['other_source_count'])

    def test_error_details_separate_mime_from_list_schema_without_raw_messages(self):
        value = report.issue_hints(['onepiece|JP: 출처 MIME 형식 오류 PRIVATE',
                                   'swu|US: SWUDB 세트 목록 형식 오류 PRIVATE',
                                   'JSON 출처 응답 길이 불일치 PRIVATE', '실행시간 예산 도달 PRIVATE'])
        self.assertEqual(1, value['detail_hint_counts']['RESPONSE_MIME'])
        self.assertEqual(1, value['detail_hint_counts']['LIST_SCHEMA'])
        self.assertEqual(1, value['detail_hint_counts']['RESPONSE_LENGTH'])
        self.assertFalse(value['counts_are_error_count'])
        self.assertNotIn('PRIVATE', json.dumps(value))

    def test_auto_summary_distinguishes_new_and_legacy_receipts(self):
        value = receipt.stamp({'run_at': START, 'scanned': 44, 'saved': 31, 'errors': 5}, SHA, START, END, True)
        result = report._auto({'last_result': value}, set(), SHA)
        self.assertEqual('READABLE_REVISION_TAGGED_RECEIPT', result['last_result_status'])
        self.assertTrue(result['run_generation_recorded'])
        self.assertTrue(result['receipt']['revision_matches_current'])
        self.assertFalse(result['current_build_cycle_verified'])
        legacy = report._auto({'last_result': {'scanned': 44, 'saved': 31}}, set(), SHA)
        self.assertFalse(legacy['run_generation_recorded'])
        self.assertEqual('READABLE_UNVERSIONED_RECEIPT', legacy['last_result_status'])

    def test_top_level_tag_status_matches_auto_without_claiming_verified_collection(self):
        auto = {'ok': True, 'last_result': receipt.stamp({}, SHA, START, END, True)}
        reader = lambda path: auto if path == report.ROUTES['auto'] else {'ok': True, 'items': [], 'unified_catalog': []}
        with patch.object(report, 'load_registry', return_value={'games': []}), patch.object(report, '_events', return_value={}), patch.object(report, 'startup_revision', return_value=SHA):
            result = report.collection_report('/fixed/repo', reader=reader)
        self.assertTrue(result['run_generation_recorded'])
        self.assertFalse(result['collector_verified'])
        self.assertFalse(result['current_build_cycle_verified'])


if __name__ == '__main__':
    unittest.main()
