"""No-network, deterministic regression for tablet Drive receipt status."""
import datetime as dt
from unittest import TestCase, main, mock

from execution import tcg_drive_delivery_proof as p

RUN = 'gpt-20261003T100521Z-92a8691a7e46'
NAME = f'manifest_20261003T100521Z_{RUN}.json'
SHA = 'a' * 40
BUNDLE_SHA = 'b' * 64
OUTPUTS = ['releases.json', 'market_prices.json']
CONTRACT = {'required_outputs': OUTPUTS, 'success_status': 'TABLET_SYNC_OK'}
NOW = dt.datetime(2026, 10, 3, 12, tzinfo=dt.timezone.utc)


def fixture():
    manifest = dict(schema_version=p.SCHEMA, repository=p.REPO, source='chatgpt_automation',
                    run_id=RUN, main_sha=SHA, created_at='2026-10-03T10:05:22+00:00',
                    bundle={'name': f'TCG_VERIFIED_20261003T100521Z_{RUN}.tar.gz', 'sha256': BUNDLE_SHA, 'size': 100},
                    files=[{'name': x, 'size': 2, 'sha256': BUNDLE_SHA} for x in OUTPUTS])
    receipt = dict(run_id=RUN, manifest_name=NAME, main_sha=SHA, bundle_sha256=BUNDLE_SHA,
                   status='TABLET_SYNC_OK', file_count=2, runtime_health=True,
                   schema_version=p.SCHEMA, repository=p.REPO,
                   applied_at='2026-10-03T10:07:00+00:00', runtime_main_sha_verified=True)
    return manifest, receipt


def audit(*args):
    return p.analyze(*args, now=NOW)


