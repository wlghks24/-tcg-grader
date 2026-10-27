"""Execute shipped navigation functions using a deterministic DOM/timer harness."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]
NAV=(ROOT/'feature_category_nav.js').read_text()
INDEX=(ROOT/'index.html').read_text()

@unittest.skipUnless(shutil.which('node'),'Node required')
class NavigationActionTests(unittest.TestCase):
    def js(self,code):
        p=subprocess.run(['node','-e',"const assert=require('node:assert/strict');\n"+code],capture_output=True,text=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def test_latest_navigation_wins_and_detached_or_hidden_targets_do_not_scroll(self):
        fn=NAV[NAV.index('  function scrollTarget('):NAV.index('  function categoryLabel(')]
        self.js("""
let navigationScrollGeneration=0,navigationScrollTimer=null,queue=[],moves=[];
const setTimeout=fn=>{queue.push(fn);return queue.length};const clearTimeout=()=>{};
const reducedMotionPreferred=()=>true;
const target=id=>({hidden:false,isConnected:true,scrollIntoView:()=>moves.push(id)});
"""+fn+"""
const a=target('old'),b=target('new');scrollTarget(a,60);scrollTarget(b,0);
queue.forEach(fn=>fn());assert.deepEqual(moves,['new']);
const c=target('hidden');scrollTarget(c,60);c.hidden=true;queue.at(-1)();assert.deepEqual(moves,['new']);
const d=target('detached');scrollTarget(d,60);d.isConnected=false;queue.at(-1)();assert.deepEqual(moves,['new']);
""")

    def test_tablet_shortcut_open_is_idempotent_and_only_one_scroll_is_requested(self):
        fn=NAV[NAV.index('  function openTabletAction('):NAV.index('  document.querySelectorAll(".tablet-manager-action")')]
        self.js("""
const VALID_TABLET_TARGETS=new Set(['v20live']);const VALID_TABLET_CLICKS=new Set(['v20issues']);
let opens=[],moves=[],actions=0,legacyClicks=0;
const nodes={v20live:{id:'v20live'},v20issues:{click:()=>actions++}};
const safeTarget=id=>nodes[id]||null;
const document={getElementById:()=>null,querySelectorAll:()=>[{dataset:{updateTarget:'v20live'},click:()=>legacyClicks++}]};
const window={TCGUpdatePanels:{open:(id,scroll)=>{opens.push([id,scroll]);return true}}};
const scrollTarget=(node,delay)=>moves.push([node.id,delay]);
"""+fn+"""
const button={dataset:{tabletTarget:'v20live',tabletClick:'v20issues'}};
assert.equal(openTabletAction(button),true);assert.equal(openTabletAction(button),true);
assert.deepEqual(opens,[['v20live',false],['v20live',false]]);assert.equal(legacyClicks,0);
assert.equal(actions,2);assert.deepEqual(moves,[['v20live',60],['v20live',60]]);
const invalid={dataset:{tabletTarget:'v20live',tabletClick:'unknown'}};
assert.equal(openTabletAction(invalid),false);assert.equal(opens.length,2);assert.equal(actions,2);
""")

    def test_queued_native_details_toggle_cannot_erase_programmatic_feature_selection(self):
        begin=NAV.index('  function selectCategory(')
        end=NAV.index('  function activateTopPanel(',begin)
        block=NAV[begin:end]
        self.js("""
let pending=[],activeCategory=null,syncing=false,detailVisible=false;
function category(id){let open=false;const listeners={};return {id,get open(){return open},set open(v){if(v!==open){open=v;pending.push(()=>listeners.toggle?.())}},addEventListener(k,fn){listeners[k]=fn}}}
const a=category('box'),b=category('tablet'),categories=[a,b];
const updateCategoryStatus=()=>{};const setCategoryContent=c=>{activeCategory=c;detailVisible=false};
"""+block+"""
selectCategory(a);detailVisible=true;
while(pending.length)pending.shift()();
assert.equal(detailVisible,true,'queued details toggle must not hide the selected feature');
assert.equal(activeCategory,a);
b.open=true;while(pending.length)pending.shift()();
assert.equal(activeCategory,b);assert.equal(detailVisible,false);
b.open=false;while(pending.length)pending.shift()();assert.equal(activeCategory,null);
""")

    def test_update_panel_open_close_and_manual_toggle_keep_accessible_state(self):
        start=INDEX.index(' const buttons=[...document.querySelectorAll(".update-menu-btn")];')
        end=INDEX.index('document.querySelectorAll(".update-panel-close")',start)
        script=INDEX[start:end]
        self.js("""
