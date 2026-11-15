"""No network/runtime: restored card UI reuses current FX provenance gates."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import multi_market_price_collector as market
from execution import tablet_card_view_v904 as view


NOW = dt.datetime(2026, 11, 15, tzinfo=dt.timezone.utc)


class FrozenDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


class WorkspaceKrwV1017Tests(unittest.TestCase):
    def payload(self, **changes):
        result = {'base': 'KRW', 'updated_at': NOW.isoformat(),
                  'source_timestamp': NOW.isoformat(),
                  'source': 'https://api.frankfurter.dev/v2/rates',
                  'source_route': 'frankfurter-v2',
                  'rates': {'USD_KRW': 1400, 'JPY_KRW': 9, 'EUR_KRW': 1500}}
        result.update(changes)
        return result

    def rates(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'exchange_rates.json'
            if payload is not None:
                path.write_text(json.dumps(payload), encoding='utf-8')
            with mock.patch.object(market, 'FX', path), \
                 mock.patch.object(market, 'datetime', FrozenDatetime), \
                 mock.patch.object(market, 'safe_urlopen', side_effect=AssertionError('network forbidden')):
                return market._fx()

    def test_krw_is_primary_and_foreign_amount_remains_visible(self):
        rates = self.rates(self.payload())
        for amount, currency, primary in ((10, 'USD', '14,000'),
                                          (100, 'JPY', '900'),
                                          (10, 'EUR', '15,000')):
            with self.subTest(currency=currency):
                page = view.price_reference(amount, currency, rates)
                self.assertTrue(page.startswith('<b>약 ₩' + primary + '</b>'))
                self.assertIn('원통화 ' + currency, page)
                self.assertIn('환산 참고가', page)

    def test_stale_future_missing_or_invalid_source_never_converts(self):
        cases = [None, self.payload(source='https://evil.invalid/rates'),
                 self.payload(base='USD'), self.payload(source_route='unknown')]
        for key in ('source_timestamp', 'updated_at'):
            for hours in (-73, 7):
                cases.append(self.payload(**{key: (NOW + dt.timedelta(hours=hours)).isoformat()}))
        for payload in cases:
            with self.subTest(payload=payload):
                page = view.price_reference(10, 'USD', self.rates(payload))
                self.assertIn('<b>USD 10</b>', page)
                self.assertIn('원화 환산 보류', page)
                self.assertNotIn('₩', page)

    def test_native_krw_does_not_require_foreign_exchange(self):
        page = view.price_reference(38000, 'KRW', self.rates(None))
        self.assertEqual('<b>₩38,000</b>', page)

    def test_invalid_rates_and_amounts_cannot_be_converted(self):
        for rate in (True, '1400', float('inf'), 0):
            with self.subTest(rate=rate):
                page = view.price_reference(10, 'USD', {'USD': rate})
                self.assertIn('원화 환산 보류', page)
        for amount in (True, False, 0, -1, float('inf'), float('nan'), 100_000_001):
            with self.subTest(amount=amount):
                self.assertIn('가격 확인 보류', view.price_reference(amount, 'USD', {'USD': 1400}))

    def test_exact_catalog_currency_is_converted_without_symbol_guessing(self):
        rates = self.rates(self.payload())
        for display in ('USD 10.00', '10 USD', 'USD10'):
            self.assertIn('<b>약 ₩14,000</b>', view.catalog_price_reference(display, rates))
        for display in ('₩38,000', '38,000원', 'KRW 38000'):
            self.assertEqual('<b>₩38,000</b>', view.catalog_price_reference(display, rates))
        for display in ('$10', '¥100', 'USD 10 + shipping USD 5', 'USD 1,00', '<img src=x>'):
            with self.subTest(display=display):
                page = view.catalog_price_reference(display, rates)
                self.assertIn('원화 환산 보류', page)
                self.assertNotIn('<img', page)
                self.assertNotIn('₩', page)

    def test_invalid_numeric_catalog_does_not_break_page(self):
        for display in ('USD 0', 'USD 100000001'):
            self.assertIn('가격 확인 보류', view.catalog_price_reference(display, {'USD': 1400}))

    def test_render_cards_loads_one_validated_fx_snapshot(self):
        with mock.patch.object(view.market_fx, '_fx', return_value={'KRW': 1}) as fx, \
             mock.patch.object(view, 'render', return_value='card') as render:
            self.assertEqual('cardcard', view.render_cards([{}, {}]))
            fx.assert_called_once_with()
            self.assertEqual(2, render.call_count)
            self.assertEqual({'KRW': 1}, render.call_args.kwargs['fx'])

    def test_real_render_uses_fx_and_retains_source_price_semantics(self):
        row = {'game_id': 'pokemon', 'region': 'US', 'kind': 'CARD',
               'name': 'Fixture card', 'card_metadata': {},
               'link_status': 'NEEDS_EXACT_IDENTITY',
               'card_facts': {'prices': [{'provider': 'tcgplayer',
                    'currency': 'USD', 'variant': 'holofoil', 'amount': 10,
                    'metric': '시장 기준가', 'updated_at': NOW.isoformat(),
                    'sale_confirmed': False}]}}
        with mock.patch.object(view.market_fx, '_fx', return_value=self.rates(self.payload())):
            page = view.render(row, '<p>사진 대기</p>')
        self.assertIn('<b>약 ₩14,000</b>', page)
        self.assertIn('USD 10', page)
        self.assertIn('실제 체결가', page)
        self.assertIn(NOW.isoformat(), page)
        blocked = dict(row, link_status='METADATA_CONFLICT')
        page = view.render(blocked, '<p>사진 대기</p>', fx={'USD': 1400})
        self.assertNotIn('₩14,000', page)
        self.assertNotIn('USD 10', page)


if __name__ == '__main__':
    unittest.main()
