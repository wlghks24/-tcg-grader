#!/usr/bin/env python3
"""V655 security QA: prevent forged official counts on every collector surface."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from execution.official_box_coverage_audit_v623 import CoverageError
from tcg_source_audit_v633 import plan

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")


class FreeSourceCountsV655(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        read=lambda name:json.loads((ROOT/name).read_text(encoding="utf-8"))
        cls.reg=read("tcg_game_registry.json")
        cls.intake=read("tcg_user_research_intake_v625.json")
        cls.base=read("tcg_official_product_catalog_v599.json")
        cls.s630=read("tcg_official_product_supplement_v630.json")
        cls.s636=read("tcg_official_product_supplement_v636.json")
        cls.s637=read("tcg_official_product_supplement_v637.json")
        cls.s649=read("tcg_official_product_supplement_v649.json")
        cls.s654=read("tcg_official_product_supplement_v654.json")

    def test_python_local_report_91_verified_sources(self):
        result=plan(self.reg,self.intake,self.base,self.s630,
                    self.s636,self.s637,self.s649,self.s654)
        self.assertEqual(91,result["official_product_samples"])
        self.assertEqual(54,result["official_sealed_box_samples"])
        self.assertEqual(29,result["declared_sealed_box_spec_gaps"])
        self.assertEqual(19,result["declared_official_sample_gaps"])
        self.assertTrue(all(r["price_evidence"]=="NONE" for r in result["scopes"]))

    def test_python_rejects_spoofed_hosts_and_fake_box_quantities(self):
        forged=copy.deepcopy(self.s654)
        forged["products"][0]["source"]="https://cf-vanguard.com.attacker.example/box"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE"):
            plan(self.reg,self.intake,self.base,self.s630,
                 self.s636,self.s637,self.s649,forged)
        wrong=copy.deepcopy(self.s654)
        wrong["products"][0]["packs_per_box"]=0
        with self.assertRaisesRegex(CoverageError,"BOX_PACK_COUNT_REQUIRED"):
            plan(self.reg,self.intake,self.base,self.s630,
                 self.s636,self.s637,self.s649,wrong)
        mistaken=copy.deepcopy(self.s654)
        mistaken["products"][0]["product_type"]="BOOSTER_PACK"
        with self.assertRaisesRegex(CoverageError,"PACK_IS_NOT_BOX"):
            plan(self.reg,self.intake,self.base,self.s630,
                 self.s636,self.s637,self.s649,mistaken)

    def test_official_supplement_chain_invalid_detected(self):
        forged=copy.deepcopy(self.s654)
        forged["append_after"]="unrelated-v999.json"
        with self.assertRaisesRegex(ValueError,"INVALID_V654_SUPPLEMENT"):
            plan(self.reg,self.intake,self.base,self.s630,self.s636,self.s637,self.s649,forged)

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_browser_30_game_counts_exclude_spoofed_product(self):
        script=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json');
const app=require('./tcg_30_game_catalog_v629.js');
const official=require('./official_box_catalog_v626.js');
const files=['tcg_official_product_catalog_v599.json',
 'tcg_official_product_supplement_v630.json',
 'tcg_official_product_supplement_v636.json',
 'tcg_official_product_supplement_v637.json',
 'tcg_official_product_supplement_v649.json',
 'tcg_official_product_supplement_v654.json'];
const all=files.flatMap(name=>require('./'+name).products);
assert.equal(all.length,91);
const total=counts=>Object.values(counts).reduce((a,b)=>a+b,0);
const original=app.officialCounts({schema_version:1,products:all},reg,official);
assert.equal(total(original),91);
assert.equal(Object.keys(original).length,30);
const forged=structuredClone(all);
forged.at(-1).source='https://yu-gi-oh.jp.attacker.example/products';
const safe=app.officialCounts({schema_version:1,products:forged},reg,official);
assert.equal(total(safe),90);
const wrong=structuredClone(all);
wrong.at(-1).product_type='BOOSTER_PACK';
assert.equal(total(app.officialCounts({schema_version:1,products:wrong},reg,official)),90);
const html=require('node:fs').readFileSync('./tcg_30_game_catalog_v629.html','utf8');
assert.ok(html.indexOf('official_box_catalog_v626.js')<
          html.indexOf('tcg_30_game_catalog_v629.js'));
"""
        r=subprocess.run([NODE,"-e",script],cwd=ROOT,capture_output=True,text=True,
                         check=False,timeout=25)
        self.assertEqual(0,r.returncode,r.stderr)


if __name__=="__main__":
    unittest.main(verbosity=2)
