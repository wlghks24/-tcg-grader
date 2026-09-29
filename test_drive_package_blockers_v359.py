import datetime as dt
import urllib.error
import unittest

import collection_verification_gate as gate
import grading_company_watch as grading
import update_market_prices as market


class DrivePackageBlockersV359Tests(unittest.TestCase):
    def test_legacy_packmagik_kr_row_is_quarantined(self):
        key='KR|창해의 칠걸|HIT'
        db={'entries':{key:{'source':'https://www.packmagik.com/cards/op-op14-op14-009-p1','kind':'OP14-009 패러렐 국제판 참고시세','transactions':'한국판 실거래 아님 · 국제판 시장가 참고'}}}
        self.assertTrue(market.quarantine_legacy_packmagik_misjoin(db))
        self.assertNotIn(key,db['entries'])
        self.assertIn(key,db['invalid_entries_quarantine'])

    def test_packmagik_parser_miss_is_optional_warning_but_arbitrary_error_is_hard(self):
        self.assertTrue(market.market_error_is_warning('Pack Magik OP14-009 JP: 가격 패턴 0건'))
        self.assertTrue(market.market_error_is_warning('Pack Magik OP14-009 JP: HTTPError: status 403'))
        self.assertFalse(market.market_error_is_warning('BOX/HIT 다중마켓 자동발견: ValueError'))

    def test_bootstrap_is_bounded_official_and_exact_source(self):
        rows=grading._load_bootstrap_sources('2026-09-29T08:12:00+00:00')
        row=rows['psa-us-pricing']
        spec=grading.WATCH_SOURCES['PSA'][0]
        self.assertTrue(grading._valid_bootstrap_source('PSA',spec,'psa-us-pricing',row))
        self.assertEqual(row['url'],'https://www.psacard.com/services/tradingcardgrading')
        self.assertTrue(row['services'])
        self.assertEqual({},grading._load_bootstrap_sources('2026-11-01T00:00:00+00:00'))

    def test_psa_403_retains_bootstrap_as_degraded_not_healthy(self):
        def blocked(url):
            raise urllib.error.HTTPError(url,403,'blocked',None,None)
        data=grading.collect(previous={},fetcher=blocked)
        row=data['sources']['psa-us-pricing']
        self.assertEqual('degraded',row['status'])
        self.assertTrue(row['verified_official_source'])
        self.assertTrue(row['retained_last_good'])
        self.assertTrue(row['services'])
        self.assertIn('403',row['last_error'])

    def test_gate_allows_only_fresh_verified_blocked_last_good(self):
        now=dt.datetime(2026,9,29,8,12,tzinfo=dt.timezone.utc)
        base={
            'company':'PSA','status':'degraded','last_error':'HTTPError: status 403',
            'verified_official_source':False,'services':[],'announcements':[]
        }
        sources={
            'psa-us-pricing':dict(base,verified_official_source=True,retained_last_good=True,
                                  last_verified_at='2026-09-29T08:11:00+00:00',services=[{'name':'Regular'}]),
            'psa-jp-pricing':dict(base),
            'psa-jp-news':dict(base),
        }
        self.assertTrue(gate._grading_blocked_last_good_ok('PSA',sources,now))
        stale={k:dict(v) for k,v in sources.items()}
        stale['psa-us-pricing']['last_verified_at']='2026-08-01T00:00:00+00:00'
        self.assertFalse(gate._grading_blocked_last_good_ok('PSA',stale,now))
        parser_failure={k:dict(v) for k,v in sources.items()}
        parser_failure['psa-jp-pricing']['last_error']='ValueError: pricing parser yielded zero verified services'
        self.assertFalse(gate._grading_blocked_last_good_ok('PSA',parser_failure,now))


if __name__ == '__main__':
    unittest.main()
