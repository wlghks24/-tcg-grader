#!/usr/bin/env python3
"""V626 independent mobile BOX UI regression, Node built-in assert only."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
NODE = shutil.which("node")
MODULE = "./official_box_catalog_v626.js"
CATALOG = "./tcg_official_product_catalog_v599.json"


@unittest.skipUnless(NODE, "Node.js is not installed; browser verification required")
class OfficialBoxViewV626Tests(unittest.TestCase):
    def run_js(self, assertions):
        code = """
'use strict';
const assert=require('node:assert/strict');
const api=require('./official_box_catalog_v626.js');
const data=require('./tcg_official_product_catalog_v599.json');
const products=api.normalizeProducts(data);
""" + assertions
        process = subprocess.run([NODE, "-e", code], cwd=ROOT, text=True,
                                 capture_output=True, timeout=20, check=False)
        self.assertEqual(process.returncode, 0, process.stdout + "\n" + process.stderr)

    def test_all_58_actual_official_products_and_14_games_visible(self):
        self.run_js("""
assert.equal(data.products.length,58);
assert.equal(products.length,58);
assert.equal(new Set(products.map(x=>x.id)).size,58);
assert.equal(new Set(products.map(x=>x.game)).size,14);
assert.equal(products.filter(x=>x.game==='Pokémon').length,10);
assert.equal(products.filter(x=>x.game==='Palworld OFFICIAL CARD GAME').length,2);
assert.equal(products.filter(x=>x.game==='Magic: The Gathering').length,6);
""")

    def test_full_pagination_no_40_or_100_record_silent_cutoff(self):
        self.run_js("""
const sorted=api.filterProducts(products,{});
const pages=[0,1,2,3,4].map(p=>api.paginate(sorted,p,12));
assert.deepEqual(pages.map(p=>p.rows.length),[12,12,12,12,10]);
assert.deepEqual(pages.map(p=>p.pages),[5,5,5,5,5]);
assert.equal(new Set(pages.flatMap(x=>x.rows.map(y=>y.id))).size,58);
assert.equal(api.paginate(sorted,999,12).page,4);
assert.equal(api.paginate(sorted,-4,12).page,0);
""")

    def test_more_than_100_rows_are_not_silently_truncated(self):
        self.run_js("""
const base=products.find(p=>p.id==='pk-KR-30TH-2026');
const extras=Array.from({length:143},(_,i)=>({...base,id:'fake-test-'+i}));
const normalized=api.normalizeProducts({schema_version:1,products:extras});
assert.equal(normalized.length,143);
const seen=[];
for(let p=0;p<12;p++)seen.push(...api.paginate(normalized,p,12).rows);
assert.equal(seen.length,143);
assert.equal(api.paginate(normalized,11,12).rows.length,11);
""")

    def test_correct_country_currency_prices_and_units(self):
        self.run_js("""
const jp=products.find(p=>p.id==='pk-JP-NINJA-2026');
const kr=products.find(p=>p.id==='pk-KR-30TH-2026');
const us=products.find(p=>p.id==='db-FB09-US');
assert.match(api.formatPrice(jp.msrp),/^제조사 정가 ¥180 \/ 팩$/);
assert.match(api.formatPrice(kr.msrp),/70,000원 \/ BOX$/);
assert.match(api.formatPrice(us.msrp),/\$4\.99 \/ 팩$/);
assert.equal(api.formatPrice(undefined),'제조사 정가 미확인');
assert.equal(api.formatPrice({currency:'GBP',amount:200,unit:'PACK'}),'제조사 정가 미확인');
""")

    def test_mobile_search_game_region_and_box_pack_filter(self):
        self.run_js("""
assert.equal(api.filterProducts(products,{game:'Pokémon',country:'KR',kind:'BOX'}).length,5);
assert.equal(api.filterProducts(products,{game:'Pokémon',country:'JP',kind:'BOOSTER_PACK'}).length,5);
assert.equal(api.filterProducts(products,{game:'Godzilla Card Game',country:'US'}).length,3);
assert.equal(api.filterProducts(products,{game:'Palworld OFFICIAL CARD GAME',country:'US'}).length,2);
assert.equal(api.filterProducts(products,{search:'hyperIA'}).length,1);
assert.equal(api.filterProducts(products,{game:'Magic: The Gathering',country:'US',kind:'BOX'}).length,6);
assert.equal(api.filterProducts(products,{search:'Reality Fracture'}).length,2);
assert.equal(api.filterProducts(products,{country:'KR',kind:'BOOSTER_PACK'}).length,0);
""")

    def test_official_source_allowlist_against_phishing(self):
        self.run_js("""