let queue=new Map(),next=0,scrolled=[];
const setTimeout=fn=>{queue.set(++next,fn);return next};const clearTimeout=id=>queue.delete(id);
function node(id,hidden=false){const classes=new Set(hidden?['hidden']:[]);return {id,dataset:{updateTarget:id},attrs:{},listeners:{},classList:{add:x=>classes.add(x),remove:x=>classes.delete(x),contains:x=>classes.has(x)},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,v){this.listeners[k]=v},scrollIntoView(){scrolled.push(id)}}}
const a=node('a',true),b=node('b',true),ba=node('a'),bb=node('b');const window={};
const document={getElementById:id=>({a,b}[id]||null),querySelectorAll:s=>s==='.update-menu-btn'?[ba,bb]:[a,b]};
"""+script+"""
assert.equal(window.TCGUpdatePanels.open('a',false),true);
assert.equal(window.TCGUpdatePanels.open('a',false),true);assert.equal(a.classList.contains('hidden'),false);
assert.equal(ba.attrs['aria-expanded'],'true');assert.equal(queue.size,0);
window.TCGUpdatePanels.open('b');assert.equal(a.classList.contains('hidden'),true);assert.equal(b.classList.contains('hidden'),false);
assert.equal(queue.size,1);window.TCGUpdatePanels.close();assert.equal(queue.size,0);
assert.equal(bb.attrs['aria-expanded'],'false');assert.equal(b.classList.contains('hidden'),true);
ba.listeners.click();assert.equal(a.classList.contains('hidden'),false);ba.listeners.click();assert.equal(a.classList.contains('hidden'),true);
assert.equal(window.TCGUpdatePanels.open('unknown'),false);assert.deepEqual(scrolled,[]);
""")

    def test_image_library_is_a_managed_destination_without_duplicate_static_id(self):
        self.assertEqual(INDEX.count('id="tcgImageLibrarySurface"'),1)
        self.assertIn('id="boxImageLibraryOpen" aria-controls="tcgImageLibrarySurface"',INDEX)
        images=(ROOT/'tablet_image_library_v1.js').read_text()
        self.assertIn('if(imageSurface)imageSurface.append(manager);',images)
        fn=NAV[NAV.index('  function showManagedTarget('):NAV.index('  registerLegacyAdvancedTargets();')]
        self.js("""
const target={id:'images',isConnected:true,contains:t=>t===target},hidden={id:'unmanaged'};
const safeTarget=id=>({images:target,unmanaged:hidden}[id]||null);
const box={id:'box',open:false};let activeCategory=null;
const managedTargets=new Set([target]);const targetCategories=new Map([[target,box]]);
const categoryTargets=new Map([[box,new Set([target])]]);const targetSurfaces=new Map([[target,target]]);
let selected=[],shown=[],scrolled=[];const selectCategory=c=>{selected.push(c.id);c.open=true;activeCategory=c;return true};
const surfaceForTarget=t=>t;const hideManagedSurfaces=()=>{};const syncAppDockSelection=()=>{};
const document={body:{setAttribute(){}}},nav={setAttribute(){}};
const ensureFeatureToolbar=t=>shown.push(t.id);const scrollTarget=t=>scrolled.push(t.id);
"""+fn+"""
assert.equal(openTarget('images'),true);assert.equal(openTarget('unmanaged'),false);assert.equal(openTarget('missing'),false);
assert.deepEqual(selected,['box']);assert.deepEqual(shown,['images']);assert.deepEqual(scrolled,['images']);
target.isConnected=false;assert.equal(openTarget('images'),false);
assert.deepEqual(selected,['box']);assert.deepEqual(shown,['images']);assert.deepEqual(scrolled,['images']);
""")

    def test_feature_search_includes_preserved_advanced_image_action(self):
        shell=(ROOT/'ui_app_shell_v272.js').read_text()
        fn=shell[shell.index('  function filterFeatures('):shell.index('  function clearSearch(')]
        self.js("""
const normalize=x=>String(x||'').trim().toLowerCase();const searchableText=x=>normalize(x?.textContent);
function node(text){const attrs=new Set();return {textContent:text,toggleAttribute:(k,on)=>on?attrs.add(k):attrs.delete(k),hasAttribute:k=>attrs.has(k),removeAttribute:k=>attrs.delete(k)}}
const resetNode=(n,a)=>n.removeAttribute(a);
const base=node('BOX 지식베이스'),image=node('태블릿 이미지·수집');
const advanced={open:false,querySelectorAll:()=>[image]};const summary=node('BOX HIT');
const category=node('BOX');category.open=false;
category.querySelectorAll=s=>s==='.feature-shortcut'?[base]:s==='.feature-advanced-shortcut'?[image]:[];
category.querySelector=s=>s==='summary'?summary:advanced;
const categories=[category],clear={disabled:true},status={dataset:{}};
"""+fn+"""
let r=filterFeatures('이미지');assert.equal(r.visibleCategories,1);assert.equal(r.visibleShortcuts,1);
assert.equal(base.hasAttribute('data-ui-filter-hidden'),true);assert.equal(image.hasAttribute('data-ui-filter-hidden'),false);assert.equal(advanced.open,true);
r=filterFeatures('');assert.equal(r.visibleShortcuts,2);assert.equal(base.hasAttribute('data-ui-filter-hidden'),false);assert.equal(clear.disabled,true);
""")

if __name__=='__main__':unittest.main()
