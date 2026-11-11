"""Offline integration tests for V980 EUR/KRW updater.

Uses a temporary output file and mocked HTTP; never rewrites the main FX cache.
"""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import update_exchange_rates as fx


def v2_rows(*, eur=True, eur_value=0.9, when=None):
    day=when or dt.datetime.now(dt.timezone.utc).date().isoformat()
    rows=[{'base':'USD','quote':'KRW','rate':1350.0,'date':day},
          {'base':'USD','quote':'JPY','rate':150.0,'date':day}]
    if eur:rows.append({'base':'USD','quote':'EUR','rate':eur_value,'date':day})
    return rows


class FxEurIntegrationV980Tests(unittest.TestCase):
    def run_candidate(self, sources):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'exchange_rates.json'
            path.write_text(json.dumps({'rates':{'USD_KRW':1200.0,'JPY_KRW':8.0},'source':'previous'}),encoding='utf-8')
            with mock.patch.object(fx,'DATA',path),mock.patch.object(fx,'SOURCES',tuple((f'fixture-{i}','https://api.frankfurter.dev/v2/rates') for i in range(len(sources)))):
                with mock.patch.object(fx,'fetch',side_effect=sources):
                    result=fx.main()
            self.assertEqual(result,json.loads(path.read_text(encoding='utf-8')))
            return result

    def test_eur_three_quotes_emitted(self):
        result=self.run_candidate([v2_rows()])
        self.assertEqual(result['collection_status'],'정상')
        self.assertAlmostEqual(result['rates']['EUR_KRW'],1500)
        self.assertAlmostEqual(result['rates']['USD_KRW'],1350)
        self.assertAlmostEqual(result['rates']['JPY_KRW'],9)

    def test_missing_optional_eur_quote_does_not_invent_rate(self):
        result=self.run_candidate([v2_rows(eur=False)])
        self.assertEqual(result['collection_status'],'정상')
        self.assertNotIn('EUR_KRW',result['rates'])

    def test_invalid_eur_quote_fallback_to_next_valid_source(self):
        result=self.run_candidate([v2_rows(eur_value='invalid'),v2_rows()])
        self.assertEqual(result['source_route'],'fixture-1')
        self.assertAlmostEqual(result['rates']['EUR_KRW'],1500)

    def test_all_sources_invalid_preserves_last_verified_rates(self):
        result=self.run_candidate([v2_rows(eur_value=True)])
        self.assertEqual(result['collection_status'],'기존 확인환율 유지')
        self.assertEqual(result['rates'],{'USD_KRW':1200.0,'JPY_KRW':8.0})
        self.assertTrue(result['collection_errors'])

    def test_source_pair_emits_eur_requests(self):
        self.assertTrue(all('EUR' in url for _,url in fx.SOURCES))


if __name__=='__main__':unittest.main()