const good=[
['https://pokemoncard.co.kr/card/960','Pokémon'],
['https://www.pokemon-card.com/products/','Pokémon'],
['https://onepiece-cardgame.kr/products/view.do?brdno=5143','ONE PIECE'],
['https://en.godzilla-cardgame.com/products/ebp04/','Godzilla Card Game'],
['https://en.palworld-official-cardgame.com/products','Palworld OFFICIAL CARD GAME'],
['https://www.yugioh-card.com/en/products/betb/','Yu-Gi-Oh!'],
['https://magic.wizards.com/en/news/feature/collecting-reality-fracture','Magic: The Gathering'],
['https://www.narutotcgmythos.com/set-1-konoha-shido','NARUTO'],
['https://www.unionarena-tcg.com/na/products/boosters/kgr-1.php','UNION ARENA'],
['https://en.ws-tcg.com/products/bp-mki/','Weiß Schwarz']
];
for(const [url,game] of good)assert.equal(api.trustedSource(url,game),true,url);
for(const bad of [
'https://pokemoncard.co.kr.evil.example/card/960',
'https://attack.example/pokemoncard.co.kr',
'http://pokemoncard.co.kr/card/960',
'javascript:alert(1)',
'https://evil@pokemoncard.co.kr/card/960',
'https://pokemoncard.co.kr:1234/card/960',
'https://pokemoncard.co.kr/card/960#frag',
'https://pokemon-card.com.evil.example/card/960'
])assert.equal(api.trustedSource(bad,'Pokémon'),false,bad);
assert.equal(api.trustedSource('https://pokemoncard.co.kr/card/960','Yu-Gi-Oh!'),false);
""")

    def test_reject_bad_rows_wrong_unit_printing_and_duplicate(self):
        self.run_js("""
const base=products.find(x=>x.id==='pk-KR-30TH-2026');
const invalid=[
{...base,source:'http://pokemoncard.co.kr/card/960'},
{...base,msrp:{currency:'USD',amount:70000,unit:'BOX'}},
{...base,msrp:{currency:'KRW',amount:NaN,unit:'BOX'}},
{...base,msrp:{currency:'KRW',amount:70000,unit:'PACK'}},
{...base,product_type:'BOOSTER_PACK'},
{...base,set_code_verified:true},
{...base,product_type:'UNKNOWN'},
{...base,packs_per_box:0}
];
for(const row of invalid)assert.equal(api.validProduct(row),false,JSON.stringify(row));
const normalized=api.normalizeProducts({schema_version:1,products:[base,base,{...base,id:'x',source:'https://evil.example'}]});
assert.equal(normalized.length,1);
assert.equal(api.normalizeProducts({schema_version:2,products:[base]}).length,0);
""")

    def test_prerelease_event_date_is_not_product_release(self):
        self.run_js("""
const h=products.find(p=>p.id==='lc-HYPERIA-PRE-US');
const a=products.find(p=>p.id==='lc-ATTACKVINE-PRE-US');
assert.equal(h.release_date,'');
const labels=api.releaseLabels(h);
assert.ok(labels.includes('프리릴리즈 행사 2026-10-16'));
assert.ok(labels.includes('세트 발매 2026-10-23'));
assert.ok(labels.includes('BOX 발매일 미확인'));
assert.ok(api.releaseLabels(a).some(x=>x.startsWith('프리릴리즈 행사 ')));
""")

    def test_node_syntax_compilation(self):
        p = subprocess.run([NODE, "--check", "official_box_catalog_v626.js"],
                           cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
        self.assertEqual(p.returncode, 0, p.stderr)


class OfficialBoxViewStaticV626Tests(unittest.TestCase):
    def test_html_loads_dependency_free_module_with_mobile_filters(self):
        html=(ROOT/"official_box_catalog_v626.html").read_text(encoding="utf-8")
        self.assertIn('lang="ko"',html)
        self.assertIn('name="viewport"',html)
        self.assertIn('official_box_catalog_v626.js',html)
        self.assertIn('Content-Security-Policy',html)
        self.assertNotIn('onsubmit=',html)
        for control in ("boxV626App","boxV626Game","boxV626Region","boxV626Type",
                        "boxV626Search","boxV626Results","boxV626Next","boxV626Previous"):
            self.assertIn('id="'+control+'"',html)

    def test_js_uses_dom_text_not_untrusted_html_template(self):
        source=(ROOT/"official_box_catalog_v626.js").read_text(encoding="utf-8")
        self.assertNotIn(".innerHTML",source)
        self.assertIn("textContent",source)
        self.assertIn('noopener noreferrer',source)
        self.assertIn('fetch("./tcg_official_product_catalog_v599.json"',source)
        self.assertNotIn("http://",source)
        self.assertNotIn("localStorage",source)

    def test_scope_is_explicitly_official_not_market_or_hit_guarantee(self):
        html=(ROOT/"official_box_catalog_v626.html").read_text(encoding="utf-8")
        self.assertIn("실시간 재고",html)
        self.assertIn("개봉 HIT 확률",html)
        self.assertIn("독립 상품 조회 화면",html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
