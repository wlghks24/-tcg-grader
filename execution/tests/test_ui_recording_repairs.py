"""Execute UI fixes against bounded local DOM fixtures, never live websites."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(shutil.which('node'),'Node required')
class RecordingUIRepairTests(unittest.TestCase):
    def js(self,source):
        p=subprocess.run(['node','-e',"const assert=require('node:assert/strict');\n"+source],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_feed_excerpts_are_plain_text_and_bounded(self):
        text=(ROOT/'index.html').read_text()
        fn=text[text.index('function feedDisplayText('):text.index('function normalizedSupplementaryItems(')]
        self.js(fn+"""
assert.equal(feedDisplayText('<a href="https://example.test">Pokemon news</a> &amp; cards'),'Pokemon news & cards');
assert.equal(feedDisplayText('&lt;a href="url?x=1&amp;y=2"&gt;Article&lt;/a&gt;'),'Article');
assert.equal(feedDisplayText('&amp;lt;a href="x"&amp;gt;Article&amp;lt;/a&amp;gt;'),'Article');
assert.equal(feedDisplayText('<script>alert(1)</script><style>bad{}</style>Safe'),'Safe');
assert.equal(feedDisplayText('a'.repeat(30000)).length,1200);
assert.equal(feedDisplayText('&#x110000; &#55296; &#x1f600;'),'😀');
""")

    def test_country_buttons_dispatch_one_change_and_preserve_edition_filters(self):
        text=(ROOT/'feature_category_nav.js').read_text()
        fn=text[text.index('  function installCountryButtons('):text.index('  ["analysisCountry","tradeCountry","releaseFilter","promoFilter"]')]
        self.js("""
class Node{constructor(){this.dataset={};this.attrs={};this.listeners={};this.children=[]}setAttribute(k,v){this.attrs[k]=v}addEventListener(k,fn){this.listeners[k]=fn}append(x){this.children.push(x)}}
const select=new Node();select.value='JP';select.parentElement={};select.options=['ALL','KR','JP','US','CN'].map(value=>({value}));
select.getAttribute=()=>null;let changes=0,bar;
select.insertAdjacentElement=(where,node)=>{assert.equal(where,'afterend');bar=node};
select.dispatchEvent=e=>{assert.equal(e.type,'change');changes++;select.listeners.change?.()};
const document={getElementById:id=>id==='analysisCountry'?select:null,createElement:()=>new Node()};
"""+fn+"""
assert.equal(installCountryButtons('analysisCountry'),true);assert.equal(bar.children.length,5);
const jp=bar.children.find(x=>x.dataset.country==='JP'),cn=bar.children.find(x=>x.dataset.country==='CN');
assert.equal(jp.attrs['aria-pressed'],'true');
cn.listeners.click({preventDefault(){}});assert.equal(select.value,'CN');assert.equal(changes,1);
cn.listeners.click({preventDefault(){}});assert.equal(changes,1);
assert.equal(cn.attrs['aria-pressed'],'true');assert.equal(jp.attrs['aria-pressed'],'false');
assert.equal(installCountryButtons('missing'),false);
select.parentElement={tagName:'LABEL',insertAdjacentElement:(where,node)=>{assert.equal(where,'afterend');bar=node}};
select.insertAdjacentElement=()=>{throw Error('country controls must span the grid outside the select label')};
assert.equal(installCountryButtons('analysisCountry'),true);assert.equal(bar.children.length,5);
""")

    def test_local_image_replacement_revalidates_and_hides_old_fallback(self):
        text=(ROOT/'image_quality_guard.js').read_text()
        self.js("""
const vm=require('node:vm');let observer;
class Img{constructor(src){this.src=src;this.currentSrc='';this.complete=true;this.naturalWidth=200;this.naturalHeight=300;this.dataset={};this.style={};this.listeners={};this.alt='BOX';this.parentElement=parent}addEventListener(k,fn){this.listeners[k]=fn}matches(){return true}}
let fallback=null;const legacy={style:{display:'block'}};
const parent={querySelector:()=>fallback,querySelectorAll:()=>[legacy,...(fallback?[fallback]:[])],insertBefore:node=>fallback=node};
const img=new Img('https://example.test/logo.jpg');
const document={readyState:'complete',documentElement:{},querySelectorAll:()=>[img],createElement:()=>({style:{}})};
const window={};const MutationObserver=class{constructor(fn){observer=fn}observe(){}};
vm.runInNewContext("""+repr(text)+""",{document,window,HTMLImageElement:Img,MutationObserver,location:{origin:'http://127.0.0.1:8765'},URL,WeakSet});
assert.equal(img.style.display,'none');assert.equal(fallback.style.display,'flex');
img.src='http://127.0.0.1:8765/api/local-card-images/file/'+'a'.repeat(32);
observer([{type:'attributes',target:img}]);
assert.equal(img.style.display,'block');assert.equal(fallback.style.display,'none');assert.equal(legacy.style.display,'none');
assert.equal(img.dataset.qualityRejected,undefined);
img.src='https://example.test/another.jpg';img.naturalWidth=1;img.naturalHeight=1;img.listeners.load();
assert.equal(img.style.display,'none');assert.equal(fallback.style.display,'flex');
img.src='/api/local-card-images/file/'+'b'.repeat(32);img.naturalWidth=200;img.naturalHeight=300;img.listeners.load();
assert.equal(img.style.display,'block');assert.equal(fallback.style.display,'none');
img.src='http://evil.test/api/local-card-images/file/'+'b'.repeat(32);img.listeners.load();assert.equal(img.style.display,'none');
const uploaded=new Img('blob:manual-upload');uploaded.matches=()=>false;
observer([{type:'attributes',target:uploaded}]);assert.equal(uploaded.style.display,undefined,'manual grading uploads must not be catalog-filtered');
assert.deepEqual(uploaded.listeners,{});
""")

    def test_image_management_launcher_reveals_managed_parent_before_scroll(self):
        text=(ROOT/'tablet_image_library_v1.js').read_text()
        start=text.index('    const destinations=[');end=text.index('    for(const [label,cb] of destinations)',start)
        self.js("""
let open=false,scrolls=[],status={};const manager={open:false,id:'manager'},surface={id:'surface'};
const document={getElementById:id=>({tcgImageManagementV46:manager,tcgImageLibrarySurface:surface}[id]),querySelector:()=>null};
const openManaged=id=>{assert.equal(id,'tcgImageLibrarySurface');open=true;return true};
const go=node=>{assert.equal(open,true,'ancestor must be revealed before scrolling');scrolls.push(node.id)};
const backToFullView=()=>{throw Error('must not hide destination parent')};const main={};
"""+text[start:end]+"""
destinations.find(x=>x[0]==='자동수집')[1]();assert.equal(manager.open,true);
open=false;destinations.find(x=>x[0]==='관리')[1]();assert.equal(manager.open,true);
assert.deepEqual(scrolls,['manager','manager']);
""")

if __name__=='__main__':unittest.main()
