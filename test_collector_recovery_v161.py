import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

import graded_photo_multi_source as photos
import release_history_backfill as history
import safe_runtime
import update_market_prices as prices
import update_releases as releases


class CollectorRecoveryV161Tests(unittest.TestCase):
    def test_pokemon_current_official_route_is_used_before_legacy_route(self):
        sample = (
            '拡張パック「ストームエメラルダ」 拡張パック '
            '販売日 2026年 7月31日（金） 希望小売価格 200円（税込）'
        )
        calls = []

        def fake_fetch(url):
            calls.append(url)
            return sample

        with mock.patch.object(releases, 'fetch', side_effect=fake_fetch):
            rows, _fingerprint = releases._collect_pokemon_jp_html()
        self.assertEqual(calls, ['https://www.pokemon-card.com/products/'])
        self.assertEqual(rows[0]['release_date'], '2026-07-31')
        self.assertEqual(rows[0]['price'], '¥200/팩')

    def test_release_route_retries_after_empty_parser_result(self):
        sample = (
            'ブースター ブースターパック 世界最強の戦士〖OP-17〗 '
            '発売日2026.08.22(土) メーカー希望小売価格240円(税込)'
        )
        with mock.patch.object(releases, 'fetch', side_effect=['동적 빈 목록', sample]) as fetch:
            rows = releases.collect_onepiece_jp()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(rows[0]['name'], '世界最強の戦士 [OP-17]')

    def test_history_route_does_not_mislabel_rows_if_server_ignores_year_filter(self):
        current_year = history._today().year
        sample = (
            f'拡張パック「현재」 販売日 {current_year}年 7月31日 希望小売価格 200円 '
            f'拡張パック「과거」 販売日 {current_year - 1}年 5月22日 希望小売価格 180円'
        )
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(history, 'STATE', Path(directory) / 'progress.json'):
            rows, errors = history.pokemon_jp_years(lambda _url: sample, lambda value: value, years_per_run=1)
        self.assertEqual(errors, [])
        self.assertEqual({row['release_date'][:4] for row in rows}, {str(current_year), str(current_year - 1)})
        self.assertTrue(all(row['release_date'].startswith(str(row['archive_year'])) for row in rows))

    def test_trusted_plain_http_redirect_is_upgraded_without_following_http(self):
        normalized = safe_runtime.normalize_public_https_redirect(
            'https://official.example/events',
            'http://official.example/events/2026?game=tcg',
            {'official.example'},
        )
        self.assertEqual(normalized, 'https://official.example/events/2026?game=tcg')
        rejected = safe_runtime.normalize_public_https_redirect(
            'https://official.example/events',
            'http://attacker.example/x',
            {'official.example'},
        )
        self.assertEqual(rejected, 'http://attacker.example/x')
        with self.assertRaisesRegex(ValueError, 'https only'):
            safe_runtime.validate_public_https_url(rejected, {'official.example'})

    def test_kream_500_retries_with_canonical_trailing_slash(self):
        error = urllib.error.HTTPError(
            'https://kream.co.kr/products/290634', 500, 'server error', {}, io.BytesIO()
        )

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, _limit): return b'ONE SIZE 149,000\xec\x9b\x90'
            def geturl(self): return 'https://kream.co.kr/products/290634/'

        with mock.patch.object(prices, 'safe_urlopen', side_effect=[error, Response()]) as opened, \
             mock.patch.object(prices.time, 'sleep'):
            text = prices.fetch('https://kream.co.kr/products/290634')
        self.assertIn('149,000원', text)
        self.assertEqual(opened.call_count, 2)
        self.assertTrue(opened.call_args_list[1].args[0].full_url.endswith('/'))

    def test_kream_trade_parser_ignores_release_and_shipping_prices(self):
        text = '발매가 48,000원 빠른배송 5,000원 ONE SIZE 149,000원 ONE SIZE 137,000원'
        self.assertEqual(prices.kream_label_prices(text, r'ONE SIZE', 50_000, 500_000), [149000, 137000])

    def test_existing_library_photos_are_requeued_but_not_promoted(self):
        manifest = {
            'records': [{
                'source_name': 'psa-front.jpg', 'sha256': 'a' * 64,
                'perceptual_hash': '1' * 16, 'company': 'PSA',
                'certification_id': '88411675', 'label_grade': 10,
                'ocr_label_text': 'PSA GEM MT 10 88411675',
                'official_result': False,
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'library_slab_candidates.json'
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with mock.patch.object(photos, 'LIBRARY_CANDIDATES', path):
                rows = photos._library_candidate_seed_rows()
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]['official_result'])
        self.assertEqual(rows[0]['learning_eligibility'], 'not_eligible_unverified')
        self.assertEqual(photos._candidate_key(rows[0]), ('cert', 'PSA', '88411675', '10.000'))
        kept, stats, audit = photos._review_and_prune_quarantine_v157(
            rows, [dict(rows[0], quarantine_review_count=3)]
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats['retained_retryable'], 1)
        self.assertEqual(audit, [])


if __name__ == '__main__':
    unittest.main()
