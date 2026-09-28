import datetime as dt
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import multi_market_price_collector as market
import update_exchange_rates as updater


class FxFailClosedRecoveryV349Tests(unittest.TestCase):
    def _write_fx(self, path, rates, *, source=True, route=True, age_hours=0):
        payload={
            'updated_at':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=age_hours)).isoformat(timespec='seconds'),
            'source_timestamp':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=age_hours)).isoformat(timespec='seconds'),
            'base':'KRW',
            'rates':rates,
        }
        if source:
            payload['source']='https://api.frankfurter.dev/v2/rates?base=USD&quotes=KRW,JPY'
        if route:
            payload['source_route']='frankfurter-v2'
        path.write_text(json.dumps(payload,allow_nan=True),encoding='utf-8')

    def test_fx_accepts_fresh_known_provenance_and_positive_finite_rates(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'exchange_rates.json'
            self._write_fx(path,{'USD_KRW':1360.65,'JPY_KRW':8.60028})
            with mock.patch.object(market,'FX',path):
                fx=market._fx()
            self.assertEqual(1360.65,fx['USD'])
            self.assertEqual(8.60028,fx['JPY'])

    def test_fx_rejects_missing_or_mismatched_provenance(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'exchange_rates.json'
            self._write_fx(path,{'USD_KRW':1360.65,'JPY_KRW':8.60028},source=False)
            with mock.patch.object(market,'FX',path):
                self.assertEqual(0.0,market._fx()['USD'])
            self._write_fx(path,{'USD_KRW':1360.65,'JPY_KRW':8.60028})
            payload=json.loads(path.read_text(encoding='utf-8'))
            payload['source']='https://example.invalid/rates'
            path.write_text(json.dumps(payload),encoding='utf-8')
            with mock.patch.object(market,'FX',path):
                self.assertEqual(0.0,market._fx()['USD'])

    def test_fx_rejects_nonfinite_zero_negative_and_stale_values(self):
        bad_values=(float('nan'),float('inf'),0.0,-1.0)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'exchange_rates.json'
            for bad in bad_values:
                with self.subTest(rate=repr(bad)):
                    self._write_fx(path,{'USD_KRW':bad,'JPY_KRW':8.6})
                    with mock.patch.object(market,'FX',path):
                        fx=market._fx()
                    self.assertEqual(0.0,fx['USD'])
                    self.assertEqual(8.6,fx['JPY'])
            self._write_fx(path,{'USD_KRW':1360.65,'JPY_KRW':8.6},age_hours=73)
            with mock.patch.object(market,'FX',path):
                self.assertEqual(0.0,market._fx()['USD'])

    def test_to_krw_fails_closed_for_nonfinite_or_nonpositive_values(self):
        fx={'KRW':1.0,'USD':1360.0,'JPY':8.6,'EUR':0.0}
        for amount in (float('nan'),float('inf'),0.0,-1.0):
            with self.subTest(amount=repr(amount)):
                self.assertEqual(0,market._to_krw(amount,'USD',fx))
        self.assertEqual(0,market._to_krw(10,'EUR',fx))
        self.assertEqual(13600,market._to_krw(10,'USD',fx))

    def test_updater_recovers_corrupt_cache_when_source_succeeds(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'exchange_rates.json'
            path.write_text('{broken',encoding='utf-8')
            raw={
                'date':dt.datetime.now(dt.timezone.utc).date().isoformat(),
                'rates':{'KRW':1360.0,'JPY':158.13953488372093},
            }
            with mock.patch.object(updater,'DATA',path), \
                 mock.patch.object(updater,'SOURCES',(('frankfurter-v1','https://api.frankfurter.dev/v1/latest'),)), \
                 mock.patch.object(updater,'fetch',return_value=raw):
                result=updater.main()
            self.assertEqual('정상',result['collection_status'])
            self.assertEqual(1360.0,result['rates']['USD_KRW'])
            self.assertTrue(math.isclose(8.6,result['rates']['JPY_KRW'],rel_tol=0,abs_tol=0.001))
            self.assertEqual('frankfurter-v1',result['source_route'])
            self.assertTrue(result['source_timestamp'])

    def test_updater_rejects_mixed_staleness_across_required_quotes(self):
        now=dt.datetime.now(dt.timezone.utc)
        raw=[
            {'quote':'KRW','rate':1360.0,'updated_at':now.isoformat()},
            {'quote':'JPY','rate':158.1,'updated_at':(now-dt.timedelta(hours=73)).isoformat()},
        ]
        with self.assertRaises(ValueError):
            updater.parse_source_timestamp(raw)

    def test_updater_requires_timestamp_for_both_required_quotes(self):
        now=dt.datetime.now(dt.timezone.utc)
        raw=[
            {'quote':'KRW','rate':1360.0,'updated_at':now.isoformat()},
            {'quote':'JPY','rate':158.1},
        ]
        with self.assertRaises(ValueError):
            updater.parse_source_timestamp(raw)

    def test_updater_ignores_unrelated_stale_quote_timestamp(self):
        now=dt.datetime.now(dt.timezone.utc)
        raw=[
            {'quote':'KRW','rate':1360.0,'updated_at':now.isoformat()},
            {'quote':'JPY','rate':158.1,'updated_at':now.isoformat()},
            {'quote':'EUR','rate':0.86,'updated_at':(now-dt.timedelta(hours=120)).isoformat()},
        ]
        observed=dt.datetime.fromisoformat(updater.parse_source_timestamp(raw))
        self.assertLess(abs((now-observed).total_seconds()),5)

    def test_fx_rejects_missing_stale_or_future_source_timestamp(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'exchange_rates.json'
            self._write_fx(path,{'USD_KRW':1360.65,'JPY_KRW':8.6})
            payload=json.loads(path.read_text(encoding='utf-8'))
            for value in (None,
                          (dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=73)).isoformat(),
                          (dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=7)).isoformat()):
                with self.subTest(source_timestamp=value):
                    if value is None:payload.pop('source_timestamp',None)
                    else:payload['source_timestamp']=value
                    path.write_text(json.dumps(payload),encoding='utf-8')
                    with mock.patch.object(market,'FX',path):
                        self.assertEqual(0.0,market._fx()['USD'])

    def test_updater_corrupt_cache_and_total_outage_never_invents_rates(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'exchange_rates.json'
            path.write_text('{broken',encoding='utf-8')
            with mock.patch.object(updater,'DATA',path), \
                 mock.patch.object(updater,'SOURCES',(('frankfurter-v1','https://api.frankfurter.dev/v1/latest'),)), \
                 mock.patch.object(updater,'fetch',side_effect=OSError('offline')):
                result=updater.main()
            self.assertEqual({},result['rates'])
            self.assertEqual('사용 가능한 확인환율 없음',result['collection_status'])
            self.assertTrue(result['collection_errors'])


if __name__=='__main__':
    unittest.main()
