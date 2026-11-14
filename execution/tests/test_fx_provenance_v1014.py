"""FX cache provenance regressions; temporary files and mocked provider data only."""
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import multi_market_price_collector as market
import update_exchange_rates as updater


NOW = dt.datetime(2026, 11, 14, 0, 0, tzinfo=dt.timezone.utc)


class FrozenDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class FxProvenanceV1014Tests(unittest.TestCase):
    def payload(self, **changes):
        value = {
            'base': 'KRW', 'updated_at': NOW.isoformat(),
            'source_timestamp': NOW.isoformat(),
            'source': 'https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY',
            'source_route': 'frankfurter-v2',
            'rates': {'USD_KRW': 1400.0, 'JPY_KRW': 9.0, 'EUR_KRW': 1500.0},
        }
        value.update(changes)
        return value

    def read_fx(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'exchange_rates.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            with mock.patch.object(market, 'FX', path), \
                 mock.patch.object(market, 'datetime', FrozenDatetime), \
                 mock.patch.object(market, 'safe_urlopen', side_effect=AssertionError('network forbidden')):
                return market._fx()

    def assert_unavailable(self, payload):
        self.assertEqual({'USD': 0.0, 'JPY': 0.0, 'EUR': 0.0, 'KRW': 1.0},
                         self.read_fx(payload))

    def test_valid_cache_converts_usd_jpy_eur_and_retains_native_krw(self):
        rates = self.read_fx(self.payload())
        self.assertEqual(14000, market._to_krw(10, 'USD', rates))
        self.assertEqual(900, market._to_krw(100, 'JPY', rates))
        self.assertEqual(15000, market._to_krw(10, 'EUR', rates))
        self.assertEqual(100, market._to_krw(100, 'KRW', rates))

    def test_required_cache_base_is_krw(self):
        for base in ('USD', 'XXX', '', None, True, ['KRW']):
            with self.subTest(base=base):
                self.assert_unavailable(self.payload(base=base))
        value = self.payload()
        del value['base']
        self.assert_unavailable(value)

    def test_boolean_and_numeric_text_are_never_fx_quotes(self):
        for value in (True, False, '1400', '', None, [], {}, float('inf'), float('nan')):
            with self.subTest(value=repr(value)):
                result = self.read_fx(self.payload(rates={'USD_KRW': value, 'JPY_KRW': 9.0}))
                self.assertEqual(0.0, result['USD'])
                self.assertEqual(9.0, result['JPY'])
        for rates in ([], None, '1400'):
            with self.subTest(rates=rates):
                self.assert_unavailable(self.payload(rates=rates))

    def test_unsafe_or_malformed_source_fails_closed_without_exception(self):
        for source in (
            'http://api.frankfurter.dev/v2/rates',
            'https://user:secret@api.frankfurter.dev/v2/rates',
            'https://@api.frankfurter.dev/v2/rates',
            'https://api.frankfurter.dev:444/v2/rates',
            'https://api.frankfurter.dev:invalid/v2/rates',
            'https://api.frankfurter.dev.evil.invalid/v2/rates',
            'https://api.frankfurter.dev\\evil.invalid/v2/rates',
            'https://api.frankfurter.dev/\npath',
            ' https://api.frankfurter.dev/v2/rates',
            'https://[malformed', '', None, [], {},
        ):
            with self.subTest(source=source):
                self.assert_unavailable(self.payload(source=source))

    def test_route_requires_matching_known_provider(self):
        for route in ('unknown', '', None, True, {}, 'frankfurter-legacy'):
            with self.subTest(route=route):
                self.assert_unavailable(self.payload(source_route=route))
        self.assertEqual(1400.0, self.read_fx(self.payload(
            source='https://api.frankfurter.app/latest?from=USD&to=KRW,JPY',
            source_route='frankfurter-legacy'))['USD'])
        self.assertEqual(1400.0, self.read_fx(self.payload(
            source='https://api.frankfurter.dev:443/v1/latest?base=USD&symbols=KRW,JPY',
            source_route='frankfurter-v1'))['USD'])

    def test_existing_freshness_and_future_skew_boundaries_are_preserved(self):
        for key in ('source_timestamp', 'updated_at'):
            for hours in (-72, 6):
                value = (NOW + dt.timedelta(hours=hours)).isoformat()
                self.assertEqual(1400.0, self.read_fx(self.payload(**{key: value}))['USD'])
            for offset in (dt.timedelta(hours=-72, seconds=-1), dt.timedelta(hours=6, seconds=1)):
                self.assert_unavailable(self.payload(**{key: (NOW + offset).isoformat()}))

    def test_amount_strings_stay_compatible_but_boolean_amounts_and_rates_do_not(self):
        rates = {'USD': 1400.0, 'KRW': 1.0}
        self.assertEqual(14000, market._to_krw('10.00', 'USD', rates))
        for amount in (True, False):
            self.assertEqual(0, market._to_krw(amount, 'USD', rates))
        for rate in (True, False, '1400'):
            self.assertEqual(0, market._to_krw(10, 'USD', {'USD': rate}))
        self.assertEqual(0, market._to_krw(10, 'USD', []))

    def test_justtcg_boolean_price_is_rejected_before_float_coercion(self):
        payload = {'data': [{'name': 'Pikachu', 'number': '001', 'variants': [
            {'price': True, 'condition': 'NM', 'printing': 'Normal'},
            {'price': 10.0, 'condition': 'NM', 'printing': 'Normal'},
        ]}]}
        with mock.patch.dict(market.os.environ, {'JUSTTCG_API_KEY': 'fixture'}), \
             mock.patch.object(market, '_json_request', return_value=payload):
            rows, status = market._justtcg_api('Pikachu 001', 'pokemon', {'USD': 1400.0}, 'US')
        self.assertEqual('ok', status)
        self.assertEqual([14000], [row['price_krw'] for row in rows])

    def test_ebay_boolean_price_rejected_but_numeric_text_preserved(self):
        payload = {'itemSummaries': [
            {'title': 'bad', 'price': {'value': True, 'currency': 'USD'}},
            {'title': 'valid', 'price': {'value': '10.00', 'currency': 'USD'}},
        ]}
        with mock.patch.dict(market.os.environ, {'EBAY_OAUTH_TOKEN': 'fixture'}), \
             mock.patch.object(market, 'safe_urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
            rows = market._ebay_api('Pikachu', 'US', {'USD': 1400.0})
        self.assertEqual([14000], [row['price_krw'] for row in rows])

    def test_valid_updater_fetch_repairs_missing_or_wrong_cache_base(self):
        observed = dt.datetime.now(dt.timezone.utc).isoformat()
        source = {'base': 'USD', 'date': observed,
                  'rates': {'KRW': 1400.0, 'JPY': 140.0}}
        for base in (None, 'USD', 'XXX'):
            with self.subTest(base=base), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'exchange_rates.json'
                old = self.payload(base=base)
                if base is None:
                    del old['base']
                path.write_text(json.dumps(old), encoding='utf-8')
                with mock.patch.object(updater, 'DATA', path), \
                     mock.patch.object(updater, 'SOURCES', (('frankfurter-v2', source_url()),)), \
                     mock.patch.object(updater, 'fetch', return_value=source), \
                     mock.patch.object(market, 'FX', path):
                    result = updater.main()
                    self.assertEqual('정상', result['collection_status'])
                    self.assertEqual('KRW', result.get('base'))
                    self.assertEqual(1400.0, market._fx()['USD'])
                    self.assertEqual(10.0, market._fx()['JPY'])
                self.assertEqual(result, json.loads(path.read_text(encoding='utf-8')))

    def test_outage_preserves_invalid_base_rates_and_observation_dates(self):
        for base in (None, 'USD', 'XXX'):
            with self.subTest(base=base), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'exchange_rates.json'
                old = self.payload(base=base)
                if base is None:
                    del old['base']
                path.write_text(json.dumps(old), encoding='utf-8')
                with mock.patch.object(updater, 'DATA', path), \
                     mock.patch.object(updater, 'SOURCES', (('frankfurter-v2', source_url()),)), \
                     mock.patch.object(updater, 'fetch', side_effect=OSError('fixture outage')):
                    result = updater.main()
                self.assertEqual('base' in old, 'base' in result)
                for key in ('base', 'rates', 'updated_at', 'source_timestamp'):
                    self.assertEqual(old.get(key), result.get(key), key)
                self.assertEqual('기존 확인환율 유지', result['collection_status'])
                self.assertTrue(result['collection_errors'])


def source_url():
    return 'https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY'


if __name__ == '__main__':
    unittest.main()
