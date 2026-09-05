import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import multi_market_price_collector as market


class MarketReferenceSourcesV130Tests(unittest.TestCase):
    def test_pavilion_one_piece_link_matches_safe_search(self):
        self.assertEqual(
            market._pavilion_url('핸콕', 'ONE PIECE'),
            'https://pavilion-tcg.com/search?gameId=2&language=ko&q=%ED%95%B8%EC%BD%95',
        )
        links=market._reference_links('핸콕','ONE PIECE')
        self.assertEqual(links[0]['source_id'],'pavilion')
        self.assertTrue(links[0]['supports_grade_prices'])

    def test_grade_table_keeps_missing_values_empty(self):
        rows=market._grade_reference([
            {'title':'Boa Hancock raw','price_krw':20020},
            {'title':'Boa Hancock PSA 10','price_krw':88246},
        ])
        by_grade={row['grade']:row for row in rows}
        self.assertEqual(by_grade['미감정']['price_krw'],20020)
        self.assertEqual(by_grade['PSA 10']['price_krw'],88246)
        self.assertEqual(by_grade['PSA 9']['price_krw'],0)

    def test_missing_justtcg_key_is_not_an_error(self):
        with mock.patch.dict(os.environ,{},clear=True):
            rows,status=market._justtcg_api('Pikachu','Pokémon',{'USD':1400,'KRW':1})
        self.assertEqual(rows,[])
        self.assertEqual(status,'not_configured')

    def test_justtcg_api_key_stays_server_side_and_price_is_converted(self):
        payload={'data':[{'name':'Pikachu','number':'025','variants':[{'condition':'Near Mint','printing':'Normal','price':10.0,'lastUpdated':0}]}]}
        with mock.patch.dict(os.environ,{'JUSTTCG_API_KEY':'secret-test-key'},clear=False), \
             mock.patch.object(market,'_json_request',return_value=payload) as request:
            rows,status=market._justtcg_api('Pikachu','Pokémon',{'USD':1400,'KRW':1})
        self.assertEqual(status,'ok')
        self.assertEqual(rows[0]['price_krw'],14000)
        self.assertNotIn('secret-test-key',rows[0]['url'])
        self.assertEqual(request.call_args.args[1]['x-api-key'],'secret-test-key')

    def test_tcgdex_is_pokemon_only_and_requires_exact_number(self):
        def fake_request(url,*_args,**_kwargs):
            if '?' in url:return [{'id':'base-25','localId':'25','name':'Pikachu'}]
            return {'id':'base-25','localId':'25','name':'Pikachu','pricing':{'tcgplayer':{'updated':'2026-01-01','unit':'USD','normal':{'marketPrice':5.0}}}}
        with mock.patch.object(market,'_json_request',side_effect=fake_request):
            rows,status=market._tcgdex_api('Pikachu 25','Pokémon',{'USD':1400,'KRW':1})
        self.assertEqual(status,'ok')
        self.assertEqual(rows[0]['price_krw'],7000)
        self.assertEqual(market._tcgdex_api('Boa Hancock','ONE PIECE',{'USD':1400})[1],'unsupported')

    def test_justtcg_keeps_variants_separate_instead_of_picking_highest(self):
        payload={'data':[{'name':'Pikachu','number':'025','variants':[
            {'condition':'Near Mint','printing':'Normal','price':5.0,'lastUpdated':0},
            {'condition':'Near Mint','printing':'Holo','price':50.0,'lastUpdated':0},
        ]}]}
        with mock.patch.dict(os.environ,{'JUSTTCG_API_KEY':'secret-test-key'},clear=False), \
             mock.patch.object(market,'_json_request',return_value=payload):
            rows,status=market._justtcg_api('Pikachu','Pokémon',{'USD':1400,'KRW':1})
        self.assertEqual(status,'ok')
        self.assertEqual(sorted(row['price_krw'] for row in rows),[7000,70000])
        self.assertEqual({row['printing'] for row in rows},{'Normal','Holo'})

    def test_region_scope_blocks_us_reference_api_for_kr_and_selects_tcgdex_language(self):
        with mock.patch.dict(os.environ,{'JUSTTCG_API_KEY':'secret-test-key'},clear=False):
            rows,status=market._justtcg_api('Pikachu','Pokémon',{'USD':1400,'KRW':1},'KR')
        self.assertEqual(rows,[])
        self.assertEqual(status,'region_unsupported')
        self.assertEqual(market._tcgdex_api('Pikachu','Pokémon',{'USD':1400},'KR')[1],'region_unsupported')

        seen=[]
        def fake_request(url,*_args,**_kwargs):
            seen.append(url)
            if '?' in url:return [{'id':'base-25','localId':'25','name':'Pikachu'}]
            return {'id':'base-25','localId':'25','name':'Pikachu','pricing':{'tcgplayer':{'updated':'2026-01-01','unit':'USD','normal':{'marketPrice':5.0}}}}
        with mock.patch.object(market,'_json_request',side_effect=fake_request):
            rows,status=market._tcgdex_api('Pikachu 25','Pokémon',{'USD':1400,'KRW':1},'JP')
        self.assertEqual(status,'ok')
        self.assertTrue(rows)
        self.assertTrue(all('/v2/ja/' in url for url in seen),seen)
        self.assertTrue(all(row['region_scope']=='JP' for row in rows))

    def test_headline_summary_does_not_mix_raw_and_graded_prices(self):
        items=[
            {'title':'Pikachu raw','price_krw':10000,'source_id':'a'},
            {'title':'Pikachu PSA 10','price_krw':100000,'source_id':'b'},
        ]
        comparable,basis=market._comparable_summary_items('Pikachu',items)
        self.assertEqual(basis,'미감정')
        self.assertEqual([row['price_krw'] for row in comparable],[10000])
        comparable,basis=market._comparable_summary_items('Pikachu PSA 10',items)
        self.assertEqual(basis,'PSA 10')
        self.assertEqual([row['price_krw'] for row in comparable],[100000])

    def test_price_parser_prefers_market_price_over_shipping_or_msrp(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        row=market._extract_price('정가 ₩120,000 · 현재가 ₩89,000 · 배송 ₩3,000',fx)
        self.assertEqual(row['price_krw'],89000)
        row=market._extract_price('price $80.00 shipping $5.00',fx)
        self.assertEqual(row['price_krw'],112000)

    def test_rate_limit_creates_cooldown_without_retry_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            learning=Path(directory)/'learning.json'
            with mock.patch.object(market,'LEARNING',learning):
                market._save_learning({'justtcg':{'hits':0,'error':1,'status':'cooldown','detail':'HTTPError: status 429; Retry-After 90s','cooldown_seconds':90}})
                saved=json.loads(learning.read_text(encoding='utf-8'))
                self.assertGreater(saved['sources']['justtcg']['cooldown_until_epoch'],time.time()+80)
                self.assertTrue(market._cooling('justtcg',saved))

    def test_search_result_host_must_be_exact_domain_or_subdomain(self):
        self.assertTrue(market._host_matches('www.snkrdunk.com','snkrdunk.com'))
        self.assertFalse(market._host_matches('snkrdunk.com.attacker.example','snkrdunk.com'))

    def test_tablet_ui_contains_sources_and_pavilion_grade_view(self):
        js=(Path(__file__).parent/'multi_market_prices.js').read_text(encoding='utf-8')
        for text in ('SNKRDUNK','JustTCG','TCGdex','Pavilion TCG','등급별 참고시세','API 키 필요'):
            self.assertIn(text,js)
        self.assertIn("'—'",js)


if __name__=='__main__':
    unittest.main()
