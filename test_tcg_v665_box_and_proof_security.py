#!/usr/bin/env python3
"""V665: offline BOX manufacturer proof and strict unknown-field firewall regression."""
import copy
import shutil
import subprocess
import unittest
from execution.official_box_coverage_audit_v623 import ROOT,CoverageError,_load_json
from tcg_official_overlay_v657 import validate_overlay
from tcg_official_overlay_v659 import validate_additions
from tcg_official_overlay_v662 import validate_v662
from tcg_official_overlay_v663 import validate_v663,validate_promo
from tcg_official_overlay_v665 import validate_v665,build
from tcg_source_audit_v633 import plan

NODE=shutil.which("node")
def load(x):return _load_json(ROOT/x)

class V665UnionArenaSourceProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=load("tcg_game_registry.json")
        cls.intake=load("tcg_user_research_intake_v625.json")
        cls.base=load("tcg_official_product_catalog_v599.json")
        cls.s=[load("tcg_official_product_supplement_v"+str(n)+".json")
               for n in (630,636,637,649,654,657,659,662,663,665)]
        cls.promo=load("tcg_official_promo_evidence_v663.json")

    def test_japanese_box_101_products_64_boxes_19_scopes_missing(self):
        result=build()
        self.assertEqual((100,63,20),tuple(result["prior"][x] for x in ("products","boxes","box_gaps")))
        self.assertEqual((101,64,55,36,19),
            tuple(result["with_v665"][x] for x in ("products","boxes","declared_scopes","box_scopes","box_gaps")))
        self.assertEqual(0,result["network_calls"])
        old=plan(self.reg,self.intake,self.base,*self.s[:-1],self.promo)
        new=plan(self.reg,self.intake,self.base,*self.s[:-1],self.promo,self.s[-1])
        self.assertEqual((100,63,20),tuple(old[k] for k in
            ("official_product_samples","official_sealed_box_samples","declared_sealed_box_spec_gaps")))
        self.assertEqual((101,64,19),tuple(new[k] for k in
            ("official_product_samples","official_sealed_box_samples","declared_sealed_box_spec_gaps")))

    def test_inuyasha_exact_release_and_pack_not_hit(self):
        p=validate_v665(self.s[-1],self.reg)[0]
        self.assertEqual(("JP","UA50BT","2026-05-29",16,"8"),
            (p["country"],p["set_code"],p["release_date"],p["packs_per_box"],p["cards_per_pack"]))
        self.assertNotIn("msrp",p)
        for field,value in (("packs_per_box",20),("cards_per_pack","9"),
                 ("source","https://www.unionarena-tcg.com.attacker.example/"),
                 ("unverified_price_guess",4999),("hit_probability",0.5),
                 ("release_date","2027-01-01")):
            with self.subTest(field=field):
                malicious=copy.deepcopy(self.s[-1])
                malicious["products"][0][field]=value
                with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V665_BOX_SPEC"):
                    validate_v665(malicious,self.reg)

    def test_prior_manufacturer_proofs_reject_unknown_market_fields(self):
        validators=[
            (validate_overlay,self.s[5],"UNSUPPORTED_V657_PRODUCT_CLAIM"),
            (validate_additions,self.s[6],"UNTRUSTED_V659_IDENTITY"),
            (validate_v662,self.s[7],"UNTRUSTED_V662_PRODUCT"),
        ]
        for verify,source,reason in validators:
            with self.subTest(stage=reason):
                malicious=copy.deepcopy(source)
                malicious["products"][0]["unverified_price_guess"]=10000
                with self.assertRaisesRegex(CoverageError,reason):
                    verify(malicious,self.reg)
        corrupted=copy.deepcopy(self.s[5])
        corrupted["products"][0]["name"]="Counterfeit Booster Display"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V657_IDENTITY"):
            validate_overlay(corrupted,self.reg)

    def test_promo_is_not_card_no_or_hitrate(self):
        verified=validate_promo(self.promo)
        self.assertEqual(3,len(verified))
        self.assertTrue(all(row["card_number"] is None for row in verified))

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_node_manual_crosslanguage_101_64_19_and_field_denials(self):
        js=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json'),leads=require('./tcg_user_research_intake_v625.json');
const base=require('./tcg_official_product_catalog_v599.json');
const p=[630,636,637,649,654,657,659,662,663,665].map(n=>require('./tcg_official_product_supplement_v'+n+'.json'));
const promo=require('./tcg_official_promo_evidence_v663.json');
const official=require('./official_box_catalog_v626.js');
const research=require('./tcg_source_research_v634.js');
const radar=require('./tcg_coverage_radar_v652.js');
const old=research.build(reg,leads,base,...p.slice(0,6),official,p[6],p[7],p[8],promo);
const now=research.build(reg,leads,base,...p.slice(0,6),official,p[6],p[7],p[8],promo,p[9]);
assert.deepEqual([old.summary.official,old.summary.officialBoxes,old.summary.boxMissing],[100,63,20]);
assert.deepEqual([now.summary.official,now.summary.officialBoxes,now.summary.boxMissing],[101,64,19]);
const r=radar.build(reg,leads,base,...p.slice(0,4),{research,official},
require('./tcg_region_lifecycle_v653.json'),p[4],p[5],p[6],p[7],p[8],promo,p[9]);
assert.deepEqual([r.official_product_samples,r.official_box_samples,r.declared_box_gaps,r.manual_search_tasks],
[101,64,19,540]);
const fake=structuredClone(p[9]);fake.products[0].unverified_price_guess=10000;
assert.throws(()=>official.validateV665(fake,[]),/UNTRUSTED_V665_PRODUCT/);
const oldFake=structuredClone(p[5]);oldFake.products[0].unverified_price_guess=5;
assert.throws(()=>official.validateV657(oldFake,[]),/UNTRUSTED_V657_PRODUCT/);
"""
        out=subprocess.run([NODE,"-e",js],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(0,out.returncode,out.stderr)

if __name__=="__main__":
    unittest.main(verbosity=2)
