import unittest
from unittest import mock
import multi_market_price_collector as m

class MultiMarketPriceCollectorTests(unittest.TestCase):
    def test_required_sources_present(self):
        names={x['name'] for x in m.SOURCES}
        for name in ['eBay','Amazon US','Amazon JP','KREAM','당근','번개장터','중고나라','Collectory','TCGplayer','Cardmarket','Mercari JP','Yahoo! Auctions JP','SNKRDUNK','JustTCG','TCGdex','Pavilion TCG']:
            self.assertIn(name,names)
    def test_price_parser_converts_krw_usd_jpy(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        self.assertEqual(m._extract_price('가격 ₩12,000',fx)['price_krw'],12000)
        self.assertEqual(m._extract_price('price $10.00',fx)['price_krw'],14000)
        self.assertEqual(m._extract_price('price ¥2,000',fx)['price_krw'],18000)
    def test_learning_health_is_bounded(self):
        self.assertGreaterEqual(m._health('x',{}),.75)
        self.assertLessEqual(m._health('x',{}),1.15)
    def test_empty_query_never_generates_price(self):
        out=m.search_multi_market('',force=True)
        self.assertFalse(out['ok'])
        self.assertEqual(out['items'],[])

    def test_card_number_matching_is_exact_not_substring(self):
        self.assertFalse(m._card_number_matches('001','1001'))
        self.assertTrue(m._card_number_matches('001','SV1-001'))
        self.assertTrue(m._card_number_matches('OP13-007','OP13-007'))
        self.assertFalse(m._card_number_matches('OP13-007','OP14-007'))
        self.assertFalse(m._card_number_matches('SVI001','SVI1001'))

    def test_justtcg_rejects_substring_card_number_collision(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        payload={'data':[{'name':'Pikachu','number':'1001','variants':[{'price':10.0,'condition':'NM','printing':'Normal'}]}]}
        with mock.patch.dict(m.os.environ,{'JUSTTCG_API_KEY':'token'}), mock.patch.object(m,'_json_request',return_value=payload):
            rows,status=m._justtcg_api('Pikachu 001','pokemon',fx,'US')
        self.assertEqual(status,'ok')
        self.assertEqual(rows,[])

    def test_tcgdex_rejects_substring_card_number_collision(self):
        fx={'KRW':1.0,'USD':1400.0,'JPY':9.0}
        def fake_json(url,*args,**kwargs):
            if '/cards?' in url:return [{'id':'sv01-1001'}]
            return {'name':'Pikachu','localId':'1001','pricing':{'tcgplayer':{'updated':'2026-09-25','normal':{'marketPrice':10.0}}}}
        with mock.patch.object(m,'_json_request',side_effect=fake_json):
            rows,status=m._tcgdex_api('Pikachu 001','pokemon',fx,'US')
        self.assertEqual(status,'ok')
        self.assertEqual(rows,[])

    def test_grade_reference_prefers_completed_sales_without_mixing_asking_prices(self):
        items=[
            {'title':'Pikachu PSA 10 sold','price_kind':'실거래/완료 신호','price_krw':100000,'verified_api':False},
            {'title':'Pikachu PSA 10','price_kind':'API 현재가','price_krw':200000,'verified_api':True},
            {'title':'Pikachu PSA 10','price_kind':'판매중','price_krw':500000,'verified_api':True},
        ]
        row=next(x for x in m._grade_reference(items) if x['grade']=='PSA 10')
        self.assertEqual(row['price_krw'],100000)
        self.assertEqual(row['basis'],'완료거래')
        self.assertEqual(row['completed_count'],1)
        self.assertEqual(row['api_reference_count'],1)
        self.assertEqual(row['asking_count'],1)
        self.assertEqual(row['total_count'],3)
        chosen,basis=m._comparable_summary_items('Pikachu PSA 10',items)
        self.assertEqual([x['price_krw'] for x in chosen],[100000])
        self.assertEqual(basis,'PSA 10 · 완료거래')

    def test_grade_reference_uses_api_reference_before_asking_when_no_completed_sale(self):
        items=[
            {'title':'Pikachu PSA 9','price_kind':'API 현재가','price_krw':180000,'verified_api':True},
            {'title':'Pikachu PSA 9','price_kind':'판매중','price_krw':400000,'verified_api':True},
        ]
        row=next(x for x in m._grade_reference(items) if x['grade']=='PSA 9')
        self.assertEqual(row['price_krw'],180000)
        self.assertEqual(row['basis'],'API 참고시세')
        self.assertEqual(row['count'],1)


    def test_exact_numeric_grades_stay_separate_across_companies(self):
        items=[
            {'title':'Pikachu PSA 8 sold','price_kind':'실거래/완료 신호','price_krw':80000},
            {'title':'Pikachu PSA 7 sold','price_kind':'실거래/완료 신호','price_krw':70000},
            {'title':'Pikachu BGS 9.5 sold','price_kind':'실거래/완료 신호','price_krw':95000},
            {'title':'Pikachu CGC 10 sold','price_kind':'실거래/완료 신호','price_krw':110000},
            {'title':'Pikachu TAG 9 sold','price_kind':'실거래/완료 신호','price_krw':90000},
            {'title':'Pikachu BRG 8 sold','price_kind':'실거래/완료 신호','price_krw':81000},
        ]
        by_grade={row['grade']:row for row in m._grade_reference(items)}
        self.assertEqual(by_grade['PSA 8']['price_krw'],80000)
        self.assertEqual(by_grade['PSA 7']['price_krw'],70000)
        self.assertEqual(by_grade['BGS 9.5']['price_krw'],95000)
        self.assertEqual(by_grade['CGC 10']['price_krw'],110000)
        self.assertEqual(by_grade['TAG 9']['price_krw'],90000)
        self.assertEqual(by_grade['BRG 8']['price_krw'],81000)

    def test_grade_number_is_not_mistaken_for_card_number(self):
        for label in ('PSA 10','PSA 10.0','BGS 9.5','CGC 9.5','TAG 9.5','BRG 9.5','BGS:9.5'):
            with self.subTest(label=label):
                name,number=m._tcgdex_query_parts(f'Pikachu {label} English')
                self.assertEqual(number,'')
                self.assertEqual(name,'Pikachu')
        name,number=m._tcgdex_query_parts('Pikachu 025 BGS 9.5 English')
        self.assertEqual(m._normalize_card_number(number),'025')
        self.assertEqual(name,'Pikachu')
        name,number=m._tcgdex_query_parts('Pikachu PAL185/193 CGC 9.5 English')
        self.assertEqual(m._normalize_card_number(number),'PAL185/193')
        self.assertEqual(name,'Pikachu')

    def test_decimal_grade_fragments_never_become_listing_card_numbers(self):
        self.assertEqual(m._identity_blob_numbers('Pikachu BGS 9.5 sold'),[])
        self.assertEqual(m._identity_blob_numbers('Pikachu PSA 10.0 sold'),[])
        self.assertIn('005',m._identity_blob_numbers('Pikachu 005 BGS 9.5 sold'))
        listing={'title':'Pikachu BGS 9.5 sold','snippet':'Pikachu','price_krw':95000}
        eligible,basis=m._item_identity_eligibility('Pikachu 005',listing)
        self.assertFalse(eligible)
        self.assertEqual(basis,'card_number_mismatch')

    def test_summary_identity_gate_rejects_wrong_card_number(self):
        good={'title':'Pikachu PAL 185/193 sold','snippet':'Pikachu','card_number':'PAL185/193','price_krw':100000}
        wrong={'title':'Pikachu PAL 186/193 sold','snippet':'Pikachu','card_number':'PAL186/193','price_krw':90000}
        self.assertEqual(m._item_identity_eligibility('Pikachu PAL185/193',good)[0],True)
        self.assertEqual(m._item_identity_eligibility('Pikachu PAL185/193',wrong)[0],False)
        local_good={'title':'Pikachu card 025 sold','snippet':'Pikachu','price_krw':50000}
        local_wrong_name={'title':'Raichu card 025 sold','snippet':'Raichu','price_krw':50000}
        self.assertTrue(m._item_identity_eligibility('Pikachu 025',local_good)[0])
        self.assertFalse(m._item_identity_eligibility('Pikachu 025',local_wrong_name)[0])


    def test_trade_recommendation_balances_sources_and_keeps_lower_evidence_reference_only(self):
        items=[
            {'source':'Market A','source_id':'a','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':100000},
            {'source':'Market A','source_id':'a','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':110000},
            {'source':'Market A','source_id':'a','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':120000},
            {'source':'Market B','source_id':'b','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':200000},
            {'source':'Market C','source_id':'c','title':'Pikachu 025 listing','price_kind':'판매중','price_krw':900000},
        ]
        comparable,basis=m._comparable_summary_items('Pikachu 025',items)
        self.assertEqual(basis,'미감정 · 완료거래')
        recommendation=m._recommendation_from_comparable(comparable,basis)
        self.assertEqual(recommendation['recommended_trade_krw'],155000)
        self.assertEqual(recommendation['recommendation_min_krw'],100000)
        self.assertEqual(recommendation['recommendation_max_krw'],200000)
        self.assertEqual(recommendation['recommendation_source_count'],2)
        self.assertEqual(recommendation['recommendation_sample_count'],4)
        breakdown={row['source_id']:row for row in m._source_price_breakdown(items,'완료거래')}
        self.assertTrue(breakdown['a']['contributes_to_recommendation'])
        self.assertTrue(breakdown['b']['contributes_to_recommendation'])
        self.assertFalse(breakdown['c']['contributes_to_recommendation'])
        self.assertEqual(breakdown['a']['price_krw'],110000)
        self.assertEqual(breakdown['c']['basis'],'판매중/호가')

    def test_grade_reference_exposes_source_balanced_recommendation_and_prices(self):
        items=[
            {'source':'Sold A','source_id':'a','title':'Pikachu PSA 10 sold','price_kind':'실거래/완료 신호','price_krw':100000},
            {'source':'Sold A','source_id':'a','title':'Pikachu PSA 10 sold','price_kind':'실거래/완료 신호','price_krw':120000},
            {'source':'Sold B','source_id':'b','title':'Pikachu PSA 10 sold','price_kind':'실거래/완료 신호','price_krw':200000},
        ]
        row=next(x for x in m._grade_reference(items) if x['grade']=='PSA 10')
        self.assertEqual(row['recommended_trade_krw'],155000)
        self.assertEqual(row['recommendation_source_count'],2)
        self.assertEqual(row['recommendation_sample_count'],3)
        self.assertEqual(row['source_count'],2)
        self.assertEqual({x['source_id'] for x in row['sources']},{'a','b'})
        self.assertTrue(all(x['contributes_to_recommendation'] for x in row['sources']))

    def test_trade_recommendation_holds_when_no_comparable_price_exists(self):
        out=m._recommendation_from_comparable([], '카드번호/세트 식별자 필요')
        self.assertEqual(out['recommended_trade_krw'],0)
        self.assertEqual(out['recommendation_confidence'],'hold')
        self.assertEqual(out['recommendation_source_count'],0)

    def test_source_breakdown_never_mixes_raw_and_predicted_grade_basis(self):
        rows=[
            {'source':'Raw Sold','source_id':'raw','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':100000},
            {'source':'PSA Sold','source_id':'psa','title':'Pikachu 025 PSA 10 sold','price_kind':'실거래/완료 신호','price_krw':900000},
        ]
        raw=m._summary_basis_items('Pikachu 025',rows)
        psa=m._summary_basis_items('Pikachu 025 PSA 10',rows)
        self.assertEqual(['raw'],[x['source_id'] for x in raw])
        self.assertEqual(['psa'],[x['source_id'] for x in psa])
        raw_breakdown=m._source_price_breakdown(raw,'완료거래')
        self.assertEqual(['raw'],[x['source_id'] for x in raw_breakdown])
        self.assertEqual(100000,raw_breakdown[0]['price_krw'])

    def test_future_market_date_has_zero_confidence_not_fresh(self):
        state=m._item_price_freshness({'date':'2999-01-01','price_krw':1000})
        self.assertEqual('FUTURE',state['freshness_status'])
        self.assertIsNone(state['freshness_age_days'])
        self.assertEqual(0.0,state['freshness_confidence_cap'])
        current=m._item_price_freshness({'verified_api':True,'price_krw':1000})
        self.assertEqual('FRESH',current['freshness_status'])
        self.assertEqual(0,current['freshness_age_days'])

    def test_source_date_normalizes_rfc_and_verified_api_observation(self):
        self.assertEqual(
            m._source_date_iso({'date':'Wed, 07 Oct 2026 10:00:00 GMT'}),
            '2026-10-07',
        )
        state=m._item_price_freshness({'verified_api':True,'price_krw':1000})
        self.assertEqual(state['freshness_status'],'FRESH')
        self.assertEqual(state['freshness_age_days'],0)

    def test_recommendation_reports_current_and_unknown_date_sources(self):
        current=[
            {'source':'A','source_id':'a','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':100000,'verified_api':True},
            {'source':'B','source_id':'b','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':120000,'verified_api':True},
        ]
        out=m._recommendation_from_comparable(current,'미감정 · 완료거래')
        self.assertEqual(out['recommendation_freshness'],'최신')
        self.assertEqual(out['recommendation_current_source_count'],2)
        unknown=[
            {'source':'A','source_id':'a','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':100000},
            {'source':'B','source_id':'b','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':120000},
        ]
        held=m._recommendation_from_comparable(unknown,'미감정 · 완료거래')
        self.assertEqual(held['recommendation_freshness'],'날짜미확인')
        self.assertEqual(held['recommendation_confidence'],'낮음')

    def test_source_breakdown_exposes_freshness_for_user_verification(self):
        rows=[
            {'source':'API A','source_id':'a','title':'Pikachu 025','price_kind':'API 현재가','price_krw':100000,'verified_api':True},
            {'source':'Listing B','source_id':'b','title':'Pikachu 025','price_kind':'판매중','price_krw':120000,'date':'Wed, 07 Oct 2026 10:00:00 GMT'},
        ]
        by={row['source_id']:row for row in m._source_price_breakdown(rows,'API 참고시세')}
        self.assertIn('freshness_status',by['a'])
        self.assertIn('freshness_age_days',by['a'])
        self.assertEqual(by['a']['freshness_status'],'FRESH')
        self.assertEqual(by['b']['source_date'],'2026-10-07')


    def test_condition_and_printing_filters_fail_closed_on_unknown_or_mismatch(self):
        exact={'condition':'Near Mint','printing':'Holo','title':'Pikachu 025'}
        self.assertEqual(m._normalize_condition('Near Mint'),'NM')
        self.assertEqual(m._normalize_condition('Lightly Played'),'LP')
        self.assertEqual(m._market_filter_eligibility(exact,'NM','holo'),(True,'market_filter_match'))
        self.assertEqual(m._market_filter_eligibility(exact,'LP','holo')[1],'condition_mismatch')
        self.assertEqual(m._market_filter_eligibility(exact,'NM','reverse_holo')[1],'printing_mismatch')
        unknown={'title':'Pikachu 025'}
        self.assertEqual(m._market_filter_eligibility(unknown,'NM','ALL')[1],'condition_unknown')
        self.assertEqual(m._market_filter_eligibility(unknown,'ALL','holo')[1],'printing_unknown')

    def test_market_filter_query_suffix_is_bounded_and_semantic(self):
        self.assertEqual(m._market_filter_query_suffix('NM','reverse_holo'),'near mint reverse holo')
        self.assertEqual(m._market_filter_query_suffix('ALL','ALL'),'')
        self.assertEqual(m._market_filter_query_suffix('INVALID','INVALID'),'')

    def test_source_breakdown_preserves_seller_names_condition_and_printing(self):
        rows=[
            {'source':'eBay','source_id':'ebay','seller_name':'sellerA','title':'Pikachu 025 near mint holo','condition':'Near Mint','print_variant':'holo','price_kind':'판매중','price_krw':100000,'verified_api':True},
            {'source':'eBay','source_id':'ebay','seller_name':'sellerB','title':'Pikachu 025 near mint holo','condition':'NM','print_variant':'holo','price_kind':'판매중','price_krw':120000,'verified_api':True},
        ]
        out=m._source_price_breakdown(rows,'판매중/호가')[0]
        self.assertEqual(out['seller_count'],2)
        self.assertEqual(out['seller_names'],['sellerA','sellerB'])
        self.assertEqual(out['conditions'],['NM'])
        self.assertEqual(out['printings'],['holo'])

    def test_cache_key_separates_condition_and_printing_filters(self):
        base=m._cache_key('Pikachu 025','US','pokemon')
        nm=m._cache_key('Pikachu 025','US','pokemon','NM','holo')
        lp=m._cache_key('Pikachu 025','US','pokemon','LP','holo')
        self.assertNotEqual(base,nm)
        self.assertNotEqual(nm,lp)

    def test_evidence_source_breakdown_keeps_completed_api_and_asking_separate(self):
        rows=[
            {'source':'Market A','source_id':'a','seller_name':'soldA','title':'Pikachu 025 sold','price_kind':'실거래/완료 신호','price_krw':100000,'date':'2026-10-07'},
            {'source':'Market A','source_id':'a','seller_name':'apiA','title':'Pikachu 025','price_kind':'API 현재가','price_krw':120000,'verified_api':True},
            {'source':'Market A','source_id':'a','seller_name':'askA','title':'Pikachu 025 listing','price_kind':'판매중','price_krw':150000,'verified_api':True},
        ]
        out=m._source_evidence_breakdown(rows)
        by={row['evidence_class']:row for row in out}
        self.assertEqual(set(by),{'completed','api_reference','asking'})
        self.assertEqual(by['completed']['price_krw'],100000)
        self.assertEqual(by['api_reference']['price_krw'],120000)
        self.assertEqual(by['asking']['price_krw'],150000)
        self.assertEqual(by['asking']['seller_names'],['askA'])

if __name__=='__main__':
    unittest.main()
