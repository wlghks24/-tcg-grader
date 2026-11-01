"""Deterministic JS contract tests, without a browser or device claims."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CatalogImageRuntimeTests(unittest.TestCase):
    def run_js(self, body):
        source = (ROOT / 'market_catalog_expander.js').read_text()
        prefix = source.split("if(document.readyState==='loading')", 1)[0]
        result = subprocess.run(['node', '-e', prefix + "\nconst assert=require('node:assert/strict');\n" + body + '\n})();'],
                                cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_exact_game_and_unique_box_only(self):
        self.run_js("""
const index={'JP|Set':{url:'https://example.test/a.jpg',game:'Pokémon'}};
const row={country:'JP',name:'Set',game:'Pokémon'};
assert.equal(applyReviewedImages([row],index),1);
assert.equal(row.boxImage,index['JP|Set'].url);
for(const extra of [{game:'ONE PIECE'},{game:'확인 중'},{marketAsset:'HIT'},{catalogAsset:'HIT'}]){
 const item={country:'JP',name:'Set',game:'Pokémon',...extra};
 assert.equal(applyReviewedImages([item],index),0);
 assert.equal(item.boxImage,undefined);
}
const a={country:'JP',name:'Set',game:'Pokémon'}, b={...a};
assert.equal(applyReviewedImages([a,b],index),0);
assert.equal(applyReviewedImages([{...a,boxImage:'existing'}],index),0);
""")

    def test_bad_manifest_cannot_abort_render_and_expansion_event(self):
        self.run_js("""
(async()=>{
 globalThis.COUNTRY_BOX_DATA=[];
 let rendered=0,events=0;
 globalThis.renderBoxKnowledge=()=>rendered++;
 globalThis.window={dispatchEvent:e=>{assert.equal(e.type,'tcg-market-catalog-expanded');events++}};
 globalThis.CustomEvent=class {constructor(type,init){this.type=type;this.detail=init.detail}};
 for(const items of [null,[],false,'bad']){
  globalThis.fetch=async path=>({ok:true,json:async()=>path.startsWith('catalog_')?{items}: {}});
  assert.equal(await loadReviewedIndex(),null);
  await expand();
 }
 assert.equal(rendered,4);assert.equal(events,4);
})().catch(e=>{console.error(e);process.exitCode=1});
""")

    def test_manifest_urls_and_duplicates_fail_closed(self):
        self.run_js(r"""
(async()=>{
 const row={region:'CN-S',name:'Set',game:'Pokémon',url:'https://example.test/a.jpg'};
 for(const url of ['http://example.test/a','https://u:p@example.test/a','https://example.test:444/a',
                   'https://example.test/a\b','https://example.test/a\nb','https://example.test/a b']){
  globalThis.fetch=async()=>({ok:true,json:async()=>({items:{Set:{...row,url}}})});
  assert.equal(Object.keys(await loadReviewedIndex()).length,0,url);
 }
 globalThis.fetch=async()=>({ok:true,json:async()=>({items:{one:row,two:{...row}}})});
 assert.equal((await loadReviewedIndex())['CN-S|Set'].ambiguous,true);
 globalThis.fetch=async()=>({ok:true,json:async()=>({items:{one:row}})});
 assert.equal((await loadReviewedIndex())['CN-S|Set'].game,'Pokémon');
})().catch(e=>{console.error(e);process.exitCode=1});
""")

    def test_local_photo_load_failure_and_code_collision(self):
        source = (ROOT / 'tablet_image_library_v1.js').read_text()
        fn = source[source.index('  function applyExactBoxPhotos(){'):source.index('  function render(){appendCards();')]
        harness = r"""
const assert=require('node:assert/strict');
const productsId='products',clean=x=>String(x||'').trim(),games={'Pokémon':'pokemon'};
const selectedCountry=(a,b)=>a==='ALL'||a===b,selectedGame=(a,b)=>a==='ALL'||a===b||games[a]===b;
const selected=()=> 'ALL',IDPAT=/^\/api\/local-card-images\/[a-f0-9]+$/;
let img=null;const fallback={style:{}};
const visual={dataset:{},prepend:x=>img=x,querySelector:s=>s==='img'?img:fallback};
const card={querySelector:s=>s==='.box-kb-name'?{textContent:'Set'}:s==='.box-kb-native'?{textContent:'Set'}:visual};
globalThis.document={getElementById:()=>({querySelectorAll:()=>[card]}),
 querySelector:()=>null,createElement:()=>({style:{},getAttribute(k){return this[k]}})};
const row={country:'JP',name:'Set',native:'Set',game:'Pokémon',code:'ABC'};
const COUNTRY_BOX_DATA=[row];
const match={kind:'BOX',catalog_kind:'BOX',match:'CODE_MATCH',region:'JP',game_id:'pokemon',
 catalog_name:'Set',catalog_code:'ABC',image_url:'/api/local-card-images/abc'};
const matches=[match],data=[{...match}];
assert.equal(applyExactBoxPhotos(),1);
assert.equal(img.style.display,'none');assert.equal(fallback.style.display,'block');
img.onerror();assert.equal(visual.dataset.tcgLocalImage,'code-match-load-failed');
img.onload();assert.equal(visual.dataset.tcgLocalImage,'code-match-loaded');
assert.equal(img.style.display,'block');assert.equal(fallback.style.display,'none');
row.code='DIFFERENT';assert.equal(applyExactBoxPhotos(),0);row.code='ABC';
COUNTRY_BOX_DATA.push({...row,game:'ONE PIECE'});assert.equal(applyExactBoxPhotos(),0);
COUNTRY_BOX_DATA.pop();data.length=0;assert.equal(applyExactBoxPhotos(),0);
"""
        result = subprocess.run(['node', '-e', fn + harness], cwd=ROOT, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == '__main__':
    unittest.main()
