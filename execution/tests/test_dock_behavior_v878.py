"""Execute the complete navigation IIFE in a deterministic local DOM fixture.

This tests navigation state and bounded work, not browser layout/device speed.
"""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm');
let created = 0, scrolled = 0, timerId = 0;
const timers = new Map();
class Element {
  constructor(tag='div', id='') {
    created++; this.tagName = tag.toUpperCase(); this.id = id;
    this.dataset = {}; this.attrs = {}; this.children = []; this.listeners = {};
    this.hidden = false; this.open = false; this.isConnected = true;
    this.className = ''; this.textContent = '';
    this.classList = {
      add: (...names) => { this.className += ' ' + names.join(' '); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter(n=>!names.includes(n)).join(' '); },
      contains: name => this.className.split(/\s+/).includes(name),
    };
  }
  setAttribute(k,v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k === 'href' ? (this.href || null) : (this.attrs[k] ?? null); }
  removeAttribute(k) { delete this.attrs[k]; }
  append(...nodes) { for (const n of nodes) { n.parentElement = this; this.children.push(n); } }
  insertBefore(n) { n.parentElement = this; this.children.unshift(n); }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  addEventListener(k,fn) { (this.listeners[k] ||= []).push(fn); }
  click() { for (const fn of this.listeners.click || []) fn({preventDefault(){}}); }
  matches(selector) {
    if (selector === 'section') return this.tagName === 'SECTION';
    if (selector === 'a[data-dock-key]') return this.tagName === 'A' && 'dockKey' in this.dataset;
    if (selector.startsWith('.feature-shortcut')) return this.classList.contains('feature-shortcut');
    if (selector.startsWith('.')) return this.classList.contains(selector.slice(1));
    return this.tagName.toLowerCase() === selector;
  }
  querySelectorAll(selector) { return this.children.flatMap(n=>[...(n.matches(selector)?[n]:[]),...n.querySelectorAll(selector)]); }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parentElement?.closest(selector) || null; }
  contains(target) { return this === target || this.children.some(n=>n.contains(target)); }
  scrollIntoView() { scrolled++; }
  focus() {}
}
const body = new Element('body'), head = new Element('head');
const document = {
  body, head, createElement: tag=>new Element(tag),
  getElementById(id) { return [body,head,...body.querySelectorAll('*'),...head.querySelectorAll('*')].find(n=>n.id===id) || null; },
  querySelectorAll: sel=>body.querySelectorAll(sel),
};
// '*' is used only by the fixture's ID lookup, never by the production script.
const matches = Element.prototype.matches;
Element.prototype.matches = function(sel) { return sel === '*' || matches.call(this,sel); };
const nav = new Element('nav','featureCategories'); body.append(nav);
const records = [
  ['grading','simpleGradeV32'], ['market','market12section'],
  ['news','releaseBoard'], ['purchase','releaseBoard'],
  ['tablet','tabletManagerHub'], ['box','box12section'],
];
const shortcuts = {};
for (const [categoryKey,id] of records) {
  const category = new Element('details'); category.className = 'feature-category';
  category.dataset.categoryKey = categoryKey; category.append(new Element('summary'));
  const link = new Element('a'); link.className = 'feature-shortcut'; link.href = '#'+id; link.textContent=id;
  if(id==='releaseBoard') link.dataset.featureOpenPanel=categoryKey==='news'?'releasePanel':'purchasePanel';
  category.append(link); nav.append(category); shortcuts[id]=link;
  if(!document.getElementById(id)) body.append(new Element('section',id));
}
for (const id of ['releasePanel','promoPanel','purchasePanel']) {
  const tab=new Element('button'); tab.className='top-info-tab'; tab.dataset.topPanel=id;
  tab.setAttribute('aria-pressed',String(id==='releasePanel')); body.append(tab);
  const panel=new Element('div',id); panel.hidden=id!=='releasePanel'; document.getElementById('releaseBoard').append(panel);
  tab.addEventListener('click',()=>{
    document.querySelectorAll('.top-info-tab').forEach(n=>n.setAttribute('aria-pressed',String(n===tab)));
    for(const pid of ['releasePanel','promoPanel','purchasePanel']) document.getElementById(pid).hidden=pid!==id;
  });
}
const window={matchMedia:()=>({matches:true})};
const context={document,window,console,queueMicrotask:fn=>fn(),
  setTimeout:fn=>{timers.set(++timerId,fn); return timerId;},clearTimeout:id=>timers.delete(id)};
vm.runInNewContext(fs.readFileSync('feature_category_nav.js','utf8'),context);
const api=window.TCGFeatureCategoryNav;
const dock=()=>document.getElementById('tcgAppBottomDock');
const links=()=>dock().querySelectorAll('a[data-dock-key]');
const byKey=key=>links().find(n=>n.dataset.dockKey===key);
const active=()=>links().filter(n=>n.getAttribute('aria-current')==='location').map(n=>n.dataset.dockKey);
const flush=()=>{const pending=[...timers.values()];timers.clear();pending.forEach(fn=>fn());};
'''


@unittest.skipUnless(shutil.which('node'), 'Node required for local navigation execution')
class DockBehaviorTests(unittest.TestCase):
    def js(self, scenario):
        run = subprocess.run(['node', '-e', FIXTURE + scenario], cwd=ROOT,
                             capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def test_all_five_click_destinations_and_single_visible_surface(self):
        self.js(r'''
