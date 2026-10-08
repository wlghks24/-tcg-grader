import unittest
from datetime import date
from market_price_context_v433 import CardPriceIdentity,price_context,price_freshness,scan_candidates,portfolio_position,price_history,price_alert,grading_expected_value,apply_scan_correction

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
 def test_history_alert_verified_only(self):
  h=price_history([{"price":100,"source_date":"2026-09-06","verification_status":"verified"},{"price":130,"source_date":"2026-10-06","verification_status":"verified"},{"price":999,"source_date":"2026-10-06","verification_status":"unverified"}],as_of=date(2026,10,6))
  self.assertEqual(130,h["latest"]);self.assertEqual("SURGE",price_alert(h,pct_threshold=10)["status"])
 def test_grading_expected_value(self):
  x=grading_expected_value(raw_price=100,grade_probabilities={"9":.5,"10":.5},grade_prices={"9":120,"10":220},grading_cost=20)
  self.assertEqual("GRADE",x["recommendation"]);self.assertEqual(50,x["incremental_value"])
 def test_market_date_only_default_uses_korean_business_day(self):
  from unittest.mock import patch
  from types import SimpleNamespace
  from datetime import datetime,timedelta
  def frozen_now(tz):
   self.assertEqual(timedelta(hours=9),tz.utcoffset(None))
   return datetime(2026,10,9,0,10,tzinfo=tz)
  with patch("market_price_context_v433.datetime",SimpleNamespace(now=frozen_now)):
   self.assertEqual("FRESH",price_freshness("2026-10-09")["status"])
   history=price_history([{"price":200,"source_date":"2026-10-09","verification_status":"verified"}])
   self.assertEqual("2026-10-09",history["series"][-1]["date"])
 def test_future_market_observation_never_looks_fresh(self):
  today=date(2026,10,9)
  future=price_freshness("2026-10-10",today=today)
  self.assertEqual("FUTURE",future["status"])
  self.assertIsNone(future["age_days"])
  self.assertEqual(0.0,future["confidence_cap"])
  self.assertEqual("FRESH",price_freshness("2026-10-09",today=today)["status"])
  self.assertEqual("UNKNOWN",price_freshness("not-a-date",today=today)["status"])
 def test_future_and_nonfinite_market_rows_are_excluded_from_price(self):
  i=self.ident();today=date(2026,10,9)
  rows=[
   {"identity_key":i.key(),"price":1000,"source_date":"2026-10-09","lineage_key":"genuine"},
   {"identity_key":i.key(),"price":999999,"source_date":"2026-10-10","lineage_key":"future"},
   {"identity_key":i.key(),"price":float("inf"),"source_date":"2026-10-09","lineage_key":"infinite"},
   {"identity_key":i.key(),"price":float("nan"),"source_date":"2026-10-09","lineage_key":"nan"},
   {"identity_key":i.key(),"price":True,"source_date":"2026-10-09","lineage_key":"boolean"},
  ]
  market=price_context(i,rows,today=today)
  self.assertEqual(1,market["evidence_count"])
  self.assertEqual(1000,market["median_price"])
  self.assertEqual("PROVISIONAL",market["status"])
  self.assertEqual("MISSING",price_context(i,rows[1:],today=today)["status"])
 def test_price_history_needs_two_valid_days_for_momentum(self):
  today=date(2026,10,9)
  rows=[
   {"price":200,"source_date":"2026-10-09","verification_status":"verified"},
   {"price":float("inf"),"source_date":"2026-10-08","verification_status":"verified"},
   {"price":float("nan"),"source_date":"2026-10-08","verification_status":"verified"},
   {"price":999,"source_date":"2026-10-10","verification_status":"verified"},
  ]
  history=price_history(rows,as_of=today)
  self.assertEqual(1,len(history["series"]))
  self.assertTrue(all(value is None for value in history["windows"].values()))
  self.assertEqual("NO_SIGNAL",price_alert(history)["status"])
 def test_sparse_7d_30d_history_has_no_false_momentum(self):
  asof=date(2026,10,9)
  h=price_history([{"price":100,"source_date":"2026-10-08","verification_status":"verified"},{"price":200,"source_date":"2026-10-09","verification_status":"verified"}],as_of=asof)
  self.assertEqual("VERIFIED",h["status"])
  self.assertTrue(all(value is None for value in h["windows"].values()))
  self.assertEqual("NO_SIGNAL",price_alert(h)["status"])
 def test_window_baselines_require_correct_horizon(self):
  asof=date(2026,10,9)
  h=price_history([{"price":100,"source_date":"2026-10-02","verification_status":"verified"},{"price":200,"source_date":"2026-10-09","verification_status":"verified"}],as_of=asof)
  self.assertEqual(100.0,h["windows"]["7D"])
  self.assertIsNone(h["windows"]["30D"])
  stale=price_history([{"price":100,"source_date":"2026-09-29","verification_status":"verified"},{"price":200,"source_date":"2026-10-06","verification_status":"verified"}],as_of=asof)
  self.assertTrue(all(value is None for value in stale["windows"].values()))
 def test_grading_economics_never_recommends_from_nonfinite_inputs(self):
  def calc(**overrides):
   args=dict(raw_price=100,grade_probabilities={"9":0.5,"10":0.5},grade_prices={"9":150,"10":250},grading_cost=10)
   args.update(overrides)
   return grading_expected_value(**args)
  for bad in (float("nan"),float("inf"),True):
   with self.assertRaises(ValueError):calc(raw_price=bad)
   with self.assertRaises(ValueError):calc(grading_cost=bad)
  with self.assertRaises(ValueError):calc(selling_fee_rate=float("nan"))
  self.assertEqual("MISSING",calc(grade_probabilities={"9":float("inf")})["status"])
  self.assertEqual("MISSING",calc(grade_probabilities={"9":True})["status"])
  self.assertEqual("MISSING",calc(grade_prices={"9":float("inf"),"10":250})["status"])
  self.assertEqual("GRADE_PRICE_REQUIRED",calc(grade_prices={"9":float("nan"),"10":250})["reason"])
  self.assertEqual("VERIFIED",calc()["status"])
 def test_scan_correction_is_explicit_and_validated(self):
  c={"game":"Pokémon","card_name":"Pikachu","card_number":"001","set_name":"Test","language":"KR","condition":"NM","printing":"normal","grader":"RAW","grade":"RAW"}
  x=apply_scan_correction(c,{"language":"JP"});self.assertEqual("CONFIRMED",x["status"]);self.assertIn("|JP|",x["identity_key"])
if __name__=="__main__":unittest.main()
