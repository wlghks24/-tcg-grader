#!/usr/bin/env python3
"""V659/V660 cross-check Japanese sealed BOX and manufacturer card-trade evidence."""
from __future__ import annotations
import copy
import csv
from datetime import date
import io
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from execution.official_box_coverage_audit_v623 import ROOT, CoverageError, _load_json
from tcg_official_overlay_v659 import build as box_build,validate_additions
from tcg_card_trade_evidence_v660 import (
    official_card_records,stage_csv,CSV_FIELDS
)
from tcg_source_audit_v633 import plan
NODE=shutil.which("node")
def load(name): return _load_json(ROOT/name)

class V659V660Crosscheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=load("tcg_game_registry.json")
        cls.intake=load("tcg_user_research_intake_v625.json")
        cls.base=load("tcg_official_product_catalog_v599.json")
        cls.docs=[load("tcg_official_product_supplement_v"+v+".json")
                  for v in ("630","636","637","649","654","657","659")]
        cls.cards=load("tcg_manufacturer_card_evidence_v660.json")

    def test_2_japanese_manufacturer_box_gaps_resolved_additively(self):
        proof=box_build()
        self.assertEqual((94,57,26),
          (proof["pre_v659"]["products"],proof["pre_v659"]["sealed_boxes"],proof["pre_v659"]["box_gaps"]))
        self.assertEqual((96,59,24),
          (proof["with_v659"]["products"],proof["with_v659"]["sealed_boxes"],proof["with_v659"]["box_gaps"]))
        self.assertEqual(31,proof["with_v659"]["scopes_with_box"])
        self.assertEqual(55,proof["with_v659"]["declared_market_scopes"])
        self.assertEqual(0,proof["network_calls"])
        self.assertTrue(proof["no_paid_dependency"])
        verified=validate_additions(self.docs[-1],self.reg)
        self.assertEqual({("pokemon-JP-SV9a-2025",30,"5"),("onepiece-JP-OP13-2025",24,"6")},
                         {(x["id"],x["packs_per_box"],x["cards_per_pack"]) for x in verified})

    def test_python_queue_and_market_scope_audit_match(self):
        report=plan(self.reg,self.intake,self.base,*self.docs)
        self.assertEqual((96,59,24),(
            report["official_product_samples"],
            report["official_sealed_box_samples"],
            report["declared_sealed_box_spec_gaps"]))
        self.assertEqual(90,report["market_search_scopes"])
        self.assertEqual(338,sum(report[k] for k in ("product_candidate_count","upcoming_candidate_count",
                                                     "hit_candidate_count","promo_candidate_count")))
        self.assertTrue(all(row["price_evidence"]=="NONE" for row in report["scopes"]))

    def test_invalid_manufacturer_host_identity_and_chain_rejected(self):
        v=copy.deepcopy(self.docs[-1])
        v["products"][1]["source"]="https://cp.onepiece-cardgame.com.attacker.example/festa"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V659_IDENTITY"):
            validate_additions(v,self.reg)
        v=copy.deepcopy(self.docs[-1])
        v["products"][0]["name"]="Fake booster name"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V659_IDENTITY"):
            validate_additions(v,self.reg)
        v=copy.deepcopy(self.docs[-1])
        v["products"][0]["cards_per_pack"]="10"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V659_IDENTITY"):
            validate_additions(v,self.reg)
        v=copy.deepcopy(self.docs[-1])
        v["append_after"]="fake.json"
        with self.assertRaisesRegex(CoverageError,"INVALID_V659_SUPPLEMENT"):
            validate_additions(v,self.reg)

    def test_card_identity_examples_and_paper_sale_not_verified(self):
        records=official_card_records(self.cards)
        self.assertEqual(3,len(records))
        self.assertEqual("ALT_ART",records["digimon-US-BT25-020-alt"]["printing"])
        self.assertEqual("SR",records["digimon-US-BT25-020-alt"]["rarity"])
        self.assertIsNone(records["onepiece-JP-OP13-001"]["rarity"])
        output=io.StringIO()
        writer=csv.DictWriter(output,fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(dict(card_ref="digimon-US-BT25-020-alt",market="US",
            source_type="COMPLETED_SALE_CLAIM",source_url="https://example.com/sold/123",
            observed_at="2026-10-10",currency="USD",amount="15.99",condition="UNSPECIFIED",
            grade_service="PSA",grade="9"))
        writer.writerow(dict(card_ref="digimon-US-BT25-020-alt",market="JP",
            source_type="SALE_LISTING",source_url="https://example.com/list/123",
            observed_at="2026-10-10",currency="JPY",amount="1200",condition="NM",
            grade_service="RAW",grade=""))
        report=stage_csv(output.getvalue(),self.cards,as_of=date(2026,10,12))
        self.assertEqual((1,1,0),(report["accepted_count"],report["rejected_count"],
                               report["verified_sale_count"]))
        self.assertEqual("COUNTRY_EDITION_MISMATCH",report["rejected"][0]["reason"])
        self.assertFalse(report["accepted"][0]["is_completed_sale_verified"])
        self.assertFalse(report["accepted"][0]["eligible_for_public_price_index"])

    def test_identity_spoof_and_grade_mismatch_not_published(self):
        corrupted=copy.deepcopy(self.cards)
        corrupted["records"][0]["game"]="Wrong manufacturer"
        with self.assertRaises(ValueError):
            official_card_records(corrupted)
        corrupted=copy.deepcopy(self.cards)
        corrupted["records"][0]["source_url"]="https://world.digimoncard.com.evil.test/cards/"
        with self.assertRaises(ValueError):
            official_card_records(corrupted)
        columns=",".join(CSV_FIELDS)
        raw="digimon-US-BT25-001-regular,US,SALE_LISTING,https://example.com/offer,2026-10-10,USD,8,NM,RAW,9"
        data=stage_csv(columns+"\n"+raw,self.cards,as_of=date(2026,10,12))
        self.assertEqual(0,data["accepted_count"])
        self.assertEqual("RAW_WITH_GRADE",data["rejected"][0]["reason"])

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_node_same_box_totals_and_fake_host(self):
        script=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const base=require('./tcg_official_product_catalog_v599.json');
const parts=['630','636','637','649','654','657','659'].map(n=>require('./tcg_official_product_supplement_v'+n+'.json'));
const official=require('./official_box_catalog_v626.js');
const research=require('./tcg_source_research_v634.js');
const radar=require('./tcg_coverage_radar_v652.js');
const history=require('./tcg_region_lifecycle_v653.json');
const full=research.build(reg,intake,base,...parts.slice(0,6),official,parts[6]);
assert.deepEqual([full.summary.official,full.summary.officialBoxes,full.summary.boxMissing],[96,59,24]);
const old=research.build(reg,intake,base,...parts.slice(0,6),official);
assert.equal(old.summary.official,94);
const view=radar.build(reg,intake,base,...parts.slice(0,4),{research,official},history,
                       parts[4],parts[5],parts[6]);
assert.deepEqual([view.official_product_samples,view.official_box_samples,view.declared_box_gaps],[96,59,24]);
const fake=structuredClone(parts[6]);
fake.products[0].source='https://www.pokemon-card.com.bad.example/fake';
assert.throws(()=>official.validateV659(fake,[]),/UNTRUSTED_V659_PRODUCT/);
"""
        proc=subprocess.run([NODE,"-e",script],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,proc.returncode,proc.stderr)

if __name__=="__main__": unittest.main(verbosity=2)
