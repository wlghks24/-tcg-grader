"""No real collection: exercise the production CLI with private sentinel payloads."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import wyyyes_market_source as market
from execution import source_security_successor_v1015 as successor


class SourceSecurityV1015Tests(unittest.TestCase):
    def capture(self, *, result=None, error=None):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(market, 'collect_quotes', return_value=result, side_effect=error):
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                code = market.cli_main()
        self.assertEqual(errors.getvalue(), '')
        self.assertNotIn('PRIVATE_SENTINEL', output.getvalue())
        return code, json.loads(output.getvalue())

    def test_sensitive_nested_fields_never_reach_stdout(self):
        payload = {'status': 'ok', 'quotes': [{'card_name': 'PRIVATE_SENTINEL',
                    'url': 'https://example.invalid/?token=PRIVATE_SENTINEL',
                    'nested': {'password': 'PRIVATE_SENTINEL'}}],
                   'errors': ['PRIVATE_SENTINEL'], 'unexpected': 'PRIVATE_SENTINEL'}
        code, out = self.capture(result=payload)
        self.assertEqual(code, 0)
        self.assertEqual(out, {'status': 'ok', 'quote_count': 1, 'error_count': 1})
        self.assertEqual(payload['quotes'][0]['card_name'], 'PRIVATE_SENTINEL')

    def test_unknown_status_and_count_fields_cannot_inject_text(self):
        _, out = self.capture(result={'status': 'PRIVATE_SENTINEL', 'quotes': 'PRIVATE_SENTINEL',
                                     'errors': {'token': 'PRIVATE_SENTINEL'},
                                     'quote_count': 'PRIVATE_SENTINEL'})
        self.assertEqual(out, {'status': 'unknown', 'quote_count': 0, 'error_count': 0})

    def test_provider_exception_has_fixed_redacted_status(self):
        code, out = self.capture(error=OSError('PRIVATE_SENTINEL password=private'))
        self.assertEqual(code, 2)
        self.assertEqual(out, {'status': 'collection_failed', 'quote_count': 0, 'error_count': 1})

    def test_counts_are_bounded(self):
        _, out = self.capture(result={'status': 'degraded_preserved', 'quotes': [{}] * 80,
                                     'errors': ['PRIVATE_SENTINEL'] * 50})
        self.assertEqual(out, {'status': 'degraded_preserved', 'quote_count': 36, 'error_count': 20})

    def test_non_mapping_is_invalid(self):
        for value in (None, True, [], 'PRIVATE_SENTINEL'):
            with self.subTest(value=type(value).__name__):
                _, out = self.capture(result=value)
                self.assertEqual(out['status'], 'invalid_result')

    def test_exact_source_successor(self):
        self.assertTrue(successor.validate_security_successor_v1015())
        self.assertFalse(successor.EXPECTED['physical_tablet_verified'])

    def test_wrong_prior_digest_is_rejected(self):
        with self.assertRaises(AssertionError):
            successor.validate_security_successor_v1015('0' * 64)

    def test_live_runtime_tampering_is_rejected(self):
        original = Path.read_bytes
        def changed(path):
            data = original(path)
            return data + b'changed' if path == successor.ROOT / 'wyyyes_market_source.py' else data
        with patch.object(Path, 'read_bytes', changed), self.assertRaises(AssertionError):
            successor.validate_security_successor_v1015()

    def test_false_device_claim_is_rejected(self):
        original = Path.read_text
        def changed(path, *args, **kwargs):
            value = original(path, *args, **kwargs)
            if path == successor.PROOF:
                data = json.loads(value)
                data['physical_tablet_verified'] = True
                return json.dumps(data)
            return value
        with patch.object(Path, 'read_text', changed), self.assertRaises(AssertionError):
            successor.validate_security_successor_v1015()
