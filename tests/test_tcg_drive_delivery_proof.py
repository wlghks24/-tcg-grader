"""No-network, deterministic regression for tablet Drive receipt status."""
import unittest
from unittest import mock

from execution import tcg_drive_delivery_proof as p

RUN = 'gpt-20261003T100521Z-92a8691a7e46'
NAME = f'manifest_20261003T100521Z_{RUN}.json'
SHA = 'a' * 40
BUNDLE_SHA = 'b' * 64
OUTPUTS = ['releases.json', 'market_prices.json']
CONTRACT = {'required_outputs': OUTPUTS, 'success_status': 'TABLET_SYNC_OK'}


def fixture():
    manifest = dict(schema_version=p.SCHEMA, repository=p.REPO, source='chatgpt_automation',
                    run_id=RUN, main_sha=SHA,
                    bundle={'name': f'TCG_VERIFIED_20261003T100521Z_{RUN}.tar.gz', 'sha256': BUNDLE_SHA},
                    files=[{'name': x} for x in OUTPUTS])
    receipt = dict(run_id=RUN, manifest_name=NAME, main_sha=SHA, bundle_sha256=BUNDLE_SHA,
                   status='TABLET_SYNC_OK', file_count=2, runtime_health=True)
    return manifest, receipt


class DeliveryProofTests(unittest.TestCase):
    def test_valid_receipt_does_not_claim_device(self):
        m, r = fixture()
        self.assertEqual(p.analyze(m, r, NAME, SHA, CONTRACT)['status'],
                         'RECEIPT_MATCHED_NOT_DEVICE_VERIFIED')

    def test_missing_receipt_is_hold(self):
        m, _ = fixture()
        self.assertIn('LATEST_RECEIPT_MISSING_OR_UNREADABLE', p.analyze(m, None, NAME, SHA, CONTRACT)['issues'])

    def test_old_manifest_head_is_hold(self):
        m, r = fixture()
        self.assertIn('MANIFEST_LOCAL_MAIN_SHA_MISMATCH', p.analyze(m, r, NAME, 'c' * 40, CONTRACT)['issues'])

    def test_old_receipt_run_is_hold(self):
        m, r = fixture()
        r['run_id'] = 'old'
        self.assertIn('RECEIPT_RUN_OR_MANIFEST_MISMATCH', p.analyze(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_failed_receipt_is_hold(self):
        m, r = fixture()
        r['status'] = 'FAILED_ROLLED_BACK'
        self.assertIn('RECEIPT_NOT_SUCCESS', p.analyze(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_bad_outputs_is_hold(self):
        m, r = fixture()
        m['files'].pop()
        self.assertIn('MANIFEST_REQUIRED_OUTPUTS_MISMATCH', p.analyze(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_bad_runtime_health_is_hold(self):
        m, r = fixture()
        r['runtime_health'] = False
        self.assertIn('RECEIPT_RUNTIME_OR_FILE_COUNT_UNVERIFIED', p.analyze(m, r, NAME, SHA, CONTRACT)['issues'])

    def test_unknown_local_head_is_hold(self):
        m, r = fixture()
        self.assertIn('LOCAL_MAIN_SHA_UNVERIFIED', p.analyze(m, r, NAME, 'unknown', CONTRACT)['issues'])

    def test_invalid_path_blocks_any_remote_read(self):
        self.assertIsNone(p.MANIFEST_NAME.fullmatch('manifest_20261003T100521Z_../../bad.json'))

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            p.strict_object(b'{"run_id":"a","run_id":"b"}')

    def test_rclone_uses_read_only_cat(self):
        with mock.patch.object(p.subprocess, 'run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b'{"hello":"world"}'
            self.assertEqual(p.rclone_read('gdrive', 'TCG_Grader_Sync', 'to_tablet', NAME), {'hello': 'world'})
            args = run.call_args.args[0]
            self.assertEqual(args[:2], ['rclone', 'cat'])
            self.assertEqual(run.call_args.kwargs['timeout'], 12)


if __name__ == '__main__':
    unittest.main()
