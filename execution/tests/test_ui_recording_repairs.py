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

    def test_saved_image_detail_click_keyboard_and_missing_metadata(self):
        text=(ROOT/'tablet_image_library_v1.js').read_text()
        start=text.index("  const API='/api/local-card-images/catalog-links';")
        end=text.index('  // The original card/BOX collectors',start)
        self.js("""
class Element{constructor(tag){this.tagName=tag;this.dataset={};this.attrs={};this.children=[];this.listeners={};this.textContent='';this.open=false;this.style={}}setAttribute(k,v){this.attrs[k]=v}addEventListener(k,fn){this.listeners[k]=fn}append(...nodes){this.children.push(...nodes)}set innerHTML(v){throw Error('metadata must never execute as HTML')}}
const document={createElement:tag=>new Element(tag),getElementById:()=>null};
const allText=node=>[node.textContent,...node.children.map(allText)].join(' ');
"""+text[start:end]+"""
const row={id:'a'.repeat(32),game_id:'pokemon',region:'CN-T',kind:'CARD',name:'Fixture Card',image_url:'/api/local-card-images/file/'+'a'.repeat(32),provider:'TCGdex',source_id:'base1-4',source_url:'https://api.tcgdex.net/v2/zh-tw/cards/base1-4',card_metadata:{card_code:'base1-4',set_name:'<script>text only</script>',rarity:'Rare'}};
const card=content(row);const [trigger,body,details]=card.children;
assert.equal(trigger.tagName,'button');assert.equal(trigger.type,'button');assert.equal(trigger.attrs['aria-expanded'],'false');
assert.equal(details.children.length,1,'detail is lazy until opened');
trigger.listeners.click();assert.equal(details.open,true);assert.equal(trigger.attrs['aria-expanded'],'true');
assert.equal(details.children.length,2);assert.match(allText(details),/중국어 번체판/);
assert.match(allText(details),/base1-4/);assert.match(allText(details),/미확인 · 추가 수집 대기/);
assert.equal(allText(details).includes('<script>text only</script>'),true);assert.match(allText(details),/검증된 시세·실거래 연결 없음/);
const panel=details.children[1],link=panel.children.find(x=>x.tagName==='a'),photo=panel.children.find(x=>x.tagName==='img');
assert.equal(link.href,row.source_url);assert.equal(link.target,'_blank');assert.equal(link.rel,'noopener noreferrer');assert.equal(photo.src,row.image_url);
for(const key of ['Enter',' ']){details.open=false;details.listeners.toggle();let prevented=false;
 trigger.listeners.keydown({key,preventDefault(){prevented=true}});assert.equal(prevented,true);assert.equal(details.open,true);assert.equal(details.children.length,2);}
const missing=content({...row,id:'b'.repeat(32),region:'CN-S',card_metadata:{},source_url:'javascript:alert(1)'});
missing.children[0].listeners.click();const missingDetail=missing.children[2];
assert.match(allText(missingDetail),/중국어 간체판/);assert.match(allText(missingDetail),/추가 수집 대기/);
assert.equal(missingDetail.children[1].children.filter(x=>x.tagName==='a').length,0);
for(const raw of ['https://api.tcgdex.net.evil.test/x','https://user@api.tcgdex.net/x','https://api.tcgdex.net:8443/x','http://api.tcgdex.net/x','https://unknown.test/x'])assert.equal(detailSourceUrl(raw),'');
""")

    def test_game_country_filters_render_only_matching_local_records(self):
        text=(ROOT/'tablet_image_library_v1.js').read_text()
        start=text.index("  const API='/api/local-card-images/catalog-links';")
        end=text.index('  function appendProducts(){',start)
        self.js("""
class Element{constructor(tag){this.tagName=tag;this.dataset={};this.attrs={};this.children=[];this.listeners={};this.textContent='';this.style={}}setAttribute(k,v){this.attrs[k]=v}addEventListener(k,fn){this.listeners[k]=fn}append(...nodes){this.children.push(...nodes)}remove(){const i=host.children.indexOf(this);if(i>=0)host.children.splice(i,1)}}
const host=new Element('div');host.querySelectorAll=()=>[...host.children];
const controls={analysisCountry:{value:'JP'},analysisAsset:{value:'HIT'},analysisGame:{value:'Pokémon'},analysisQuery:{value:''},countryAnalysisList:host,analysisCount:{textContent:'검색'}};
const document={createElement:tag=>new Element(tag),getElementById:id=>controls[id]};
"""+text[start:end]+"""
data=['KR','JP','CN-S','CN-T'].map((region,i)=>({id:String(i).repeat(32),game_id:'pokemon',region,kind:'CARD',name:region+' fixture',image_url:'/api/local-card-images/file/'+String(i).repeat(32)}));
data.push({...data[0],id:'e'.repeat(32),game_id:'naruto',name:'Naruto Fixture'});
assert.equal(appendCards(),1);assert.equal(host.children[0].dataset.region,'JP');assert.equal(host.children[0].children[0].tagName,'button');
controls.analysisCountry.value='CN';assert.equal(appendCards(),2);assert.deepEqual(host.children.map(x=>x.dataset.region),['CN-S','CN-T']);
controls.analysisCountry.value='ALL';controls.analysisGame.value='NARUTO';assert.equal(appendCards(),1);assert.equal(host.children[0].dataset.game,'naruto');
controls.analysisGame.value='Pokémon';controls.analysisAsset.value='BOX';assert.equal(appendCards(),0);assert.equal(host.children.length,0);
""")

if __name__=='__main__':unittest.main()
