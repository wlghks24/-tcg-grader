#!/usr/bin/env python3
"""V663: Pokémon US display & retailer promo must never inflate HIT or sale evidence."""
import copy
import shutil
import subprocess
import unittest
from execution.official_box_coverage_audit_v623 import ROOT, CoverageError, _load_json
from tcg_official_overlay_v663 import build,validate_v663,validate_promo
from tcg_source_audit_v633 import plan
from tcg_multi_source_queue_v639 import build_queue

NODE=shutil.which("node")
def get(name):return _load_json(ROOT/name)

class PokemonUSProofV663(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=get("tcg_game_registry.json")
        cls.intake=get("tcg_user_research_intake_v625.json")
        cls.base=get("tcg_official_product_catalog_v599.json")
        cls.parts=[get("tcg_official_product_supplement_v"+str(n)+".json")
                    for n in (630,636,637,649,654,657,659,662,663)]
        cls.promo=get("tcg_official_promo_evidence_v663.json")

    def test_python_sealed_box_gap_and_promo_number_boundaries(self):
        report=build()
        self.assertEqual((99,62,21),tuple(report["prior"][k] for k in ("products","boxes","gaps")))
        self.assertEqual((100,63,20),tuple(report["with_v663"][k] for k in ("products","boxes","gaps")))
        self.assertEqual(35,report["with_v663"]["with_box"])
        self.assertEqual(55,report["with_v663"]["region_pairs"])
        self.assertEqual(3,report["official_promo_name_samples"])
        self.assertEqual(0,report["official_promo_card_numbers_verified"])
        self.assertEqual(0,report["market_prices_verified"])
        self.assertEqual(0,report["network_calls"])

    def test_offline_market_plan_and_original_30_games_preserved(self):
        first=plan(self.registry,self.intake,self.base,*self.parts[:-1])
        second=plan(self.registry,self.intake,self.base,*self.parts,self.promo)
        self.assertEqual((99,62,21),tuple(first[k] for k in
             ("official_product_samples","official_sealed_box_samples","declared_sealed_box_spec_gaps")))
        self.assertEqual((100,63,20),tuple(second[k] for k in
             ("official_product_samples","official_sealed_box_samples","declared_sealed_box_spec_gaps")))
        self.assertEqual(90,second["market_search_scopes"])
        self.assertEqual(338,sum(second[k] for k in
             ("product_candidate_count","upcoming_candidate_count","hit_candidate_count","promo_candidate_count")))
        queued=build_queue()
        self.assertEqual(1014,len(queued["jobs"]))
        self.assertTrue(all(x["review_status"]=="PENDING_HUMAN_SOURCE_VERIFICATION"
                            and not x["manufacturer_approved"] for x in queued["jobs"]))
        self.assertTrue(all(x["official_box_samples_in_scope"]>0 for x in queued["jobs"]
                            if x["game_id"]=="pokemon" and x["market"]=="US"))

    def test_fake_boxes_prices_and_event_promo_are_denied(self):
        prior=[*self.base["products"],*
               [p for supplement in self.parts[:-1] for p in supplement["products"]]]
        accepted=validate_v663(self.parts[-1],self.registry,prior)
        self.assertEqual((1,36,"10"),(len(accepted),accepted[0]["packs_per_box"],
                                     accepted[0]["cards_per_pack"]))
        for name,value in (("packs_per_box",9),("cards_per_pack","11"),
                           ("source","https://pokemon.com.attacker.example/"),
                           ("release_date","2027-01-01"),
                           ("set_code_verified",True),
                           ("msrp",{"currency":"USD","amount":100,"unit":"BOX"}),
                           ("unverified_price_guess",99999)):
            with self.subTest(field=name):
                fake=copy.deepcopy(self.parts[-1])
                fake["products"][0][name]=value
                with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V663_PRODUCT"):
                    validate_v663(fake,self.registry,prior)
        promos=validate_promo(self.promo)
        self.assertEqual(3,len(promos))
        self.assertTrue(all(x["card_number"] is None for x in promos))
        fake=copy.deepcopy(self.promo);fake["records"][0]["surprise_hit_odds"]=0.9
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V663_PROMO"):
            validate_promo(fake)
        fake=copy.deepcopy(self.promo);fake["records"][0]["card_number"]="FAKE-001"
        with self.assertRaisesRegex(CoverageError,"UNTRUSTED_V663_PROMO"):
            validate_promo(fake)

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_node_radar_catalog_and_promo_crosscheck(self):
        js=r"""
const assert=require('node:assert/strict');
const reg=require('./tcg_game_registry.json'),lead=require('./tcg_user_research_intake_v625.json');
const base=require('./tcg_official_product_catalog_v599.json');
const x=[630,636,637,649,654,657,659,662,663].map(n=>require('./tcg_official_product_supplement_v'+n+'.json'));
const promos=require('./tcg_official_promo_evidence_v663.json');
const official=require('./official_box_catalog_v626.js');
const research=require('./tcg_source_research_v634.js');
const radar=require('./tcg_coverage_radar_v652.js');
const old=research.build(reg,lead,base,...x.slice(0,6),official,x[6],x[7]);
const latest=research.build(reg,lead,base,...x.slice(0,6),official,x[6],x[7],x[8],promos);
assert.deepEqual([old.summary.official,old.summary.officialBoxes,old.summary.boxMissing],[99,62,21]);
assert.deepEqual([latest.summary.official,latest.summary.officialBoxes,latest.summary.boxMissing],[100,63,20]);
const history=require('./tcg_region_lifecycle_v653.json');
const r=radar.build(reg,lead,base,...x.slice(0,4),{research,official},history,
   x[4],x[5],x[6],x[7],x[8],promos);
assert.deepEqual([r.official_product_samples,r.official_box_samples,r.declared_box_gaps,r.manual_search_tasks],
                 [100,63,20,540]);
const bad=structuredClone(promos);bad.records[1].card_number="FAKE";
assert.throws(()=>official.validatePromoV663(bad),/UNTRUSTED_V663_PROMO/);
"""
        p=subprocess.run([NODE,"-e",js],cwd=ROOT,text=True,capture_output=True,timeout=30)
        self.assertEqual(0,p.returncode,p.stderr)

    @unittest.skipUnless(NODE,"Node.js unavailable")
    def test_tablet_optional_json_loads_in_parallel_and_preserves_previous_data(self):
        js=r"""
const assert=require('node:assert/strict');
const official=require('./official_box_catalog_v626.js');
class Node {
 constructor(){this.children=[];this.textContent='';this.value='ALL';this.disabled=false;}
 appendChild(item){this.children.push(item);return item;}
 replaceChildren(...rows){this.children=rows;}
 addEventListener(){}
 setAttribute(){}
}
const ids=['boxV626App','boxV626Game','boxV626Region','boxV626Type','boxV626Search',
 'boxV626Filters','boxV626Results','boxV626Status','boxV626Next','boxV626Previous','boxV626Page'];
const dom=Object.fromEntries(ids.map(x=>[x,new Node()]));
const doc={getElementById:key=>dom[key],createElement:()=>new Node()};
const fetched=[];
const baseline={schema_version:1,products:[{id:'us-box-sample',game:'Pokémon',
 country:'US',product_type:'BOX',set_code:'LOCAL-UNITTEST',set_code_verified:false,
 name:'Known good preserved sealed box',release_date:'2026-03-27',
 source:'https://www.pokemon.com/us/news/pokemon-tcg-mega-evolution-perfect-order-product-showcase',
 packs_per_box:36,cards_per_pack:'10'}]};
global.fetch=(url)=>{
 const name=url.replace(/^\.\//,'');
 fetched.push(name);
 if(name==='tcg_official_product_catalog_v599.json')
   return Promise.resolve({ok:true,json:async()=>baseline});
 return Promise.resolve({ok:false,status:404,json:async()=>null});
};
(async()=>{
 official.mount(doc);
 for(let i=0;i<70;i++) await Promise.resolve();
 assert.equal(fetched.filter(x=>x.startsWith('tcg_official_product_supplement_v')).length,11);
 assert.equal(fetched.filter(x=>x.includes('promo_evidence_v663')).length,1);
 assert.ok(dom.boxV626Status.textContent.includes('1건'));
 assert.ok(dom.boxV626Status.textContent.includes('추가 제조사 자료 일부 로드 실패'));
})().catch(err=>{console.error(err);process.exitCode=1;});
"""
        result=subprocess.run([NODE,"-e",js],cwd=ROOT,capture_output=True,text=True,timeout=30)
        self.assertEqual(0,result.returncode,result.stderr)

if __name__=="__main__":
    unittest.main(verbosity=2)
