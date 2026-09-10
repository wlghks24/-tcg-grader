import unittest
from copy import deepcopy
from pathlib import Path

import grading_costs_live as g


class GradingCostTests(unittest.TestCase):
    def test_all_five_companies_present(self):
        self.assertEqual(set(g.COMPANIES),{'PSA','BGS','CGC','TAG','BRG'})

    def test_official_sources_and_positive_fees(self):
        for name,c in g.COMPANIES.items():
            self.assertTrue(c['source'].startswith('https://'))
            self.assertTrue(c['services'])
            for s in c['services']:
                self.assertGreater(float(s['fee']),0)

    def test_variable_shipping_is_not_fabricated(self):
        for c in g.COMPANIES.values():
            self.assertIsInstance(c.get('shipping'),str)
            self.assertNotIn('fixed_fake',c.get('shipping',''))

    def test_known_fallback_fees_remain_available_when_watch_is_offline(self):
        by={k:{x['name']:x['fee'] for x in v['services']} for k,v in g.COMPANIES.items()}
        self.assertEqual(by['PSA']['Regular'],79.99)
        self.assertEqual(by['CGC']['Economy'],20.0)
        self.assertEqual(by['TAG']['Standard'],39.0)
        self.assertEqual(by['BRG']['Regular'],19800)

    def test_verified_watch_adds_new_service_and_keeps_japan_separate(self):
        companies=deepcopy(g.COMPANIES)
        watch={
            'companies':{
                'PSA':{
                    'markets':{
                        'US':{'currency':'USD','source':'https://www.psacard.com/services/tradingcardgrading','services':[
                            {'name':'Standard','fee':84.99,'currency':'USD','availability':'open','verified_official_source':True,
                             'source':'https://www.psacard.com/services/tradingcardgrading'}]},
                        'JP':{'currency':'JPY','source':'https://www.psacard.com/ja-JP/services/tradingcardgrading/grading','services':[
                            {'name':'Standard','fee':9980,'currency':'JPY','turnaround_business_days':100,'availability':'open',
                             'verified_official_source':True,'source':'https://www.psacard.com/ja-JP/services/tradingcardgrading/grading'}]},
                    },
                    'source_health':[{'source_id':'psa-jp-pricing','status':'ok'}],
                }
            },
            'history':[],
        }
        g._merge_watch(companies,watch)
        psa=companies['PSA']
        self.assertEqual(next(x for x in psa['services'] if x['name']=='Standard')['fee'],84.99)
        self.assertEqual(psa['regional_markets']['JP']['currency'],'JPY')
        self.assertEqual(psa['regional_markets']['JP']['services'][0]['fee'],9980)
        self.assertEqual(next(x for x in psa['services'] if x['name']=='Regular')['fee'],79.99)

    def test_only_explicit_verified_removal_retires_fallback_service(self):
        companies=deepcopy(g.COMPANIES)
        watch={'companies':{},'history':[
            {'company':'PSA','type':'service_removed','service':'Regular','verified_official_source':True}
        ]}
        g._merge_watch(companies,watch)
        regular=next(x for x in companies['PSA']['services'] if x['name']=='Regular')
        self.assertEqual(regular['availability'],'retired')

    def test_ui_has_jpy_change_history_and_static_pages_fallback(self):
        source=Path('grading_costs_live.js').read_text(encoding='utf-8')
        self.assertIn("c==='JPY'?jpy(n)",source)
        self.assertIn('/grading_company_updates.json?t=',source)
        self.assertIn('최근 요금·서비스 변경',source)
        self.assertIn('업체 이벤트·공지',source)
        self.assertIn("document.visibilityState==='visible'",source)


if __name__=='__main__':
    unittest.main()
