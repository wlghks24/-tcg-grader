"""Regress false set-level pricing for the actual SV8a-217 Umbreon ex card."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
import update_market_prices as market

ROOT=Path(__file__).resolve().parent
OLD='JP|테라스탈 페스타 ex 일본판|HIT'
NEW='JP|블래키ex SAR [SV8a 217/187]|HIT'
URL='https://pokard.io/jpcard/SV8a-217/'

class PokardExactIdentityV523(unittest.TestCase):
    def test_legacy_snapshot_migrates_only_verified_source_without_price_or_date_rewrite(self):
        old={'source':URL,'display':'¥79,800','source_date':'2026-09-30','kind':'미감정 참고가격'}
        db={'entries':{OLD:old.copy()}}
        self.assertTrue(market.reconcile_known_pokard_card_identity(db))
        self.assertNotIn(OLD,db['entries'])
        row=db['entries'][NEW]
        self.assertEqual('SV8a-217',row['card_number'])
        self.assertEqual('JP',row['language'])
        self.assertEqual('SAR',row['variant'])
        self.assertEqual(old['display'],row['display'])
        self.assertEqual(old['source_date'],row['source_date'])

    def test_mismatch_does_not_transfer_unrelated_card_price(self):
        db={'entries':{OLD:{'source':'https://example.org/another-card','display':'¥9,999'}}}
        self.assertFalse(market.reconcile_known_pokard_card_identity(db))
        self.assertIn(OLD,db['entries'])
        self.assertNotIn(NEW,db['entries'])

    def test_existing_exact_card_observation_is_never_overwritten(self):
        exact={'source':URL,'display':'¥68,000','source_date':'2026-10-01'}
        db={'entries':{OLD:{'source':URL,'display':'¥79,800'},NEW:exact.copy()}}
        self.assertTrue(market.reconcile_known_pokard_card_identity(db))
        self.assertEqual(exact,db['entries'][NEW])
        self.assertNotIn(OLD,db['entries'])

    def test_kream_single_card_migrates_without_overwriting_value_or_date(self):
        source='https://kream.co.kr/products/959332'
        old='KR|테라스탈 페스타 ex|HIT'
        new='KR|블래키ex SAR [SV8A 217/187]|HIT'
        prior={'source':source,'display':'₩119,000','source_date':'2026-09-29'}
        rows={'entries':{old:prior.copy()}}
        self.assertTrue(market.reconcile_known_kream_card_identity(rows))
        self.assertNotIn(old,rows['entries'])
        now=rows['entries'][new]
        self.assertEqual(prior['display'],now['display'])
        self.assertEqual(prior['source_date'],now['source_date'])
        self.assertEqual('KR',now['language'])
        self.assertEqual('SV8A-217-187',now['card_number'])

    def test_kream_other_product_is_not_migrated(self):
        old='KR|테라스탈 페스타 ex|HIT'
        rows={'entries':{old:{'source':'https://kream.co.kr/products/other','display':'₩9,999'}}}
        self.assertFalse(market.reconcile_known_kream_card_identity(rows))
        self.assertIn(old,rows['entries'])

    def test_kream_newer_exact_card_price_is_not_replaced_by_legacy(self):
        old='KR|테라스탈 페스타 ex|HIT'
        new='KR|블래키ex SAR [SV8A 217/187]|HIT'
        exact={'source':'https://kream.co.kr/products/959332','display':'₩145,000'}
        rows={'entries':{old:{'source':exact['source'],'display':'₩119,000'},new:exact.copy()}}
        self.assertTrue(market.reconcile_known_kream_card_identity(rows))
        self.assertEqual(exact,rows['entries'][new])
        self.assertNotIn(old,rows['entries'])

    def test_korean_and_japanese_snapshots_do_not_coalesce(self):
        data=json.loads((ROOT/'market_prices.json').read_text(encoding='utf-8'))
        kr=data['entries']['KR|블래키ex SAR [SV8A 217/187]|HIT']
        jp=data['entries'][NEW]
        self.assertNotIn('KR|테라스탈 페스타 ex|HIT',data['entries'])
        self.assertEqual('KR',kr['language'])
        self.assertEqual('JP',jp['language'])
        self.assertEqual('https://kream.co.kr/products/959332',kr['source'])
        self.assertEqual(URL,jp['source'])
        self.assertEqual('SV8A-217-187',kr['card_number'])
        self.assertEqual('SV8a-217',jp['card_number'])
        self.assertNotEqual(kr['display'],jp['display'])

    def test_committed_market_snapshot_identifies_exact_card_without_fabricated_freshness(self):
        data=json.loads((ROOT/'market_prices.json').read_text(encoding='utf-8'))
        self.assertNotIn(OLD,data['entries'])
        row=data['entries'][NEW]
        for field,value in [('source',URL),('game','Pokémon'),('card_name','블래키ex'),
                            ('card_number','SV8a-217'),('language','JP'),('variant','SAR')]:
            self.assertEqual(value,row[field],field)
        self.assertRegex(row['source_date'],r'^20\\d{2}-\\d{2}-\\d{2}
        source=(ROOT/'update_market_prices.py').read_text(encoding='utf-8')
        self.assertIn("key='JP|블래키ex SAR [SV8a 217/187]|HIT'",source)
        self.assertIn('reconcile_known_pokard_card_identity(db)',source)

if __name__=='__main__': unittest.main()
)
        source=(ROOT/'update_market_prices.py').read_text(encoding='utf-8')
        self.assertIn("key='JP|블래키ex SAR [SV8a 217/187]|HIT'",source)
        self.assertIn('reconcile_known_pokard_card_identity(db)',source)

if __name__=='__main__': unittest.main()
