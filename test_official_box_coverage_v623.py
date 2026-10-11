#!/usr/bin/env python3
"""V623 official BOX/pack coverage audit: fake marketplace data must never fill gaps."""
import copy
from datetime import date
import json
from pathlib import Path
import unittest

from execution.official_box_coverage_audit_v623 import CoverageError, audit

ROOT = Path(__file__).resolve().parent


class OfficialBoxCoverageV623(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=json.loads((ROOT/'tcg_game_registry.json').read_text(encoding='utf-8'))
        cls.catalog=json.loads((ROOT/'tcg_official_product_catalog_v599.json').read_text(encoding='utf-8'))

    def test_actual_official_snapshot_coverage_is_reported_not_invented(self):
        report=audit(self.registry,self.catalog,as_of=date(2026,10,12))
        self.assertEqual(30,report['registry_games'])
        self.assertEqual(21,report['reviewed_official_product_records'])
        self.assertEqual(55,report['declared_game_country_pairs'])
        self.assertEqual(5,report['pairs_with_any_official_product'])
        self.assertEqual(50,report['game_country_product_coverage_gaps'])
        self.assertEqual(90,len(report['cells']))
        self.assertIn('OFFLINE_SNAPSHOT_ONLY_NOT_LIVE_CRAWL',report['limitations'])
        self.assertIn('MISSING_FROM_LOCAL_CATALOG_DOES_NOT_MEAN_NO_PRODUCT_EXISTS',report['limitations'])

    def test_known_pokemon_boxes_and_gundam_packs_stay_distinct(self):
        rows={(r['game_id'],r['country']):r for r in audit(self.registry,self.catalog)['cells']}
        pk=rows['pokemon','KR']
        self.assertEqual((5,0,5),(pk['official_box_count'],pk['official_booster_pack_count'],pk['official_product_count']))
        self.assertEqual('OFFICIAL_PRODUCT_SAMPLE_PRESENT',pk['status'])
        gd=rows['gundam','US']
        self.assertEqual(0,gd['official_box_count'])
        self.assertEqual(5,gd['official_booster_pack_count'])
        self.assertIn('SEALED_BOX_SPEC_NOT_YET_REVIEWED',gd['missing'])
        self.assertEqual('NOT_DECLARED_FOR_GAME',rows['gundam','KR']['status'])

    def test_core_naruto_gaps_are_explicit_and_no_live_stock_pretended(self):
        rows=[r for r in audit(self.registry,self.catalog)['cells'] if r['game_id']=='naruto']
        self.assertEqual({'KR','JP','US'},{r['country'] for r in rows})
        self.assertTrue(all(r['status']=='OFFICIAL_PRODUCT_COVERAGE_GAP' for r in rows))
        self.assertTrue(all('COMPLETED_SALE' in r['noncatalog_evidence_not_audited'] for r in rows))
        self.assertTrue(all('LIVE_STOCK' in r['noncatalog_evidence_not_audited'] for r in rows))
        self.assertTrue(all('HIT_IDENTITY' in r['noncatalog_evidence_not_audited'] for r in rows))

    def test_same_id_or_exact_variant_collision_rejected(self):
        data=copy.deepcopy(self.catalog)
        data['products'].append(copy.deepcopy(data['products'][0]))
        with self.assertRaisesRegex(CoverageError,'DUPLICATE_OFFICIAL_PRODUCT_ID'):
            audit(self.registry,data)
        data=copy.deepcopy(self.catalog)
        cloned=copy.deepcopy(data['products'][0]);cloned['id']='other-safe-id'
        data['products'].append(cloned)
        with self.assertRaisesRegex(CoverageError,'DUPLICATE_OFFICIAL_PRODUCT_VARIANT'):
            audit(self.registry,data)

    def test_wrong_source_and_impersonation_and_price_rejected(self):
        for source in ('http://pokemoncard.co.kr/card/960','https://evil.example/card/960',
                       'https://pokemoncard.co.kr.evil.example/card/960',
                       'https://user:secret@pokemoncard.co.kr/card/960'):
            data=copy.deepcopy(self.catalog)
            row=next(x for x in data['products'] if x['id']=='pk-KR-30TH-2026')
            row['source']=source
            with self.subTest(source=source),self.assertRaisesRegex(
                CoverageError,'UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE'):
                audit(self.registry,data)

    def test_box_and_pack_metadata_cannot_be_confused(self):
        data=copy.deepcopy(self.catalog)
        row=next(x for x in data['products'] if x['id']=='gd-EB01')
        row['packs_per_box']=24
        with self.assertRaisesRegex(CoverageError,'PACK_IS_NOT_BOX'):
            audit(self.registry,data)
        data=copy.deepcopy(self.catalog)
        row=next(x for x in data['products'] if x['id']=='pk-KR-30TH-2026')
        del row['packs_per_box']
        with self.assertRaisesRegex(CoverageError,'BOX_PACK_COUNT_REQUIRED'):
            audit(self.registry,data)

    def test_msrp_wrong_currency_sale_price_and_pull_rate_rejected(self):
        for field,value,message in (
            ('msrp',{'currency':'USD','amount':70000,'unit':'BOX'},'INVALID_MSRP_CURRENCY_OR_UNIT'),
            ('msrp',{'currency':'KRW','amount':True,'unit':'BOX'},'INVALID_MSRP_AMOUNT'),
            ('verified_sales',12,'UNSUPPORTED_MARKET_OR_GRADE_CLAIM'),
            ('pull_rate',0.2,'UNSUPPORTED_MARKET_OR_GRADE_CLAIM'),
            ('verified_stock',True,'UNSUPPORTED_MARKET_OR_GRADE_CLAIM'),
        ):
            data=copy.deepcopy(self.catalog)
            row=next(x for x in data['products'] if x['id']=='pk-KR-30TH-2026')
            row[field]=value
            with self.subTest(field=field,value=value),self.assertRaisesRegex(CoverageError,message):
                audit(self.registry,data)

    def test_missing_release_date_only_allowed_for_prerelease_box(self):
        data=copy.deepcopy(self.catalog)
        row=next(x for x in data['products'] if x['id']=='gd-EB01')
        row['release_date']=''
        with self.assertRaisesRegex(CoverageError,'MISSING_PRODUCT_RELEASE_DATE'):
            audit(self.registry,data)
        data=copy.deepcopy(self.catalog)
        row=next(x for x in data['products'] if x['id']=='swu-HOMEWORLDS-pre')
        self.assertEqual('',row['release_date'])
        self.assertEqual('PARTIAL_OFFICIAL_PRODUCT_COVERAGE',audit(self.registry,data)['status'])

    def test_different_language_region_not_silently_promoted(self):
        data=copy.deepcopy(self.catalog)
        row=next(x for x in data['products'] if x['id']=='gd-EB01')
        row['country']='KR'
        with self.assertRaisesRegex(CoverageError,'PRODUCT_COUNTRY_OUTSIDE_GAME_REGION'):
            audit(self.registry,data)

    def test_invalid_game_and_missing_registry_are_errors(self):
        bad=copy.deepcopy(self.registry)
        bad['games'][0]['id']=bad['games'][1]['id']
        with self.assertRaisesRegex(CoverageError,'DUPLICATE_GAME'):
            audit(bad,self.catalog)
        with self.assertRaisesRegex(CoverageError,'INVALID_GAME_REGISTRY'):
            audit({},self.catalog)

if __name__=='__main__':
    unittest.main(verbosity=2)
