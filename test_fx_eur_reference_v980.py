import datetime as dt
import unittest
from fx_eur_reference_v980 import verified_eur_krw

NOW = dt.datetime(2026, 11, 9, 12, tzinfo=dt.timezone.utc)
BASE = '2026-11-08T00:00:00+00:00'
EUR = {'base': 'USD', 'quote': 'EUR', 'rate': 0.9, 'date': '2026-11-08'}


class FxEurReferenceV980Tests(unittest.TestCase):
    def run_fx(self, data, stamp=BASE, usd=1350):
        return verified_eur_krw(data, usd, stamp, now=NOW)

    def test_v2_row(self):
        self.assertEqual(self.run_fx({'data':[EUR]}), 1500)

    def test_v1_rates(self):
        self.assertEqual(self.run_fx({'base':'USD','rates':{'KRW':1350,'JPY':150,'EUR':0.9},'date':'2026-11-08'}),1500)

    def test_list_response(self):
        self.assertEqual(self.run_fx([EUR]),1500)

    def test_missing_optional_quote_keeps_compatibility(self):
        self.assertIsNone(self.run_fx({'data':[{'quote':'KRW','rate':1350,'date':'2026-11-08'}]}))

    def test_missing_optional_quote_v1_keeps_compatibility(self):
        self.assertIsNone(self.run_fx({'rates':{'KRW':1350,'JPY':150},'date':'2026-11-08'}))

    def test_negative_and_untyped_quotes_rejected(self):
        for v in [-1,0,True,'0.9',float('nan'),float('inf'),10000]:
            with self.subTest(v=v),self.assertRaises(ValueError):self.run_fx({'data':[{**EUR,'rate':v}]})

    def test_stale_quote_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[{**EUR,'date':'2026-11-01'}]})

    def test_future_quote_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[{**EUR,'date':'2026-11-12'}]})

    def test_cross_day_skew_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[EUR]},stamp='2026-11-05T00:00:00Z')

    def test_wrong_base_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[{**EUR,'base':'EUR'}]})

    def test_ambiguous_quote_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[EUR,EUR]})

    def test_missing_source_timestamp_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[{k:v for k,v in EUR.items() if k!='date'}]})

    def test_untrusted_fx_base_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'base':'EUR','rates':{'EUR':0.9},'date':'2026-11-08'})

    def test_invalid_usd_rate_rejected(self):
        for v in [-2,False,float('nan'),30000]:
            with self.subTest(v=v),self.assertRaises(ValueError):self.run_fx({'data':[EUR]},usd=v)

    def test_bad_base_time_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[EUR]},stamp='malformed')

    def test_no_io_or_mutation(self):
        d={'data':[dict(EUR)]}
        before=repr(d)
        self.run_fx(d)
        self.assertEqual(repr(d),before)

    def test_timezone_naive_timestamp_rejected(self):
        with self.assertRaises(ValueError):self.run_fx({'data':[{**EUR,'date':'2026-11-08T08:00:00'}]})

    def test_date_only_v1_keeps_valid_rate(self):
        self.assertEqual(self.run_fx({'rates':{'EUR':0.9},'date':'2026-11-08'}),1500)


if __name__=='__main__':unittest.main()
