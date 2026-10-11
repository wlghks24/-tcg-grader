import unittest
from datetime import date
from market_price_context_v433 import CardPriceIdentity,price_context,price_freshness,scan_candidates,portfolio_position,price_history,price_alert,grading_expected_value,apply_scan_correction

class V433(unittest.TestCase):
 def history(self,rows,*,as_of=None,identity=None,currency="KRW"):
  # Synthesize reviewer declarations only for deterministic UNIT TESTS.
  # This does not create or certify real completed transactions.
  ident=identity or self.ident()
  data=[]
  for index,row in enumerate(rows):
   sale_id=f"ebay:{10000000000+index}"
   data.append({"identity_key":ident.key(),"card_name":ident.card_name,
       "currency":"KRW","evidence_type":"completed_sale",
       "verification_status":"verified","review_status":"manual_verified",
       "review_method":"source_page_crosscheck",
       "reviewed_at":(as_of or date(2026,10,9)).isoformat(),
       "transaction_finality":"sold","lineage_key":f"history-test-{index}",
       "sale_id":sale_id,"source":f"https://www.ebay.com/itm/{sale_id.split(':')[1]}",
       **row})
  return price_history(data,as_of=as_of,identity=ident,currency=currency)

 def ident(self,**kw):
  d=dict(game="Pokémon",card_name="Pikachu",card_number="001",set_name="Test",language="KR",condition="NM",printing="normal")
  d.update(kw);return CardPriceIdentity(**d)
 def test_identity_never_merges_condition_language_printing(self):
  a=self.ident();self.assertNotEqual(a.key(),self.ident(condition="LP").key());self.assertNotEqual(a.key(),self.ident(language="JP").key());self.assertNotEqual(a.key(),self.ident(printing="foil").key());self.assertNotEqual(a.key(),self.ident(card_name="Raichu").key())
  with self.assertRaises(ValueError):self.ident(card_name="Pika|chu").key()
  with self.assertRaises(ValueError):self.ident(card_name=["Pikachu"]).key()
 def test_two_lineage_fresh_price_can_verify(self):
  i=self.ident();common={"identity_key":i.key(),"card_name":i.card_name,"verification_status":"verified","review_status":"manual_verified","review_method":"source_page_crosscheck","reviewed_at":"2026-10-06","evidence_type":"completed_sale","transaction_finality":"sold","currency":"KRW"}
  rows=[{**common,"price":1000,"source_date":"2026-10-06","lineage_key":"a","sale_id":"ebay:12345678901","source":"https://www.ebay.com/itm/12345678901"},{**common,"price":1200,"source_date":"2026-10-05","lineage_key":"b","sale_id":"ebay:12345678902","source":"https://www.ebay.com/itm/12345678902"}]
  x=price_context(i,rows,today=date(2026,10,6));self.assertEqual("VERIFIED",x["status"]);self.assertEqual(1100,x["median_price"]);self.assertEqual(2,x["verified_evidence_count"])
 def test_unreviewed_quotes_do_not_become_verified_sales(self):
  i=self.ident();base={"identity_key":i.key(),"price":999,"source_date":"2026-10-06"}
  rows=[{**base,"lineage_key":"a","source":"https://www.ebay.com/itm/12345678901"},
        {**base,"lineage_key":"b","source":"https://www.ebay.com/itm/12345678902"}]
  x=price_context(i,rows,today=date(2026,10,6))
  self.assertEqual("PROVISIONAL",x["status"])
  self.assertEqual(0,x["verified_evidence_count"])
  self.assertEqual("unreviewed_reference",x["price_basis"])
  self.assertEqual("QUARANTINE",price_context(i,None,today=date(2026,10,6))["status"])

 def test_untrusted_or_duplicated_sale_source_cannot_fake_second_lineage(self):
  i=self.ident();base={"identity_key":i.key(),"price":100,"source_date":"2026-10-06",
                      "verification_status":"verified","evidence_type":"completed_sale","currency":"KRW",
                      "review_status":"manual_verified","review_method":"source_page_crosscheck",
                      "reviewed_at":"2026-10-06","transaction_finality":"sold","sale_id":"ebay:12345678901"}
  rows=[{**base,"lineage_key":"a","source":"https://www.ebay.com/itm/12345678901"},
        {**base,"lineage_key":"b","source":"https://www.ebay.com/itm/12345678901?tracking=1"},
        {**base,"lineage_key":"c","source":"http://www.ebay.com/itm/12345678902"},
        {**base,"lineage_key":"d","source":"https://user:password@www.ebay.com/itm/12345678903"},
        {**base,"lineage_key":"e","source":"https://localhost/itm/12345678904"},
        {**base,"lineage_key":"f","source":"https://www.ebay.com:8000/itm/12345678905"},
        {**base,"lineage_key":"g","source":"https://www.ebay.com/itm/12345678907","verification_status":[]},
        {**base,"lineage_key":"h","source":"https://www.ebay.com/itm/12345678908","evidence_type":{}}]
  result=price_context(i,rows,today=date(2026,10,6))
  self.assertEqual("PROVISIONAL",result["status"])
  self.assertEqual(1,result["verified_evidence_count"])
  self.assertEqual(100,result["median_price"])

 def test_missing_or_mismatched_card_name_never_merges_evidence(self):
  i=self.ident()
  other=self.ident(card_name="Raichu")
  self.assertNotEqual(i.key(),other.key())
  result=price_context(i,[{"identity_key":i.key(),"card_name":"Raichu","price":999,"source_date":"2026-10-06"}],today=date(2026,10,6))
  self.assertEqual("MISSING",result["status"])

 def test_reviewer_claim_without_fully_matched_sale_event_is_provisional(self):
  i=self.ident();base={"identity_key":i.key(),"price":1000,"currency":"KRW","source_date":"2026-10-06",
                       "verification_status":"verified","evidence_type":"completed_sale",
                       "source":"https://www.ebay.com/itm/12345678901","lineage_key":"a"}
  cases=[
   {**base,"review_status":"manual_verified"},
   {**base,"review_status":"manual_verified","review_method":"source_page_crosscheck"},
   {**base,"review_status":"manual_verified","review_method":"source_page_crosscheck","reviewed_at":"2026-10-06"},
   {**base,"review_status":"manual_verified","review_method":"source_page_crosscheck","reviewed_at":"2026-10-06","transaction_finality":"sold","sale_id":"ebay:99999999999"},
   {**base,"review_status":"manual_verified","review_method":"source_page_crosscheck","reviewed_at":"2026-10-05","transaction_finality":"sold","sale_id":"ebay:12345678901"},
  ]
  for row in cases:
   with self.subTest(row=row):
    got=price_context(i,[row],today=date(2026,10,6))
    self.assertEqual(0,got["verified_evidence_count"])
    self.assertEqual("PROVISIONAL",got["status"])

 def test_independent_currency_prices_do_not_mix(self):
  i=self.ident()
  rows=[{"identity_key":i.key(),"price":1400,"currency":"KRW","source_date":"2026-10-06"},
        {"identity_key":i.key(),"price":1.5,"currency":"USD","source_date":"2026-10-06"}]
  got=price_context(i,rows,today=date(2026,10,6))
  self.assertEqual("CURRENCY_CONFLICT",got["status"])
  self.assertIsNone(got["median_price"])
  self.assertEqual(["KRW","USD"],got["currencies"])
  self.assertEqual("UNKNOWN",price_context(i,[{"identity_key":i.key(),"price":500,"source_date":"2026-10-06"}],today=date(2026,10,6))["price_currency"])

 def test_reference_and_sale_are_not_one_transaction_population(self):
  i=self.ident()
  common={"identity_key":i.key(),"currency":"KRW","source_date":"2026-10-06",
          "verification_status":"verified","review_status":"manual_verified",
          "review_method":"source_page_crosscheck","reviewed_at":"2026-10-06"}
  rows=[{**common,"price":1000,"lineage_key":"sale","evidence_type":"completed_sale",
         "transaction_finality":"sold","sale_id":"ebay:12345678901","source":"https://www.ebay.com/itm/12345678901"},
        {**common,"price":99999,"lineage_key":"reference","evidence_type":"market_reference",
         "source":"https://www.tcgplayer.com/product/123456"}]
  got=price_context(i,rows,today=date(2026,10,6))
  self.assertEqual("PROVISIONAL",got["status"])
  self.assertEqual("reviewed_completed_sale",got["price_basis"])
  self.assertEqual(1000,got["median_price"])
  self.assertEqual(1,got["verified_evidence_count"])

 def test_wrong_variant_is_excluded(self):
  i=self.ident();self.assertEqual("MISSING",price_context(i,[{"identity_key":self.ident(condition="LP").key(),"price":999,"source_date":"2026-10-06"}],today=date(2026,10,6))["status"])
 def test_ambiguous_scan_requires_confirmation(self):
  x=scan_candidates([{"score":.81,"card_number":"1"},{"score":.77,"card_number":"2"}]);self.assertEqual("AMBIGUOUS",x["status"]);self.assertTrue(x["requires_user_confirmation"])
 def test_high_ocr_score_missing_variant_and_condition_still_requires_manual_review(self):
  high=scan_candidates([{"score":0.999,"game":"pokemon","card_name":"Pikachu",
                         "card_number":"025/165"}])
  self.assertEqual("MATCH",high["status"])
  self.assertFalse(high["match_verified"])
  self.assertTrue(high["requires_user_confirmation"])
  self.assertTrue(high["requires_variant_confirmation"])
  self.assertTrue(high["requires_condition_confirmation"])
  complete={"score":0.99,"game":"pokemon","card_name":"Pikachu",
            "card_number":"025/165","set_name":"151","language":"JP","printing":"normal"}
  still_condition=scan_candidates([complete])
  self.assertFalse(still_condition["requires_variant_confirmation"])
  self.assertTrue(still_condition["requires_condition_confirmation"])
  self.assertTrue(still_condition["requires_user_confirmation"])

 def test_duplicate_exact_scan_does_not_fabricate_second_card(self):
  first={"score":0.97,"game":"pokemon","card_name":"Pikachu","card_number":"025/165",
         "set_name":"151","language":"JP","printing":"normal","condition":"NM"}
  again={**first,"score":0.96,"card_name":" PIKACHU ","set_name":"１５１"}
  result=scan_candidates([first,again])
  self.assertEqual("MATCH",result["status"])
  self.assertEqual(1,result["duplicates_removed"])
  self.assertEqual(1,len(result["candidates"]))
  self.assertFalse(result["requires_user_confirmation"])
  self.assertFalse(result["match_verified"],"vision suggestion is not official card authentication")

 def test_same_art_parallel_or_set_stays_ambiguous_despite_high_score_gap(self):
  first={"score":0.99,"game":"onepiece","card_name":"Luffy","card_number":"OP01-001",
         "set_name":"OP01","language":"JP","printing":"normal","condition":"NM"}
  alternate={**first,"score":0.51,"printing":"parallel"}
  result=scan_candidates([first,alternate])
  self.assertEqual("AMBIGUOUS",result["status"])
  self.assertTrue(result["requires_variant_confirmation"])
  self.assertTrue(result["requires_user_confirmation"])
  self.assertEqual(2,len(result["candidates"]))
  rerun=scan_candidates([first,{**alternate,"set_name":"Different Set","printing":"normal"}])
  self.assertEqual("AMBIGUOUS",rerun["status"])

 def test_scan_rejects_invalid_batch_and_threshold_parameters(self):
  for batch,kwargs in (
    (None,{}),("not a candidate list",{}),([{}]*4097,{}),
    ([{"score":0.91}],{"minimum":True}),
    ([{"score":0.91}],{"minimum":float("nan")}),
    ([{"score":0.91}],{"ambiguity_margin":float("inf")}),
    ([{"score":0.91}],{"ambiguity_margin":2}),
  ):
   with self.subTest(batch=str(type(batch)),kwargs=kwargs):
    result=scan_candidates(batch,**kwargs)
    self.assertEqual("NO_MATCH",result["status"])
    self.assertTrue(result["requires_user_confirmation"])
    self.assertEqual("INVALID_OR_OVERSIZED_SCAN_INPUT",result["reason"])

 def test_missing_scan_correction_fields_are_quarantined_not_keyerror(self):
  result=apply_scan_correction({"game":"Pokémon","card_name":"Pikachu"},
                               {"language":"JP"})
  self.assertEqual("QUARANTINE",result["status"])
  self.assertTrue(any("MISSING" in err for err in result["errors"]))

 def test_portfolio_profit(self):
  x=portfolio_position(quantity=3,buy_unit=1000,current_unit=1500,sold_quantity=1,sold_unit=1800);self.assertEqual(1800,x["total_pnl"])
 def test_portfolio_requires_actual_sale_price(self):
  with self.assertRaisesRegex(ValueError,"sold_unit required"):
   portfolio_position(quantity=2,buy_unit=1000,current_unit=1500,sold_quantity=1)
  no_sale=portfolio_position(quantity=2,buy_unit=1000,current_unit=1500)
  self.assertEqual(0,no_sale["realized_pnl"])
  self.assertEqual(1000,no_sale["unrealized_pnl"])
  sold=portfolio_position(quantity=2,buy_unit=1000,current_unit=1500,sold_quantity=1,sold_unit=1600)
  self.assertEqual(600,sold["realized_pnl"])
  self.assertEqual(500,sold["unrealized_pnl"])
  self.assertEqual(1100,sold["total_pnl"])

 def test_portfolio_rejects_boolean_nonfinite_and_oversized_amounts(self):
  for kwargs in (
    {"quantity":True,"buy_unit":1,"current_unit":1},
    {"quantity":2.0,"buy_unit":1,"current_unit":1},
    {"quantity":1,"sold_quantity":True,"buy_unit":1,"current_unit":1},
    {"quantity":1,"sold_quantity":2,"buy_unit":1,"current_unit":1},
    {"quantity":1000001,"buy_unit":1,"current_unit":1},
    {"quantity":1,"buy_unit":float("nan"),"current_unit":1},
    {"quantity":1,"buy_unit":float("inf"),"current_unit":1},
    {"quantity":1,"buy_unit":1,"current_unit":float("inf")},
    {"quantity":1,"buy_unit":1,"current_unit":float("nan")},
    {"quantity":1,"sold_quantity":1,"sold_unit":False,"buy_unit":1,"current_unit":1},
    {"quantity":2,"buy_unit":1e308,"current_unit":1e308},
  ):
   with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
    portfolio_position(**kwargs)

 def test_grading_probabilities_must_be_complete_and_no_silent_normalization(self):
  base={"raw_price":100,"grade_prices":{"8":120,"9":150,"10":250},"grading_cost":10}
  for invalid in ({"9":0.2,"10":0.2},{"9":50,"10":50},
                  {"9":0.9,"10":0.9},{"9":float("nan"),"10":0.1},
                  {9:0.5,"10":0.5},{"9":0.5,"":0.5}):
   with self.subTest(invalid=invalid):
    self.assertEqual("MISSING",grading_expected_value(
      **base,grade_probabilities=invalid)["status"])
  missing_price=grading_expected_value(**base,grade_probabilities={"7":0.5,"10":0.5})
  self.assertEqual("GRADE_PRICE_REQUIRED",missing_price["reason"])
  hypothetical=grading_expected_value(**base,grade_probabilities={"9":0.5,"10":0.5})
  self.assertEqual("SCENARIO",hypothetical["status"])
  self.assertNotEqual("GRADE",hypothetical["recommendation"])

 def test_history_alert_verified_only(self):
  h=self.history([{"price":100,"source_date":"2026-09-06","verification_status":"verified"},{"price":130,"source_date":"2026-10-06","verification_status":"verified"},{"price":999,"source_date":"2026-10-06","verification_status":"unverified"}],as_of=date(2026,10,6))
  self.assertEqual(130,h["latest"]);self.assertEqual("SURGE",price_alert(h,pct_threshold=10)["status"])
 def test_grading_expected_value(self):
  x=grading_expected_value(raw_price=100,grade_probabilities={"9":.5,"10":.5},grade_prices={"9":120,"10":220},grading_cost=20)
  self.assertEqual("SCENARIO",x["status"]);self.assertEqual("REVIEW_GRADING",x["recommendation"])
  self.assertEqual("POSITIVE",x["economic_signal"]);self.assertEqual(50,x["incremental_value"])
  self.assertFalse(x["grade_probability_calibration_verified"])
  self.assertFalse(x["completed_sale_price_evidence_verified"])
 def test_market_date_only_default_uses_korean_business_day(self):
  from unittest.mock import patch
  from types import SimpleNamespace
  from datetime import datetime,timedelta
  def frozen_now(tz):
   self.assertEqual(timedelta(hours=9),tz.utcoffset(None))
   return datetime(2026,10,9,0,10,tzinfo=tz)
  with patch("market_price_context_v433.datetime",SimpleNamespace(now=frozen_now)):
   self.assertEqual("FRESH",price_freshness("2026-10-09")["status"])
   history=self.history([{"price":200,"source_date":"2026-10-09","verification_status":"verified"}])
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
  history=self.history(rows,as_of=today)
  self.assertEqual(1,len(history["series"]))
  self.assertTrue(all(value is None for value in history["windows"].values()))
  self.assertEqual("NO_SIGNAL",price_alert(history)["status"])
 def test_sparse_7d_30d_history_has_no_false_momentum(self):
  asof=date(2026,10,9)
  h=self.history([{"price":100,"source_date":"2026-10-08","verification_status":"verified"},{"price":200,"source_date":"2026-10-09","verification_status":"verified"}],as_of=asof)
  self.assertEqual("VERIFIED",h["status"])
  self.assertTrue(all(value is None for value in h["windows"].values()))
  self.assertEqual("NO_SIGNAL",price_alert(h)["status"])
 def test_window_baselines_require_correct_horizon(self):
  asof=date(2026,10,9)
  h=self.history([{"price":100,"source_date":"2026-10-02","verification_status":"verified"},{"price":200,"source_date":"2026-10-09","verification_status":"verified"}],as_of=asof)
  self.assertEqual(100.0,h["windows"]["7D"])
  self.assertIsNone(h["windows"]["30D"])
  stale=self.history([{"price":100,"source_date":"2026-09-29","verification_status":"verified"},{"price":200,"source_date":"2026-10-06","verification_status":"verified"}],as_of=asof)
  self.assertTrue(all(value is None for value in stale["windows"].values()))
 def test_history_requires_variant_and_currency_context(self):
  self.assertEqual("EXACT_IDENTITY_AND_CURRENCY_REQUIRED",price_history([])["reason"])
  self.assertEqual("MISSING",self.history([{"source_date":"2026-10-09","price":120,
       "identity_key":self.ident(card_name="Raichu").key()}],as_of=date(2026,10,9))["status"])
  x=self.history([{"source_date":"2026-10-09","price":120,"currency":"USD"}],as_of=date(2026,10,9))
  self.assertEqual("CURRENCY_CONFLICT",x["status"])
  self.assertEqual([],x["series"])
  self.assertEqual("CURRENCY_CONFLICT",self.history([{"source_date":"2026-10-09","price":120,
       "currency":None}],as_of=date(2026,10,9))["status"])
  self.assertEqual("INVALID_OR_OVERSIZED_HISTORY",price_history([{}]*5001,
       as_of=date(2026,10,9),identity=self.ident(),currency="KRW")["reason"])

 def test_history_rejects_unreviewed_and_reference_only_quotes(self):
  d=date(2026,10,9)
  result=self.history([{"source_date":"2026-10-09","price":180,"evidence_type":"api_reference"},
                       {"source_date":"2026-10-09","price":200,"review_status":"review_pending"},
                       {"source_date":"2026-10-09","price":500,"verification_status":"unverified"}],as_of=d)
  self.assertEqual("MISSING",result["status"])
  self.assertEqual("NO_SIGNAL",price_alert(result)["status"])

 def test_history_deduplicates_sale_id_across_observation_dates(self):
  asof=date(2026,10,9)
  a="ebay:12345678901"
  rows=[{"source_date":"2026-10-02","price":100,"sale_id":a,"source":"https://www.ebay.com/itm/12345678901"},
        {"source_date":"2026-10-09","price":9000,"sale_id":a,"source":"https://www.ebay.com/itm/12345678901?tracking=x"},
        {"source_date":"2026-10-09","price":120}]
  history=self.history(rows,as_of=asof)
  self.assertEqual(2,history["event_count"])
  self.assertEqual(120,history["latest"])
  self.assertEqual(20.0,history["windows"]["7D"])
  self.assertEqual([1,1],[point["samples"] for point in history["series"]])

 def test_history_reviewer_timestamp_must_precede_asof(self):
  d=date(2026,10,9)
  late=self.history([{"source_date":"2026-10-09","price":200,
       "reviewed_at":"2026-10-11"}],as_of=d)
  self.assertEqual("MISSING",late["status"])
  valid=self.history([{"source_date":"2026-10-09","price":200,
       "reviewed_at":"2026-10-09"}],as_of=d)
  self.assertEqual("VERIFIED",valid["status"])

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
  self.assertEqual("SCENARIO",calc()["status"])
 def test_scan_correction_is_explicit_and_validated(self):
  c={"game":"Pokémon","card_name":"Pikachu","card_number":"001","set_name":"Test","language":"KR","condition":"NM","printing":"normal","grader":"RAW","grade":"RAW"}
  x=apply_scan_correction(c,{"language":"JP"});self.assertEqual("CONFIRMED",x["status"]);self.assertIn("|JP|",x["identity_key"])
 def test_market_source_date_requires_exact_format_and_kst_offset(self):
  today=date(2026,10,9)
  for bad in ("2026-10-09junk","prefix2026-10-09","2026-10-09T12:30:00",
              "2026-02-31","2025-02-29","2026-10-09<script>",None,True):
   with self.subTest(bad=bad):
    self.assertEqual("UNKNOWN",price_freshness(bad,today=today)["status"])
  for valid in ("2026-10-09","2026-10-09T09:00:00+09:00",
                "2026-10-08T15:30:00Z","Thu, 08 Oct 2026 15:30:00 GMT"):
   with self.subTest(valid=valid):
    self.assertEqual("FRESH",price_freshness(valid,today=today)["status"])
  self.assertEqual("FUTURE",price_freshness("2026-10-10T00:00:00+09:00",today=today)["status"])
  self.assertEqual("FUTURE",price_freshness("2999-01-01",today=today)["status"])
  self.assertEqual("EXPIRED",price_freshness("1999-12-31",today=today)["status"])
  self.assertEqual("STALE",price_freshness("2026-09-29",today=today)["status"])

 def test_scan_boolean_confidence_never_beats_real_ocr_matches(self):
  rows=[{"score":True,"card_number":"forged"},{"score":0.84,"card_number":"verified"}]
  result=scan_candidates(rows)
  self.assertEqual("MATCH",result["status"])
  self.assertEqual("verified",result["candidates"][0]["card_number"])
  self.assertEqual("NO_MATCH",scan_candidates([{"score":False,"card_number":"bad"}])["status"])
  self.assertEqual("NO_MATCH",scan_candidates([{"score":float("nan"),"card_number":"bad"}])["status"])
  enormous=10**500
  self.assertEqual("NO_MATCH",scan_candidates([{"score":enormous,"card_number":"forged"}])["status"])
  ranked=scan_candidates([{"score":enormous,"card_number":"forged"},{"score":0.91,"card_number":"real"}])
  self.assertEqual("real",ranked["candidates"][0]["card_number"])

 def test_price_history_rejects_forged_date_prefixes_and_bad_prices(self):
  items=[{"price":100,"source_date":"2026-10-09fake","verification_status":"verified"},
         {"price":True,"source_date":"2026-10-09","verification_status":"verified"},
         {"price":120,"source_date":"2026-10-09T01:00:00Z","verification_status":"verified"}]
  result=self.history(items,as_of=date(2026,10,9))
  self.assertEqual(1,len(result["series"]))
  self.assertEqual(120,result["latest"])
  self.assertTrue(all(val is None for val in result["windows"].values()))

if __name__=="__main__":unittest.main()
