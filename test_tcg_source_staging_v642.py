#!/usr/bin/env python3
"""V642 evidence staging QA: zero-promotion, legal source identity, CSV hygiene."""
import csv
from datetime import date, datetime, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import tcg_multi_source_queue_v639 as q
import tcg_source_staging_v642 as stage


class V642EvidenceStagingQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue=q.build_queue()["jobs"]
        cls.pokemon=next(x for x in cls.queue if x["game_id"]=="pokemon" and x["market"]=="KR")
        cls.wixoss=next(x for x in cls.queue if x["game_id"]=="wixoss" and x["market"]=="JP")

    def csv_text(self, rows):
        buf=io.StringIO()
        writer=csv.DictWriter(buf,fieldnames=stage.REQUIRED)
        writer.writeheader()
        for row in rows:writer.writerow(row)
        return buf.getvalue()

    def row(self,job,**changes):
        result={"task_id":job["task_id"],"source_url":"https://pokemoncard.co.kr/products/",
                "source_type":"manufacturer","observed_at":"2026-10-11",
                "amount":"","currency":""}
        result.update(changes)
        return result

    def test_kst_midnight_accepts_same_day_proof_on_utc_runner(self):
        self.assertEqual(date(2026,10,13),stage.current_kst_day(
            datetime(2026,10,12,16,0,tzinfo=timezone.utc)))
        self.assertEqual(date(2026,10,12),stage.current_kst_day(
            datetime(2026,10,12,14,59,tzinfo=timezone.utc)))
        with self.assertRaisesRegex(ValueError,"AWARE_TIMESTAMP_REQUIRED"):
            stage.current_kst_day(datetime(2026,10,12,16,0))
        proof=self.row(self.pokemon,observed_at="2026-10-13")
        with patch.object(stage,"current_kst_day",return_value=date(2026,10,13)):
            report=stage.stage_csv(self.csv_text([proof]),
                jobs_by_id={self.pokemon["task_id"]:self.pokemon})
        self.assertEqual(1,report["accepted_count"])
        self.assertFalse(report["accepted"][0]["is_official_product_verified"])
        old=stage.stage_csv(self.csv_text([proof]),today=date(2026,10,12),
            jobs_by_id={self.pokemon["task_id"]:self.pokemon})
        self.assertEqual("FUTURE_OBSERVATION",old["rejected"][0]["reason"])

    def test_valid_manufacturer_source_stays_unverified_even_on_allowlist(self):
        result=stage.stage_csv(self.csv_text([self.row(self.pokemon)]),
                               today=date(2026,10,12))
        self.assertEqual((1,0),(result["accepted_count"],result["rejected_count"]))
        proof=result["accepted"][0]
        self.assertTrue(proof["manufacturer_host_on_allowlist"])
        self.assertFalse(proof["manual_approval"])
        self.assertFalse(proof["is_official_product_verified"])
        self.assertFalse(proof["is_completed_sale_verified"])
        self.assertEqual("USER_SUPPLIED_UNVERIFIED_LINK",proof["evidence_level"])
        self.assertEqual(self.pokemon["canonical_game"],"Pokémon")

    def test_manufacturer_phishing_not_promoted(self):
        row=self.row(self.pokemon,source_url="https://pokemoncard.co.kr.attacker.example/box")
        output=stage.stage_csv(self.csv_text([row]),today=date(2026,10,12))
        self.assertEqual(1,output["accepted_count"])
        self.assertFalse(output["accepted"][0]["manufacturer_host_on_allowlist"])
        self.assertEqual("MANUFACTURER_DOMAIN_REVIEW_REQUIRED",
                         output["accepted"][0]["validation_status"])
        self.assertFalse(output["accepted"][0]["manual_approval"])

    def test_price_type_region_and_duplicate_ids(self):
        row=self.row(self.pokemon,source_url="https://store.example/buy",source_type="store_buy_offer",
                     amount="12,000",currency="KRW")
        output=stage.stage_csv(self.csv_text([row,row]),today=date(2026,10,12))
        self.assertEqual(1,output["accepted_count"])
        self.assertEqual(0,output["rejected_count"])
        self.assertEqual("12000",output["accepted"][0]["reported_amount"])
        self.assertFalse(output["accepted"][0]["is_completed_sale_verified"])
        wrong=self.row(self.pokemon,source_url="https://store.example/buy",
                       source_type="store_buy_offer",amount="100",currency="USD")
        err=stage.stage_csv(self.csv_text([wrong]),today=date(2026,10,12))
        self.assertEqual("CURRENCY_MARKET_MISMATCH",err["rejected"][0]["reason"])

    def test_reject_unsafe_urls_invalid_tasks_and_future_dates(self):
        rows=[
            self.row(self.pokemon,source_url="http://no-tls.example/a"),
            self.row(self.pokemon,source_url="https://127.0.0.1/a"),
            self.row(self.pokemon,source_url="https://a.example:6000/a"),
            self.row(self.pokemon,task_id="00000000000000000000"),
            self.row(self.pokemon,observed_at="2027-01-01"),
            self.row(self.pokemon,amount="0",currency="KRW"),
            self.row(self.pokemon,amount="1.999",currency="KRW"),
        ]
        report=stage.stage_csv(self.csv_text(rows),today=date(2026,10,12))
        self.assertEqual(0,report["accepted_count"])
        self.assertEqual(7,report["rejected_count"])
        self.assertEqual("UNKNOWN_TASK_ID",report["rejected"][3]["reason"])
        self.assertEqual("FUTURE_OBSERVATION",report["rejected"][4]["reason"])

    def test_no_csv_formula_override_of_identity_and_no_auto_sales_verification(self):
        row=self.row(self.wixoss,source_url="https://market.example/item/123",
                     source_type="completed_sale",amount="1350",currency="JPY")
        out=stage.stage_csv(self.csv_text([row]),today=date(2026,10,12))
        self.assertEqual(1,out["accepted_count"])
        proof=out["accepted"][0]
        self.assertEqual(self.wixoss["game_id"],proof["game_id"])
        self.assertEqual(self.wixoss["kind"],proof["kind"])
        self.assertFalse(proof["is_completed_sale_verified"])
        self.assertFalse(proof["manual_approval"])
        self.assertNotIn("HIT_RATE",out["policy"])

    def test_cacheless_atomic_staging_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination=Path(tmp)/"staged.json"
            data=stage.stage_csv(self.csv_text([self.row(self.pokemon)]),
                                 today=date(2026,10,12))
            stage.save_new(destination,data)
            self.assertTrue(destination.is_file())
            with self.assertRaises(ValueError):
                stage.save_new(destination,data)
            with self.assertRaises(ValueError):
                stage.save_new(Path(tmp)/"danger.py",data)
            self.assertEqual(1,len(list(Path(tmp).glob("*.json"))))


if __name__=="__main__":
    unittest.main(verbosity=2)