assert.equal(links().length,5);
for(const key of ['market-search','scan','purchase-finder','tablet-manager','menu']) {
  byKey(key).click(); flush(); assert.deepEqual(active(),[key]);
  const view=document.body.getAttribute('data-feature-view-active');
  assert.equal(view,key==='menu'?null:byKey(key).dataset.dockTarget);
  for(const [,id] of records) assert.equal(document.getElementById(id).hidden,id!==view);
}
''')

    def test_shortcut_and_toolbar_keep_selection_current(self):
        self.js(r'''
byKey('scan').click();
assert.equal(api.navigateShortcut(shortcuts.market12section),true);
assert.deepEqual(active(),['market-search']);
document.getElementById('market12section').querySelector('.app-feature-collapse').click();
assert.deepEqual(active(),['menu']);
''')

    def test_shared_grading_target_is_deduplicated_before_render(self):
        self.js(r'''
assert.equal(api.applyAdaptiveDock(['auto-grade','market-search','tablet-manager']),true);
assert.equal(byKey('auto-grade'),undefined);
byKey('scan').click(); assert.deepEqual(active(),['scan']);
api.applyAdaptiveDock(['auto-grade','market-search','tablet-manager']);
assert.deepEqual(active(),['scan']);
''')

    def test_shared_board_respects_current_panel_on_rerender_and_tab_click(self):
        self.js(r'''
const keys=['promo-event-info','market-search','tablet-manager'];
api.applyAdaptiveDock(keys); byKey('promo-event-info').click(); flush();
api.applyAdaptiveDock(keys); assert.deepEqual(active(),['promo-event-info']);
document.querySelectorAll('.top-info-tab').find(n=>n.dataset.topPanel==='purchasePanel').click();
assert.deepEqual(active(),[],'a different panel is not the dock destination');
''')

    def test_unchanged_plan_reuses_links_and_one_listener_per_link(self):
        self.js(r'''
const original=links(), before=created;
for(let i=0;i<1000;i++) assert.equal(api.createAppDock(),true);
assert.equal(created,before,'unchanged plan allocates no DOM nodes');
links().forEach((n,i)=>{assert.equal(n,original[i]);assert.equal(n.listeners.click.length,1);});
const count=scrolled; byKey('market-search').click();assert.equal(scrolled,count+1);
''')

    def test_unmanaged_or_replaced_target_fails_closed(self):
        self.js(r'''
const old=document.getElementById('market12section');
body.children.splice(body.children.indexOf(old),1,new Element('section','market12section'));
const previous=links(),count=scrolled, selection=active();
assert.equal(api.createAppDock(),false);assert.deepEqual(links(),previous);
byKey('market-search').click();assert.equal(scrolled,count);assert.deepEqual(active(),selection);
''')

    def test_latest_navigation_cancels_delayed_panel_scroll(self):
        self.js(r'''
byKey('purchase-finder').click();const count=scrolled;
byKey('scan').click();flush();assert.equal(scrolled,count+1);
assert.deepEqual(active(),['scan']);
''')

    def test_detached_target_preserves_current_screen_for_every_entrypoint(self):
        self.js(r'''
byKey('scan').click(); const count=scrolled;
document.getElementById('market12section').isConnected=false;
assert.equal(api.openTarget('market12section'),false);
assert.equal(api.navigateShortcut(shortcuts.market12section),false);
byKey('market-search').click();
assert.equal(scrolled,count);assert.deepEqual(active(),['scan']);
assert.equal(document.getElementById('simpleGradeV32').hidden,false);
assert.equal(document.body.getAttribute('data-feature-view-active'),'simpleGradeV32');
''')

    def test_shared_board_keeps_the_selected_valid_category(self):
        self.js(r'''
byKey('purchase-finder').click();
assert.equal(document.body.getAttribute('data-feature-category-active'),'purchase');
api.returnToCategory(null);
assert.equal(document.body.getAttribute('data-feature-category-active'),'purchase');
assert.equal(api.navigateShortcut(shortcuts.releaseBoard),true);
assert.equal(document.body.getAttribute('data-feature-category-active'),'purchase');
byKey('scan').click();api.openTarget('releaseBoard');
assert.equal(document.body.getAttribute('data-feature-category-active'),'news',
  'an unrelated active category must not own the next target');
''')

    def test_back_and_unrepresented_screen_do_not_leave_old_selection(self):
        self.js(r'''
byKey('scan').click();api.openTarget('box12section');assert.deepEqual(active(),[]);
api.returnToCategory(null);assert.deepEqual(active(),['menu']);
''')


if __name__ == '__main__':
    unittest.main()
