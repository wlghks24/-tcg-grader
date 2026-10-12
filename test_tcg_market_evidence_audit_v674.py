#!/usr/bin/env python3
import unittest
from tcg_market_evidence_audit_v674 import audit_prices, classify

def row(**changes):
    base = dict(game_id="digimon", market="US", card_number="BT25-001",
        printing="BASE", condition="NM", grade_service="RAW", grade=None,
        reported_currency="USD", reported_amount="10",
        source_type="SALE_LISTING", evidence_status="USER_SUPPLIED_UNVERIFIED")
    base.update(changes)
    return base

class V674Tests(unittest.TestCase):
    def test_listing_and_completed_claim_never_mix(self):
        report=audit_prices([row(),row(source_type="COMPLETED_SALE_CLAIM",reported_amount="100")])
        self.assertEqual(2,len(report["groups"]))
        self.assertEqual(0,report["independently_verified_sale_count"])
        self.assertTrue(all(not g["eligible_for_public_price_index"] for g in report["groups"]))

    def test_country_printing_and_grade_are_separate(self):
        report=audit_prices([row(),row(market="JP",reported_currency="JPY"),
            row(printing="ALT_ART"),row(grade_service="PSA",condition="UNSPECIFIED",grade="9")])
        self.assertEqual(4,len(report["groups"]))

    def test_fake_verified_claim_is_rejected(self):
        report=audit_prices([row(evidence_status="INDEPENDENTLY_SETTLED_VERIFIED")])
        self.assertEqual(1,report["rejected_count"])
        self.assertEqual([],report["groups"])

    def test_currency_mismatch_and_price_limits_rejected(self):
        report=audit_prices([row(market="JP",reported_currency="USD"),
            row(reported_amount="1000000001"),row(reported_amount="1.001"),
            row(grade_service="FAKE")])
        self.assertEqual(4,report["rejected_count"])
        self.assertEqual([],report["groups"])

    def test_grade_and_condition_spoof_rejected(self):
        report=audit_prices([row(grade_service="PSA",condition="NM",grade="9"),
            row(grade_service="PSA",condition="UNSPECIFIED",grade="11"),
            row(grade_service="PSA",condition="UNSPECIFIED",grade="NaN"),
            row(grade_service="RAW",condition="UNKNOWN")])
        self.assertEqual(4,report["rejected_count"])
        self.assertEqual([],report["groups"])

    def test_duplicate_source_not_assumed_verified(self):
        report=audit_prices([row(),row()])
        self.assertEqual(0,report["independently_verified_sale_count"])
        self.assertFalse(report["groups"][0]["eligible_for_public_price_index"])

    def test_bad_prices_and_missing_grade_rejected(self):
        report=audit_prices([row(reported_amount="NaN"),row(reported_amount="-1"),
            row(grade_service="PSA",grade=None)])
        self.assertEqual(3,report["rejected_count"])

    def test_buy_offer_ask_and_completed_claim_never_mix(self):
        report=audit_prices([row(source_type="STORE_BUY_OFFER",reported_amount="5"),
            row(source_type="SALE_LISTING",reported_amount="30"),
            row(source_type="COMPLETED_SALE_CLAIM",reported_amount="40")])
        self.assertEqual(3,len(report["groups"]))
        self.assertEqual(
            {"UNVERIFIED_STORE_BUY_OFFER","UNVERIFIED_SALE_LISTING","UNVERIFIED_COMPLETED_CLAIM"},
            {g["evidence_class"] for g in report["groups"]})
        self.assertEqual({"5","30","40"},{g["observed_median"] for g in report["groups"]})
        self.assertEqual(0,report["independently_verified_sale_count"])

    def test_unhashable_and_missing_identities_fail_closed(self):
        bad=[row(game_id=[]),row(card_number={"fake":1}),row(printing=["ALT"]),
             row(condition={}),row(grade_service=[]),row(reported_currency=["USD"]),
             row(game_id=""),row(card_number=" BT25-001"),row(game_id="a"+chr(10)+"b"),
             row(grade_service="RAW",grade=0),
             row(grade_service="PSA",condition="UNSPECIFIED",grade={})]
        report=audit_prices(bad+[row(reported_amount="7")])
        self.assertEqual(len(bad),report["rejected_count"])
        self.assertEqual(1,len(report["groups"]))
        self.assertEqual("7",report["groups"][0]["observed_median"])

    def test_grade_strings_normalize_to_same_group(self):
        report=audit_prices([
            row(grade_service="PSA",condition="UNSPECIFIED",grade="9",reported_amount="90"),
            row(grade_service="PSA",condition="UNSPECIFIED",grade="9.0",reported_amount="110")])
        self.assertEqual(1,len(report["groups"]))
        self.assertEqual("9",report["groups"][0]["identity"]["grade"])
        self.assertEqual("100",report["groups"][0]["observed_median"])
        self.assertFalse(report["groups"][0]["eligible_for_public_price_index"])

    def test_identical_unsourced_rows_not_inflate_sample(self):
        report=audit_prices([row(),row(),row(reported_amount="20")])
        self.assertEqual(1,report["duplicate_count"])
        self.assertEqual(2,report["groups"][0]["sample_count"])
        self.assertEqual("15",report["groups"][0]["observed_median"])
        self.assertEqual(0,report["independently_verified_sale_count"])

    def test_conflicting_prices_from_one_source_quarantined(self):
        url="https://example.com/item/card-123"
        report=audit_prices([
            row(source_url=url,reported_amount="10"),
            row(source_url=url,reported_amount="100"),
            row(source_url="https://example.org/item/456",reported_amount="20")])
        self.assertEqual(1,report["conflicting_source_count"])
        self.assertEqual(1,report["groups"][0]["sample_count"])
        self.assertEqual("20",report["groups"][0]["observed_median"])
        self.assertFalse(report["groups"][0]["eligible_for_public_price_index"])

    def test_untrusted_source_url_rejected(self):
        report=audit_prices([
            row(source_url="http://example.com/a"),row(source_url="https://user@example.com/a"),
            row(source_url="https://127.0.0.1/a"),row(source_url="https://example.com/a#frag"),
            row(source_url=[]),row(source_url="https://example.com@attacker.test/p"),
            row(source_url="https://example.org/valid",reported_amount="8")])
        self.assertEqual(6,report["rejected_count"])
        self.assertEqual("8",report["groups"][0]["observed_median"])

    def test_bounds_and_bool_amount(self):
        with self.assertRaisesRegex(ValueError,"INVALID_RECORD_COLLECTION"):
            audit_prices(None)
        with self.assertRaisesRegex(ValueError,"TOO_MANY_MARKET_RECORDS"):
            audit_prices([row()] * 10001)
        report=audit_prices([row(reported_amount=True),row(reported_amount="4")])
        self.assertEqual(1,report["rejected_count"])
        self.assertEqual("4",report["groups"][0]["observed_median"])

    def test_tracking_parameters_cannot_multiply_source(self):
        report=audit_prices([
            row(source_url="https://example.org/item/10?utm_source=social",reported_amount="10"),
            row(source_url="https://example.org/item/10?gclid=click",reported_amount="10"),
            row(source_url="https://example.org/item/10?variant=foil",reported_amount="20")])
        self.assertEqual(1,report["duplicate_count"])
        self.assertEqual(2,report["groups"][0]["sample_count"])
        self.assertEqual("15",report["groups"][0]["observed_median"])

    def test_deterministic_malformed_record_fuzz_stays_private(self):
        import random
        rng=random.Random(20261013)
        keys=("game_id","market","card_number","printing","condition",
              "grade_service","grade","reported_currency","reported_amount",
              "source_type","evidence_status","source_url")
        junk=(None, [], {}, True, False, 0, 7, "NaN", "", "\\x00",
              "https://127.0.0.1/a", "https://user@example.org/a", "USD",
              "JP", "NM", "PSA", "RAW", "SALE_LISTING", "COMPLETED_SALE_CLAIM")
        for _ in range(500):
            candidate=row()
            for _ in range(rng.randrange(1,4)):
                candidate[rng.choice(keys)]=rng.choice(junk)
            report=audit_prices([candidate])
            self.assertEqual(0,report["independently_verified_sale_count"])
            self.assertEqual(0,report["network_calls"])
            self.assertEqual(0,report["paid_dependencies"])
            self.assertTrue(all(not g["eligible_for_public_price_index"]
                                for g in report["groups"]))

if __name__=="__main__":
    unittest.main()
