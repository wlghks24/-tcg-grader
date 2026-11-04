"use strict";
// Actual shell IIFE in a deterministic DOM fixture. No browser/server/network.
const assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const root = path.resolve(__dirname,"../..");
const source = fs.readFileSync(path.join(root,"index.html"),"utf8");
const features = Object.fromEntries(Array.from(source.matchAll(/href="#([^"]+)" data-feature-key="([^"]+)"/g),m => [m[2],m[1]]));
assert.equal(Object.keys(features).length,18);
const script = fs.readFileSync(path.join(root,"execution/tablet_menu_shell_v903.js"),"utf8");
let passed = 0;
function test(label, run) { run(); passed++; console.log("PASS " + label); }
function fixture(options = {}) {
  const ids = new Map(), docEvents = {}, winEvents = {}, historyWrites = [], clicks = [], opened = [];
  let stopped = 0, wide = false, doc;
  class Element {
    constructor(id="", tag="DIV") {
      this.id=id; this.tagName=tag; this.dataset={}; this.attrs={}; this.listeners={}; this.children=[];
      this.hidden=false; this.value=""; this.textContent=""; this.parentElement=null; this.isConnected=true;
      this.childNodes=[{textContent:id}]; this.classList={contains:c => this.classes?.includes(c) || false};
    }
    setAttribute(k,v) { this.attrs[k]=String(v); }
    getAttribute(k) { return this.attrs[k] ?? null; }
    removeAttribute(k) { delete this.attrs[k]; }
    addEventListener(k,f) { (this.listeners[k] ||= []).push(f); }
    emit(k,event={}) { event.target ||= this; for (const f of this.listeners[k] || []) f(event); }
    replaceChildren(...children) { this.children=children; }
    focus() { doc.activeElement=this; }
    getClientRects() { return [1]; }
    scrollIntoView() { this.scrolled=true; }
    querySelector() { return null; }
    querySelectorAll(selector) {
      if (this.id === "tcg903-drawer") return selector === "a[href],button,summary" ? [ids.get("tcg903-close"),...menuLinks] : menuLinks;
      if (this.id === "tcg903-countries") return countries;
      return [];
    }
    closest(selector) {
      if (selector === "a[href]") return this.tagName === "A" ? this : null;
      if (selector === "[data-tcg903-country]") return Object.hasOwn(this.dataset,"tcg903Country") ? this : null;
      if (selector === ".app-feature-back,.app-feature-collapse") return this.oldBack ? this : null;
      if (selector === "#tcg903-grid") return this.inGrid ? ids.get("tcg903-grid") : null;
      if (selector === "#featureCategories") { let p=this; while(p) { if(p.id === "featureCategories") return p; p=p.parentElement; } }
      return null;
    }
    click() { if (this.original) clicks.push(this.dataset.featureKey); else this.emit("click",event(this)); }
  }
  function add(id,tag) { const e=new Element(id,tag); ids.set(id,e); return e; }
  const body=add("body","BODY"); body.dataset.tcg903View="home";
  for(const id of ["config","drawer","toggle","backdrop","close","home","events","title","status","cards","grid","count","page","prev","next","query","game","kind","countries","collect","refresh","job","advanced"]) add("tcg903-"+id);
  const originalLinks=Object.entries(features).map(([key,target]) => {
    if(!ids.has(target)) add(target,"SECTION").parentElement=body;
    const a=new Element("original-"+key,"A"); a.original=true; a.classes=["feature-shortcut"]; a.dataset.featureKey=key; return a;
  });
  const category=add("featureCategories","SECTION"); category.parentElement=body;
  const childCategory=add("migrationSection2","DETAILS"); childCategory.parentElement=category;
  add("out","SECTION").hidden=true; add("simpleGradeResult","SECTION").hidden=true;
  const advanced=add("advancedFixture","DETAILS"); advanced.parentElement=ids.get("precisionHub");
  const menuLinks=[new Element("menu-first","A"),new Element("menu-last","A")];
  menuLinks[0].attrs.href="/index.html?pane=home"; menuLinks[1].attrs.href="/index.html?pane=events";
  const countries=["","KR","JP","US","CN"].map(code => { const e=new Element("country-"+code,"BUTTON"); e.dataset.tcg903Country=code; return e; });
  const cards=Array.from({length:65},(_,i) => { const e=new Element("row-"+i,"ARTICLE"); e.textContent="Card "+i; e.dataset={region:["KR","JP","US","CN-S","CN-T"][i%5],game:i%2 ? "pokemon" : "onepiece",kind:i%3 ? "CARD" : "PRODUCT"}; return e; });
  ids.get("tcg903-cards").content={querySelectorAll:() => cards};
  ids.get("tcg903-config").textContent=JSON.stringify({features,targets:[...Object.values(features),"featureCategories","migrationSection2","out","simpleGradeResult","advancedFixture"],viewState:options.viewState||"COMPLETE",initial:options.initial||"home",compatibility:false});
  const location = {href:"http://127.0.0.1:8765/index.html",origin:"http://127.0.0.1:8765",assign:() => { throw Error("unexpected location navigation"); }};
  const history={pushState:(_,__,value) => { historyWrites.push(value); location.href=new URL(value,location.href).href; }};
  doc={body,readyState:"complete",activeElement:ids.get("tcg903-toggle"),getElementById:id=>ids.get(id)||null,
    querySelectorAll:s => s === ".feature-shortcut[data-feature-key]" ? originalLinks : s === "#tcg903-drawer a" ? menuLinks : [],
    addEventListener:(k,f) => { (docEvents[k] ||= []).push(f); }};
  const win={matchMedia:()=>({matches:wide}),addEventListener:(k,f)=>{(winEvents[k] ||= []).push(f);},dispatchEvent:e=>{for(const f of winEvents[e.type]||[])f(e);},tcgCameraRuntime:{stop:()=>stopped++},TCGFeatureCategoryNav:{openTarget:id=>{opened.push(id);return Object.values(features).includes(id);},closeFeatureView:()=>{}}};
  class Event { constructor(type) { this.type=type; } }
  vm.runInNewContext(script,{document:doc,window:win,location,history,URL,Event,HTMLImageElement:Element,requestAnimationFrame:f=>f(),fetch:()=>{throw Error("unexpected request");}});
  function event(target, extra={}) { return {target,button:0,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...extra}; }
  return {ids,body,win,location,historyWrites,clicks,opened,cards,countries,menuLinks,doc,stopped:()=>stopped,wide:v=>{wide=v;win.dispatchEvent(new Event("resize"));},
    route:q=>win.TCGMenuShellV903.route(new URL(q,location.href)),emit:(k,e)=>{for(const f of docEvents[k]||[])f(e);},event,grid:()=>ids.get("tcg903-grid").children};
}

