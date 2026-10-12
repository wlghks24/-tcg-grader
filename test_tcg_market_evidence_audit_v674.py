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

    def test_bad_prices_and_missing_grade_rejected(self):
        report=audit_prices([row(reported_amount="NaN"),row(reported_amount="-1"),
            row(grade_service="PSA",grade=None)])
        self.assertEqual(3,report["rejected_count"])

if __name__=="__main__":
    unittest.main()
