import unittest
from datetime import date
from market_price_context_v433 import CardPriceIdentity,price_context,scan_candidates,portfolio_position

class V433(unittest.TestCase):
 def ident(self,**kw):
  d=dict(game="Pokémon",card_name="Pikachu",card_number="001",set_name="Test",language="KR",condition="NM",printing="normal")
  d.update(kw);return CardPriceIdentity(**d)
 def test_identity_never_merges_condition_language_printing(self):
  a=self.ident();self.assertNotEqual(a.key(),self.ident(condition="LP").key());self.assertNotEqual(a.key(),self.ident(language="JP").key());self.assertNotEqual(a.key(),self.ident(printing="foil").key())
 def test_two_lineage_fresh_price_can_verify(self):
  i=self.ident(); rows=[{"identity_key":i.key(),"price":1000,"source_date":"2026-10-06","lineage_key":"a"},{"identity_key":i.key(),"price":1200,"source_date":"2026-10-05","lineage_key":"b"}]
  x=price_context(i,rows,today=date(2026,10,6));self.assertEqual("VERIFIED",x["status"]);self.assertEqual(1100,x["median_price"])
 def test_wrong_variant_is_excluded(self):
  i=self.ident();self.assertEqual("MISSING",price_context(i,[{"identity_key":self.ident(condition="LP").key(),"price":999,"source_date":"2026-10-06"}],today=date(2026,10,6))["status"])
 def test_ambiguous_scan_requires_confirmation(self):
  x=scan_candidates([{"score":.81,"card_number":"1"},{"score":.77,"card_number":"2"}]);self.assertEqual("AMBIGUOUS",x["status"]);self.assertTrue(x["requires_user_confirmation"])
 def test_portfolio_profit(self):
  x=portfolio_position(quantity=3,buy_unit=1000,current_unit=1500,sold_quantity=1,sold_unit=1800);self.assertEqual(1800,x["total_pnl"])
if __name__=="__main__":unittest.main()
