#!/usr/bin/env python3
"""V652/V653: cross-category 30-game gap radar and retired-edition safety."""
from pathlib import Path
import json
import shutil
import subprocess
import unittest
from datetime import date

ROOT=Path(__file__).resolve().parent
NODE=shutil.which("node")


class FreeCoverageRadarV652(unittest.TestCase):
    def test_official_lifecycle_is_explicit_not_a_registry_deletion(self):
        registry=json.loads((ROOT/"tcg_game_registry.json").read_text(encoding="utf-8"))
        caveat=json.loads((ROOT/"tcg_region_lifecycle_v653.json").read_text(encoding="utf-8"))
        self.assertEqual(30,len(registry["games"]))
        self.assertEqual(1,len(caveat["rules"]))
        w=next(g for g in registry["games"] if g["id"]=="wixoss")
        self.assertIn("JP",w["regions"])
        self.assertIn("US",w["regions"])
        retired=caveat["rules"][0]
        self.assertEqual(("wixoss","US","OFFICIAL_ENGLISH_EDITION_ENDED"),
                         (retired["game_id"],retired["country"],retired["lifecycle_status"]))
        self.assertEqual("2025-09-15",retired["official_announcement_date"])
        self.assertEqual("NOT_VERIFIED",retired["live_market_state"])

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_radar_540_tasks_32_true_box_gaps_31_current_p0(self):
        js=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json');
const intake=require('./tcg_user_research_intake_v625.json');
const a=require('./tcg_official_product_catalog_v599.json');
const b=require('./tcg_official_product_supplement_v630.json');
const c=require('./tcg_official_product_supplement_v636.json');
const d=require('./tcg_official_product_supplement_v637.json');
const e=require('./tcg_official_product_supplement_v649.json');
const caveat=require('./tcg_region_lifecycle_v653.json');
const app=require('./tcg_coverage_radar_v652.js');
const research=require('./tcg_source_research_v634.js');
const official=require('./official_box_catalog_v626.js');
const deps={research,official};
const r=app.build(reg,intake,a,b,c,d,e,deps,caveat);
assert.equal(r.games,30);assert.equal(r.region_scopes,90);
assert.equal(r.declared_region_scopes,55);
assert.equal(r.manual_search_tasks,540);
assert.equal(r.official_product_samples,88);
assert.equal(r.official_box_samples,51);
assert.equal(r.scoped_box_proofs,23);
assert.equal(r.declared_box_gaps,32);
assert.equal(r.historical_edition_scopes,1);
assert.equal(r.currently_prioritized_box_gaps,31);
assert.equal(r.manufacturer_game_samples,30);
assert.equal(app.filtered(r.tasks,{lane:'BOX',gapOnly:true}).length,32);
assert.equal(app.filtered(r.tasks,{lane:'HIT'}).length,90);
for(const t of r.tasks){
 assert.equal(t.source_verification,'SEARCH_LINK_ONLY');
 assert.equal(t.verified_product_updates,0);
 assert.equal(t.found_sources,0);
 assert.equal(t.links.length>=4,true);
 assert.ok(t.links.every(l=>l.url.startsWith('https://')));
}
const wixoss=r.tasks.find(t=>t.game_id==='wixoss'&&t.region==='US'&&t.lane==='BOX');
assert.equal(wixoss.priority,4);
assert.equal(wixoss.historical_only,true);
const japan=r.tasks.find(t=>t.game_id==='wixoss'&&t.region==='JP'&&t.lane==='CARD');
assert.equal(japan.links[0].label,'공식 카드 갤러리');
const untouched=app.build(reg,intake,a,b,c,d,e,deps);
assert.equal(untouched.currently_prioritized_box_gaps,32);
const attack=structuredClone(caveat);attack.rules[0].evidence_url='https://attacker.example';
assert.throws(()=>app.build(reg,intake,a,b,c,d,e,deps,attack),/UNVERIFIED_LIFECYCLE_RULE/);
const forged=structuredClone(e);forged.products[0].source='https://shopelestrals.com.attacker.example';
assert.throws(()=>app.build(reg,intake,a,b,c,d,forged,deps,caveat),/UNTRUSTED_V649_PRODUCT_SOURCE/);
const html=require('node:fs').readFileSync('./tcg_coverage_radar_v652.html','utf8');
assert.ok(html.includes('id="coverageList"'));
assert.ok(html.includes('tcg_region_lifecycle_v653'));
"""
        result=subprocess.run([NODE,"-e",js],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stderr)

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_node_syntax_scripts(self):
        for file in ("tcg_coverage_radar_v652.js","tcg_source_research_v634.js",
                     "tcg_event_intelligence_v646.js"):
            with self.subTest(file=file):
                p=subprocess.run([NODE,"--check",file],cwd=ROOT,capture_output=True,text=True,timeout=15)
                self.assertEqual(0,p.returncode,p.stderr)

if __name__=="__main__":
    unittest.main(verbosity=2)