test("home immediately mounts 24 card photos without opening another panel",()=>{const f=fixture();assert.equal(f.body.dataset.tcg903View,"home");assert.equal(f.grid().length,24);assert.equal(f.ids.get("tcg903-home").hidden,false);});
test("all 18 menu features invoke their original same-document shortcuts",()=>{const f=fixture();for(const key of Object.keys(features))assert.equal(f.route("/index.html?feature="+key),true);assert.deepEqual(f.clicks,Object.keys(features));assert.equal(f.body.dataset.tcg903View,"legacy");});
test("country controls group both Chinese editions and keep Korean exact",()=>{const f=fixture();f.ids.get("tcg903-countries").emit("click",f.event(f.countries[4]));assert.equal(f.ids.get("tcg903-count").textContent.startsWith("26개"),true);assert(f.grid().every(r=>r.dataset.region.startsWith("CN-")));f.ids.get("tcg903-countries").emit("click",f.event(f.countries[1]));assert.equal(f.grid().length,13);assert(f.grid().every(r=>r.dataset.region==="KR"));});
test("pagination keeps each active page at 24 and visits all 65 distinct originals",()=>{const f=fixture(),seen=[...f.grid()];f.ids.get("tcg903-next").emit("click");assert.equal(f.grid().length,24);seen.push(...f.grid());f.ids.get("tcg903-next").emit("click");assert.equal(f.grid().length,17);seen.push(...f.grid());assert.equal(new Set(seen).size,65);assert.equal(f.ids.get("tcg903-next").disabled,true);});
test("home card/BOX aliases and text filters stay on the home screen",()=>{const f=fixture();f.route("/index.html?pane=home&kind=PRODUCT");assert.equal(f.body.dataset.tcg903View,"home");assert(f.grid().every(r=>r.dataset.kind==="PRODUCT"));f.ids.get("tcg903-query").value="missing fixture";f.ids.get("tcg903-query").emit("input");assert.equal(f.grid().length,0);});
test("unknown menu targets fail without changing the URL",()=>{const f=fixture();for(const q of ["?feature=bad","?target=bad","?pane=bad","#bad"])assert.equal(f.route(q),false);assert.equal(f.historyWrites.length,0);assert(f.ids.get("tcg903-status").textContent.includes("찾지 못"));});
test("result gates open input owners and never reveal old result nodes",()=>{const f=fixture();f.route("?target=out");assert(f.opened.includes("precisionHub"));assert.equal(f.ids.get("out").hidden,true);f.route("/index.html#simpleGradeResult");assert(f.opened.includes("simpleGradeV32"));assert.equal(f.ids.get("simpleGradeResult").hidden,true);});
test("advanced details use managed ancestor and category targets reopen menu",()=>{const f=fixture();f.route("?target=advancedFixture");assert.equal(f.ids.get("advancedFixture").open,true);f.route("?target=migrationSection2");assert.equal(f.body.dataset.tcg903View,"home");assert.equal(f.body.dataset.tcg903Menu,"open");});
test("mobile Escape restores outside focus even after menu reentry",()=>{const f=fixture(),toggle=f.ids.get("tcg903-toggle");f.win.TCGMenuShellV903.menu(true);assert.equal(f.ids.get("tcg903-drawer").attrs["aria-modal"],"true");f.win.TCGMenuShellV903.menu(true);f.emit("keydown",f.event(toggle,{key:"Escape"}));assert.equal(f.doc.activeElement,toggle);assert.equal(f.ids.get("tcg903-drawer").inert,true);});
test("Tab focus trap wraps and desktop drawer is nonmodal",()=>{const f=fixture();f.win.TCGMenuShellV903.menu(true);f.menuLinks[1].focus();f.emit("keydown",f.event(f.menuLinks[1],{key:"Tab"}));assert.equal(f.doc.activeElement,f.ids.get("tcg903-close"));f.wide(true);assert.equal(f.ids.get("tcg903-drawer").attrs["aria-modal"],undefined);assert.equal(f.ids.get("tcg903-drawer").inert,false);});
test("leaving camera stops it and back/popstate reuse home",()=>{const f=fixture();f.route("?feature=auto-grade");const before=f.stopped();f.route("?pane=home");assert(f.stopped()>before);f.location.href="http://127.0.0.1:8765/index.html?pane=events";const n=f.historyWrites.length;f.win.dispatchEvent({type:"popstate"});assert.equal(f.body.dataset.tcg903View,"events");assert.equal(f.historyWrites.length,n);});
test("unavailable gallery never reports a confirmed zero count",()=>{const f=fixture({viewState:"UNAVAILABLE"});assert(f.ids.get("tcg903-count").textContent.includes("읽기 보류"));assert(!f.ids.get("tcg903-count").textContent.startsWith("0개"));});
console.log("V903 offline DOM fixture: " + passed + " tests passed");
