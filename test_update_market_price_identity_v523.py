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

    def test_committed_market_snapshot_identifies_exact_card_without_fabricated_freshness(self):
        data=json.loads((ROOT/'market_prices.json').read_text(encoding='utf-8'))
        self.assertNotIn(OLD,data['entries'])
        row=data['entries'][NEW]
        for field,value in [('source',URL),('game','Pokémon'),('card_name','블래키ex'),
                            ('card_number','SV8a-217'),('language','JP'),('variant','SAR')]:
            self.assertEqual(value,row[field],field)
        self.assertEqual('2026-09-30',row['source_date'])
        source=(ROOT/'update_market_prices.py').read_text(encoding='utf-8')
        self.assertIn("key='JP|블래키ex SAR [SV8a 217/187]|HIT'",source)
        self.assertIn('reconcile_known_pokard_card_identity(db)',source)

if __name__=='__main__': unittest.main()
