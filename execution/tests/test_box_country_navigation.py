"""Execute shipped JS helpers with Node; no browser, network, or tablet mutation."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(shutil.which('node'),'Node required')
class CountryNavigationTests(unittest.TestCase):
    def run_js(self,source):
        p=subprocess.run(['node','-e',"const assert=require('node:assert/strict');\n"+source],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_all_tab_shows_unknown_release_without_claiming_released(self):
        source=(ROOT/'box_knowledge_stats.js').read_text()
        self.assertIn('data-box-tab="ALL"',source)
        self.assertIn("let activeTab='ALL';",source)
        fn=source[source.index('function passesTab('):source.index('function applyTabFilter(')]
        self.run_js("let activeTab='ALL';const uniqueKey=(c,n)=>c+'|'+n;const releaseState=r=>r.status;\n"+fn+"""
const rows=['UNKNOWN','RELEASED','UPCOMING'].map(status=>({country:'KR',name:status,status}));
assert.deepEqual(rows.map(r=>passesTab(r,new Set())),[true,true,true]);
activeTab='RELEASED';assert.deepEqual(rows.map(r=>passesTab(r,new Set())),[false,true,false]);
activeTab='UPCOMING';assert.deepEqual(rows.map(r=>passesTab(r,new Set())),[false,false,true]);
activeTab='TRADING';assert.deepEqual(rows.map(r=>passesTab(r,new Set(['KR|UNKNOWN']))),[true,false,false]);
""")

    def test_combined_chinese_button_preserves_exact_editions(self):
        source=(ROOT/'box_knowledge_stats.js').read_text()
        helpers=source[source.index('const normCountry='):source.index('const validImage=')]
        index=(ROOT/'index.html').read_text()
        fn=index[index.index('function boxKbCountryMatches('):index.index('let selectedBoxKbCountry=')]
        self.run_js(helpers+fn+"""
const editions=['KR','JP','US','CN-S','CN-T'];
for(const selected of ['ALL','KR','JP','US','CN','CN-S','CN-T']){
 assert.deepEqual(editions.filter(x=>countryMatches(selected,x)),editions.filter(x=>boxKbCountryMatches(selected,x)));
}
assert.deepEqual(editions.filter(x=>countryMatches('CN',x)),['CN-S','CN-T']);
assert.equal(countryLabel('CN'),'중국판');assert.equal(countryMatches('CN-S','CN-T'),false);
assert.equal(countryMatches('KR','CN-S'),false);
""")
        self.assertIn('data-kb-country="CN"',index)

    def test_country_updates_are_scoped_and_synchronous(self):
        source=(ROOT/'box_knowledge_stats.js').read_text()
        start=source.index("document.addEventListener('click',e=>{\n const t=")
        end=source.index("if(document.readyState",start)
        handler=source[start:end]
        self.run_js("""
let click;let changed=0,filtered=0,stats=0;
const section={contains:t=>t.inside};const $=()=>section;
const document={addEventListener:(name,fn)=>{click=fn}};
const updateBoxFilterState=()=>changed++,applyTabFilter=()=>filtered++,refreshStatsOnly=()=>stats++;
"""+handler+"""
const button={inside:true};
click({target:{closest:s=>{assert.equal(s,'.box-kb-country');return button}}});
assert.deepEqual([changed,filtered,stats],[1,1,1]);
click({target:{closest:()=>({inside:false})}});click({target:{closest:()=>null}});
assert.deepEqual([changed,filtered,stats],[1,1,1]);
""")

    def test_official_china_enters_same_catalog_without_price_or_duplicate(self):
        source=(ROOT/'tcg_market_expanded_v487.js').read_text()
        piece=source[source.index('  function validOfficialLink(row){'):source.index('  async function load(){',source.index('/* V571:'))]
        self.run_js("""
const regions=[['CN-S'],['CN-T']];const COUNTRY_BOX_DATA=[];let renders=0,events=0;
const renderBoxKnowledge=()=>renders++;const CustomEvent=function(type,options){this.type=type;this.detail=options.detail};
const window={dispatchEvent:e=>{assert.equal(e.type,'tcg-market-catalog-expanded');events++}};
"""+piece+"""
const base={autodiscovered:true,source_grade:'official_catalog',market_eligible:false,price_evidence:'NONE',game:'Pokémon',asset:'BOX',name:'Fixture'};
const a={...base,region:'CN-S',market_locale:'CN',source:'https://www.pokemon.cn/tcg/product/12345.html'};
const b={...base,region:'CN-T',market_locale:'TW',source:'https://asia.pokemon-card.com/tw/archives/12345/'};
assert.equal(validOfficialLink({...a,source:'https://evil.example/tcg/product/12345.html'}),'');
assert.equal(validOfficialLink({...a,market_eligible:true}),'');
assert.equal(validOfficialLink({...a,price_evidence:'VERIFIED'}),'');
const rows=[a,b].map(r=>({...r,safeSource:validOfficialLink(r)}));
integrate(rows);integrate(rows);
assert.equal(COUNTRY_BOX_DATA.length,2);assert.equal(renders,2);
for(const row of COUNTRY_BOX_DATA){assert.equal(row.priceEvidence,'NONE');assert.equal(row.release,'확인 중');assert.equal(row.marketTrading,false);assert.equal(row.officialCatalogOnly,true);}
""")
        self.assertNotIn('tcgChinaAutoV571',source)

if __name__=='__main__':unittest.main()