class DeliveryProofTests(TestCase):
    def test_valid_receipt_does_not_claim_device(self):
        m, r = fixture()
        self.assertEqual(audit(m, r, NAME, SHA, CONTRACT)['status'],
                         'RECEIPT_MATCHED_NOT_DEVICE_VERIFIED')

    def test_missing_manifest_created_at_is_hold(self):
        m, r = fixture()
        del m['created_at']
        self.assertIn('MANIFEST_CREATED_AT_INVALID_OR_STALE', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_old_manifest_is_hold_even_if_hashes_match(self):
        m, r = fixture()
        m['created_at'] = '2026-09-20T10:05:22Z'
        self.assertIn('MANIFEST_CREATED_AT_INVALID_OR_STALE', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_manifest_filename_date_mismatch_is_hold(self):
        m, r = fixture()
        m['created_at'] = '2026-10-03T11:00:00+00:00'
        self.assertIn('MANIFEST_FILENAME_TIMESTAMP_MISMATCH', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_future_manifest_date_is_hold(self):
        m, r = fixture()
        m['created_at'] = '2026-10-04T10:05:22+00:00'
        self.assertIn('MANIFEST_CREATED_AT_INVALID_OR_STALE', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_old_or_earlier_receipt_is_hold(self):
        for old in ('2026-09-20T10:07:00Z', '2026-10-02T10:07:00Z'):
            with self.subTest(applied_at=old):
                m, r = fixture()
                r['applied_at'] = old
                self.assertIn('RECEIPT_APPLIED_AT_INVALID_OR_STALE', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_missing_or_naive_receipt_time_is_hold(self):
        for wrong in (None, '2026-10-03T10:07:00', 'not-a-date'):
            with self.subTest(applied_at=wrong):
                m, r = fixture()
                r['applied_at'] = wrong
                self.assertIn('RECEIPT_APPLIED_AT_INVALID_OR_STALE', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_foreign_receipt_identity_is_hold(self):
        m, r = fixture()
        r['repository'] = 'untrusted/repo'
        self.assertIn('RECEIPT_UNTRUSTED_IDENTITY', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_unverified_runtime_main_sha_is_hold(self):
        m, r = fixture()
        r['runtime_main_sha_verified'] = False
        self.assertIn('RECEIPT_RUNTIME_SHA_NOT_VERIFIED', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_missing_receipt_is_hold(self):
        m, _ = fixture()
        self.assertIn('LATEST_RECEIPT_MISSING_OR_UNREADABLE', audit(m, None, NAME, SHA, CONTRACT)['issues'])

    def test_old_manifest_head_is_hold(self):
        m, r = fixture()
        self.assertIn('MANIFEST_LOCAL_MAIN_SHA_MISMATCH', audit(m, r, NAME, 'c' * 40, CONTRACT)['issues'])

    def test_old_receipt_run_is_hold(self):
        m, r = fixture()
        r['run_id'] = 'old'
        self.assertIn('RECEIPT_RUN_OR_MANIFEST_MISMATCH', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_failed_receipt_is_hold(self):
        m, r = fixture()
        r['status'] = 'FAILED_ROLLED_BACK'
        self.assertIn('RECEIPT_NOT_SUCCESS', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_bad_outputs_is_hold(self):
        m, r = fixture()
        m['files'].pop()
        self.assertIn('MANIFEST_REQUIRED_OUTPUTS_MISMATCH', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_missing_hash_in_manifest_is_hold(self):
        m, r = fixture()
        del m['files'][0]['sha256']
        self.assertIn('MANIFEST_REQUIRED_OUTPUTS_MISMATCH', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_boolean_file_count_is_hold(self):
        m, r = fixture()
        r['file_count'] = True
        self.assertIn('RECEIPT_RUNTIME_OR_FILE_COUNT_UNVERIFIED', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_bad_runtime_health_is_hold(self):
        m, r = fixture()
        r['runtime_health'] = False
        self.assertIn('RECEIPT_RUNTIME_OR_FILE_COUNT_UNVERIFIED', audit(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_unknown_local_head_is_hold(self):
        m, r = fixture()
        self.assertIn('LOCAL_MAIN_SHA_UNVERIFIED', audit(m, r, NAME, 'unknown', CONTRACT)['issues'])

    def test_invalid_path_blocks_any_remote_read(self):
        self.assertIsNone(p.MANIFEST_NAME.fullmatch('manifest_20261003T100521Z_../../bad.json'))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            p.strict_object(b'{"run_id":"a","run_id":"b"}')

    def test_invalid_calendar_date_in_manifest_name_is_hold(self):
        m, r = fixture()
        for bogus in ('manifest_20261303T100521Z_' + RUN + '.json',
                      'manifest_20260230T100521Z_' + RUN + '.json',
                      'manifest_20261003T256161Z_' + RUN + '.json'):
            with self.subTest(filename=bogus):
                result = audit(m, r, bogus, SHA, CONTRACT)
                self.assertEqual(result['status'], 'HOLD')
                self.assertIn('INVALID_MANIFEST_TIMESTAMP', result['issues'])

    def test_empty_or_duplicate_required_output_contract_cannot_pass(self):
        m, r = fixture()
        for broken in ([], ['releases.json', 'releases.json']):
            with self.subTest(required_outputs=broken):
                contract = dict(CONTRACT, required_outputs=broken)
                result = audit(m, r, NAME, SHA, contract)
                self.assertEqual(result['status'], 'HOLD')
                self.assertIn('MANIFEST_REQUIRED_OUTPUTS_MISMATCH', result['issues'])

    def test_unsafe_rclone_root_is_rejected_before_network(self):
        for root in ('TCG_Grader_Sync/./to_tablet',
                     'TCG_Grader_Sync//to_tablet',
                     'TCG_Grader_Sync/../to_tablet'):
            with self.subTest(root=root), mock.patch.object(p, 'rclone_read') as reader, \
                 mock.patch('sys.argv', ['delivery', '--remote', 'gdrive',
                                          '--remote-root', root, '--manifest', NAME,
                                          '--local-head', SHA, '--contract', 'ignored.json']):
                self.assertEqual(p.main(), 0)
                reader.assert_not_called()

    def test_rclone_uses_read_only_cat(self):
        with mock.patch.object(p.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b'{"hello":"world"}'
            self.assertEqual(p.rclone_read('gdrive', 'TCG_Grader_Sync', 'to_tablet', NAME), {'hello': 'world'})
            args = run.call_args.args[0]
            self.assertEqual(args, ['rclone', 'cat',
                                    f'gdrive:TCG_Grader_Sync/to_tablet/{NAME}',
                                    '--count', '16385'])
            self.assertEqual(run.call_args.kwargs['timeout'], 12)
            self.assertEqual(run.call_args.kwargs['stdout'], p.subprocess.PIPE)
            self.assertEqual(run.call_args.kwargs['stderr'], p.subprocess.DEVNULL)

    def test_read_limit_exact_boundary_is_accepted(self):
        # 16 KiB JSON stays valid; the remote CLI cap remains 16 KiB+1.
        payload = b'{"pad":"' + b'a' * (16384 - len(b'{"pad":""}')) + b'"}'
        self.assertEqual(len(payload), 16384)
        with mock.patch.object(p.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = payload
            parsed = p.rclone_read('gdrive', 'TCG_Grader_Sync', 'to_tablet', NAME)
            self.assertEqual(len(parsed['pad']), 16384 - len(b'{"pad":""}'))
            self.assertEqual(run.call_args.args[0][-2:], ['--count', '16385'])

    def test_read_limit_sentinel_is_rejected(self):
        payload = b'{"pad":"' + b'a' * (16385 - len(b'{"pad":""}')) + b'"}'
        self.assertEqual(len(payload), 16385)
        with mock.patch.object(p.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = payload
            with self.assertRaisesRegex(ValueError, 'oversized'):
                p.rclone_read('gdrive', 'TCG_Grader_Sync', 'receipts', NAME)
            self.assertEqual(run.call_args.args[0][-2:], ['--count', '16385'])

    def test_failed_read_cannot_be_promoted_to_receipt(self):
        with mock.patch.object(p.subprocess, 'run') as run:
            run.return_value.returncode = 3
            run.return_value.stdout = b'{"status":"TABLET_SYNC_OK"}'
            with self.assertRaises(ValueError):
                p.rclone_read('gdrive', 'TCG_Grader_Sync', 'receipts', NAME)


if __name__ == '__main__':
    main()
