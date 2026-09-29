import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import collection_verification_gate_contextual as contextual
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

    def _write_fixture(self, root: Path, *, observed='2026-09-29T08:11:00+00:00', expires='2026-10-06T08:11:00+00:00', errors=None):
        services=[{'name':'Standard','fee_usd':59.99,'availability':'open'}]
        canonical=json.dumps(services,ensure_ascii=False,sort_keys=True,separators=(',',':'))
        proof={
            'schema_version':1,'provider':'PSA','source_id':'psa-us-pricing',
            'source_url':'https://www.psacard.com/services/tradingcardgrading',
            'observed_at':observed,'expires_at':expires,
            'facts_sha256':hashlib.sha256(canonical.encode()).hexdigest(),'services':services,
            'policy':{'official_source_only':True,'runtime_block_stays_degraded':True,'bypass_blocked_source':False,'max_age_seconds':604800,'not_injected_into_grading_company_updates':True},
        }
        (root/'provider_last_good_official.json').write_text(json.dumps(proof),encoding='utf-8')
        errs=errors or ['HTTPError: status 403','HTTPError: status 403','HTTPError: status 403']
        sources={}
        for source_id,error in zip(('psa-us-pricing','psa-jp-pricing','psa-jp-news'),errs):
            sources[source_id]={'company':'PSA','status':'degraded','url':'https://www.psacard.com/services/tradingcardgrading','last_error':error,'services':[],'verified_official_source':False}
        (root/'grading_company_updates.json').write_text(json.dumps({'sources':sources}),encoding='utf-8')

    def test_recent_external_proof_downgrades_only_hard_block_to_medium(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root)
            finding={'severity':'high','code':'GRADING_COMPANY_NO_HEALTHY_SOURCE','companies':['PSA'],'degraded_samples_by_company':{'PSA':[]},'degraded_sample_counts_by_company':{'PSA':3}}
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,9,29,9,tzinfo=dt.timezone.utc))
            self.assertEqual(1,len(proofs)); self.assertEqual('medium',rows[0]['severity'])
            self.assertEqual('degraded',proofs[0]['runtime_status']); self.assertFalse(proofs[0]['bypass_attempted'])

    def test_expired_or_nonblocked_provider_stays_high(self):
        finding={'severity':'high','code':'GRADING_COMPANY_NO_HEALTHY_SOURCE','companies':['PSA'],'degraded_samples_by_company':{'PSA':[]},'degraded_sample_counts_by_company':{'PSA':3}}
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root)
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,10,6,8,11,1,tzinfo=dt.timezone.utc))
            self.assertFalse(proofs); self.assertEqual('high',rows[0]['severity'])
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root,errors=['HTTPError: status 403','ValueError: parser changed','HTTPError: status 403'])
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,9,29,9,tzinfo=dt.timezone.utc))
            self.assertFalse(proofs); self.assertEqual('high',rows[0]['severity'])

    def test_tampered_proof_stays_high(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); self._write_fixture(root)
            proof=json.loads((root/'provider_last_good_official.json').read_text())
            proof['services'][0]['fee_usd']=1.0
            (root/'provider_last_good_official.json').write_text(json.dumps(proof))
            finding={'severity':'high','code':'GRADING_COMPANY_NO_HEALTHY_SOURCE','companies':['PSA'],'degraded_samples_by_company':{'PSA':[]},'degraded_sample_counts_by_company':{'PSA':3}}
            rows,proofs=contextual._contextualize_blocked_provider(root,finding,dt.datetime(2026,9,29,9,tzinfo=dt.timezone.utc))
            self.assertFalse(proofs); self.assertEqual('high',rows[0]['severity'])


if __name__ == '__main__':
    unittest.main()
