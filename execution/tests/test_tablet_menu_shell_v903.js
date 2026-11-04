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
  const ids = new Map(), docEvents = {}, winEvents = {}, historyWrites = [], clicks = [], opened = [], engineClicks = [];
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
    querySelector(selector) {
      if (this.tagName === "ARTICLE" && selector === "h2") return {textContent:this.textContent};
      if (this.id === "tcgMain" && selector.startsWith('button[data-simple-game="')) {
        const game=selector.split('"')[1];
        return ["pokemon","onepiece","naruto"].includes(game) ? {click:()=>engineClicks.push(game)} : null;
      }
      return null;
    }
    querySelectorAll(selector) {
      if (this.id === "tcg903-drawer") return selector === "a[href],button,summary" ? [ids.get("tcg903-close"),...menuLinks] : menuLinks;
      if (this.id === "tcg903-countries") return countries;
      return [];
    }
    closest(selector) {
      if (selector === "a[href]") return this.tagName === "A" ? this : null;
      if (selector === "article[data-card-code]") {
        let p=this;
        while(p) { if(p.tagName === "ARTICLE" && Object.hasOwn(p.dataset,"cardCode"))return p; p=p.parentElement; }
        return null;
      }
      if (selector === "[data-tcg903-country]") return Object.hasOwn(this.dataset,"tcg903Country") ? this : null;
      if (selector === ".app-feature-back,.app-feature-collapse") return this.oldBack ? this : null;
      if (selector === "main.app") { let p=this;while(p){if(p.id === "tcgMain")return p;p=p.parentElement;}return null;}
      if (selector === "#tcg903-grid") return this.inGrid ? ids.get("tcg903-grid") : null;
      if (selector === "#featureCategories") { let p=this; while(p) { if(p.id === "featureCategories") return p; p=p.parentElement; } }
      return null;
    }
    click() { if (this.original) clicks.push(this.dataset.featureKey); else this.emit("click",event(this)); }
  }
  function add(id,tag) { const e=new Element(id,tag); ids.set(id,e); return e; }
  const body=add("body","BODY"); body.dataset.tcg903View="home";
  const app=add("tcgMain","MAIN");app.parentElement=body;
  for(const id of ["tcg904-workspace-head","tcg904-workspace-title","tcg904-selected-card"]){const e=add(id);e.parentElement=app;app.children.push(e);}
  for(const id of ["config","drawer","toggle","backdrop","close","home","events","title","status","cards","grid","count","empty","page","prev","next","query","game","kind","countries","collect","refresh","job","advanced"]) add("tcg903-"+id);
  const originalLinks=Object.entries(features).map(([key,target]) => {
    if(!ids.has(target)){const e=add(target,"SECTION");e.parentElement=app;app.children.push(e);}
    const a=new Element("original-"+key,"A"); a.original=true; a.classes=["feature-shortcut"]; a.dataset.featureKey=key; return a;
  });
  const category=add("featureCategories","SECTION"); category.parentElement=body;
  const childCategory=add("migrationSection2","DETAILS"); childCategory.parentElement=category;
  for(const id of ["out","simpleGradeResult"]){const e=add(id,"SECTION");e.hidden=true;e.parentElement=app;app.children.push(e);}
  const advanced=add("advancedFixture","DETAILS"); advanced.parentElement=ids.get("precisionHub");
  const menuLinks=[new Element("menu-first","A"),new Element("menu-last","A")];
  menuLinks[0].attrs.href="/index.html?pane=home"; menuLinks[1].attrs.href="/index.html?pane=events";
  const countries=["","KR","JP","US","CN","CN-S","CN-T"].map(code => { const e=new Element("country-"+code,"BUTTON"); e.dataset.tcg903Country=code; return e; });
  const cards=Array.from({length:65},(_,i) => { const e=new Element("row-"+i,"ARTICLE"); e.textContent="Card "+i; e.dataset={region:["KR","JP","US","CN-S","CN-T"][i%5],game:i%2 ? "pokemon" : "onepiece",kind:i%3 ? "CARD" : "PRODUCT",cardCode:"CARD-"+i}; return e; });
  for (const [index,fields] of Object.entries(options.cardOverrides || {})) {
    const row=cards[Number(index)];
    assert(row,"fixture override target");
    if (fields.textContent !== undefined) row.textContent=fields.textContent;
    if (fields.dataset) Object.assign(row.dataset,fields.dataset);
  }
  ids.get("tcg903-cards").content={querySelectorAll:() => cards};
  ids.get("tcg903-config").textContent=JSON.stringify({features,targets:[...Object.values(features),"featureCategories","migrationSection2","out","simpleGradeResult","advancedFixture"],viewState:options.viewState||"COMPLETE",initial:options.initial||"home",compatibility:false,
    sourcePairs:options.sourcePairs||[["pokemon","JP"],["onepiece","US"]],
    sourceCoverageVerified:options.sourceCoverageVerified!==false});
  const location = {href:"http://127.0.0.1:8765/index.html",origin:"http://127.0.0.1:8765",assign:() => { throw Error("unexpected location navigation"); }};
  const history={pushState:(_,__,value) => { historyWrites.push(value); location.href=new URL(value,location.href).href; }};
  doc={body,readyState:"complete",activeElement:ids.get("tcg903-toggle"),getElementById:id=>ids.get(id)||null,
    querySelectorAll:s => s === ".feature-shortcut[data-feature-key]" ? originalLinks : s === "#tcg903-drawer a" ? menuLinks : [],
    addEventListener:(k,f) => { (docEvents[k] ||= []).push(f); }};
  const win={matchMedia:()=>({matches:wide}),addEventListener:(k,f)=>{(winEvents[k] ||= []).push(f);},dispatchEvent:e=>{for(const f of winEvents[e.type]||[])f(e);},tcgCameraRuntime:{stop:()=>stopped++},TCGFeatureCategoryNav:{openTarget:id=>{opened.push(id);return Object.values(features).includes(id);},closeFeatureView:()=>{}}};
  class Event { constructor(type) { this.type=type; } }
  vm.runInNewContext(script,{document:doc,window:win,location,history,URL,Event,HTMLImageElement:Element,requestAnimationFrame:f=>f(),fetch:()=>{throw Error("unexpected request");}});
  function event(target, extra={}) { return {target,button:0,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;},...extra}; }
  return {ids,body,win,location,historyWrites,clicks,opened,engineClicks,cards,countries,menuLinks,doc,stopped:()=>stopped,wide:v=>{wide=v;win.dispatchEvent(new Event("resize"));},
    route:q=>win.TCGMenuShellV903.route(new URL(q,location.href)),emit:(k,e)=>{for(const f of docEvents[k]||[])f(e);},event,grid:()=>ids.get("tcg903-grid").children};
}

test("home immediately mounts 24 card photos without opening another panel",()=>{const f=fixture();assert.equal(f.body.dataset.tcg903View,"home");assert.equal(f.grid().length,24);assert.equal(f.ids.get("tcg903-home").hidden,false);});
test("all 18 menu features stay in home/news/workspace without old-screen navigation",()=>{const f=fixture();for(const key of Object.keys(features))assert.equal(f.route("/index.html?feature="+key),true);assert.deepEqual(f.clicks,Object.keys(features).filter(k=>!["market-search","trading-catalog","box-knowledge","release-info","promo-event-info"].includes(k)));assert.equal(f.body.dataset.tcg903View,"tool");});
test("country controls group both Chinese editions and keep Korean exact",()=>{const f=fixture();f.ids.get("tcg903-countries").emit("click",f.event(f.countries[4]));assert.equal(f.ids.get("tcg903-count").textContent.startsWith("26개"),true);assert(f.grid().every(r=>r.dataset.region.startsWith("CN-")));f.ids.get("tcg903-countries").emit("click",f.event(f.countries[1]));assert.equal(f.grid().length,13);assert(f.grid().every(r=>r.dataset.region==="KR"));});
test("CN-S and CN-T have independent exact filters without mixing editions",()=>{
  const f=fixture();
  for(const [index,region] of [[5,"CN-S"],[6,"CN-T"]]){
    f.ids.get("tcg903-countries").emit("click",f.event(f.countries[index]));
    assert.equal(f.grid().length,13);
    assert(f.grid().every(row=>row.dataset.region===region));
  }
});

test("legacy V881 HTML link in original header stays in unified home instead of navigating",()=>{
  assert.match(source,/href="tablet_market_hub_v881\.html" id="tcgV881HubLink"/);
  for(const raw of ["tablet_market_hub_v881.html","/execution/tablet_market_hub_v881.html"]){
    const f=fixture();f.route("/index.html?feature=auto-grade");
    assert.equal(f.body.dataset.tcg903View,"tool");
    const anchor=f.menuLinks[0];anchor.attrs.href=raw;
    anchor.href=new URL(raw,f.location.href).href;
    const ev=f.event(anchor);f.emit("click",ev);
    assert.equal(ev.prevented,true);
    assert.equal(ev.stopped,true);
    assert.equal(f.body.dataset.tcg903View,"home");
    assert.equal(f.historyWrites.at(-1),"/index.html?pane=home");
  }
  const f=fixture(),external=f.menuLinks[0];
  external.attrs.href="https://external.example/fixture";
  external.href="https://external.example/fixture";
  const ev=f.event(external);f.emit("click",ev);
  assert.equal(ev.prevented,undefined);
  assert.equal(f.historyWrites.length,0);
});

test("unconfigured Naruto and country editions show an honest missing-collector state",()=>{
  const f=fixture(),game=f.ids.get("tcg903-game");
  game.value="naruto";game.emit("change");
  const empty=f.ids.get("tcg903-empty");
  assert.equal(f.grid().length,0);
  assert.equal(empty.hidden,false);
  assert.match(empty.textContent,/자동 사진 공급사 미연결/);
  assert.match(empty.textContent,/미구현/);
  assert.doesNotMatch(empty.textContent,/카드가 존재하지 않는다\./);
});

test("configured photo source with no rows never claims a completed collection",()=>{
  const f=fixture({sourcePairs:[["naruto","JP"]]});
  f.ids.get("tcg903-game").value="naruto";
  f.ids.get("tcg903-game").emit("change");
  f.ids.get("tcg903-countries").emit("click",f.event(f.countries[2]));
  const text=f.ids.get("tcg903-empty").textContent;
  assert.match(text,/공급사 설정은 있지만/);
  assert.match(text,/실제 수집 성공을 뜻하지 않습니다/);
  assert.doesNotMatch(text,/미구현/);
});

test("searching, partial data, source uncertainty and cleared filters never fake missing cards",()=>{
  const f=fixture(),empty=f.ids.get("tcg903-empty"),game=f.ids.get("tcg903-game");
  f.ids.get("tcg903-query").value="absent fixture";
  f.ids.get("tcg903-query").emit("input");
  assert.match(empty.textContent,/검색 조건/);
  assert.equal(empty.hidden,false);
  f.ids.get("tcg903-query").value="";
  f.ids.get("tcg903-query").emit("input");
  assert.equal(empty.hidden,true);
  game.value="naruto";game.emit("change");
  assert.equal(empty.hidden,false);
  game.value="";game.emit("change");
  assert.equal(empty.hidden,true);
  const partial=fixture({viewState:"PARTIAL_READ_ONLY"});
  partial.ids.get("tcg903-game").value="naruto";
  partial.ids.get("tcg903-game").emit("change");
  assert.match(partial.ids.get("tcg903-empty").textContent,/일부 출처/);
  assert.doesNotMatch(partial.ids.get("tcg903-empty").textContent,/미구현입니다/);
  const unverified=fixture({sourceCoverageVerified:false});
  unverified.ids.get("tcg903-game").value="naruto";
  unverified.ids.get("tcg903-game").emit("change");
  assert.match(unverified.ids.get("tcg903-empty").textContent,/공급사 상태를 확인할 수 없습니다/);
  const unavailable=fixture({viewState:"UNAVAILABLE"});
  unavailable.ids.get("tcg903-game").value="naruto";
  unavailable.ids.get("tcg903-game").emit("change");
  assert.match(unavailable.ids.get("tcg903-empty").textContent,/읽기 보류/);
  assert.doesNotMatch(unavailable.ids.get("tcg903-empty").textContent,/미구현/);
});

test("changing selected game or country never carries a stale Pokemon card into One Piece grading",()=>{
  const f=fixture(),link=f.menuLinks[0],context=f.ids.get("tcg904-selected-card");
  link.attrs.href="/index.html?feature=auto-grade";
  link.href=new URL(link.attrs.href,f.location.href).href;
  link.parentElement=f.cards[1]; // Pokemon record: only a real card click selects it
  f.emit("click",f.event(link));
  assert.match(context.textContent,/CARD-1/);
  assert.deepEqual(f.engineClicks,["pokemon"]);
  assert.equal(f.body.dataset.tcg903View,"tool");
  f.ids.get("tcg903-game").value="onepiece";
  f.ids.get("tcg903-game").emit("change");
  assert.equal(context.textContent,"");
  link.parentElement=null;
  link.attrs["data-tcg903-link"]="";
  f.emit("click",f.event(link)); // top-level tool nav, not a selected card
  assert.equal(context.textContent,"");
  assert.deepEqual(f.engineClicks,["pokemon"],"stale Pokemon mode must not be clicked");
  f.ids.get("tcg903-countries").emit("click",f.event(f.countries[2]));
  assert.equal(context.textContent,"");
});

test("unsupported registered TCG card never auto-selects a different grading engine",()=>{
  const f=fixture(),link=f.menuLinks[0],context=f.ids.get("tcg904-selected-card");
  f.cards[2].dataset.game="mtg";
  link.parentElement=f.cards[2];
  link.attrs.href="/index.html?feature=auto-grade";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  assert.match(context.textContent,/CARD-2/);
  assert.match(f.ids.get("tcg903-status").textContent,/mtg 전용 자동등급 기준 미검증/);
  assert.deepEqual(f.engineClicks,[]);
  link.parentElement=null;
  link.attrs["data-tcg903-link"]="";
  link.attrs.href="/index.html?pane=home";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  assert.equal(context.textContent,"");
  assert.equal(f.body.dataset.tcg903View,"home");
});

test("browser back clears old selected-card context even when filters are unchanged",()=>{
  const f=fixture(),link=f.menuLinks[0],context=f.ids.get("tcg904-selected-card");
  link.parentElement=f.cards[4]; // CARD: the previous fixture was a PRODUCT that must not be graded
  link.attrs.href="/index.html?feature=auto-grade";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  assert.match(context.textContent,/CARD-4/);
  f.location.href="http://127.0.0.1:8765/index.html?pane=home";
  f.win.dispatchEvent({type:"popstate"});
  assert.equal(context.textContent,"");
  assert.equal(f.body.dataset.tcg903View,"home");
});

test("market and pricing surfaces never trigger the card grading selector",()=>{
  const f=fixture(),link=f.menuLinks[0],context=f.ids.get("tcg904-selected-card");
  link.parentElement=f.cards[1]; // verified fixture Pokemon card, not a BOX
  link.attrs.href="/index.html?feature=grading-economics";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  assert.equal(f.body.dataset.tcg903View,"tool");
  assert.match(context.textContent,/CARD-1/);
  assert.deepEqual(f.engineClicks,[],"price details must not switch the grading engine");
  f.route("/index.html?feature=market-search");
  assert.equal(f.body.dataset.tcg903View,"home");
  assert.deepEqual(f.engineClicks,[],"market lookup must not switch the grading engine");
  assert.equal(f.ids.get("tcg903-query").value,"CARD-1");
});

test("BOX and unknown products cannot enter individual-card grading or grade-based pricing",()=>{
  for(const kind of ["PRODUCT","BUNDLE",""]){
    const f=fixture(),link=f.menuLinks[0],context=f.ids.get("tcg904-selected-card");
    f.cards[0].dataset.kind=kind;
    link.parentElement=f.cards[0];
    for(const feature of ["auto-grade","grading-economics"]){
      link.attrs.href="/index.html?feature="+feature;
      link.href=new URL(link.attrs.href,f.location.href).href;
      const ev=f.event(link);f.emit("click",ev);
      assert.equal(ev.prevented,true,kind+" "+feature);
      assert.equal(ev.stopped,true,kind+" "+feature);
      assert.equal(f.body.dataset.tcg903View,"home");
      assert.equal(context.textContent,"");
      assert.deepEqual(f.engineClicks,[]);
      assert.equal(f.historyWrites.length,0);
      assert.match(f.ids.get("tcg903-status").textContent,/BOX·팩·상품은 개별 카드의 등급 측정 대상이 아닙니다/);
    }
  }
});

test("PROMO cards retain explicit One Piece grading selection",()=>{
  const f=fixture(),link=f.menuLinks[0],context=f.ids.get("tcg904-selected-card");
  f.cards[0].dataset.kind="PROMO";
  f.cards[0].dataset.game="onepiece";
  link.parentElement=f.cards[0];
  link.attrs.href="/index.html?feature=auto-grade";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  assert.equal(f.body.dataset.tcg903View,"tool");
  assert.match(context.textContent,/CARD-0/);
  assert.deepEqual(f.engineClicks,["onepiece"]);
});

test("search indexes canonical metadata code even when display shows only shortened number",()=>{
  const f=fixture(),search=f.ids.get("tcg903-query");
  search.value="CARD-29";
  search.emit("input");
  assert.equal(f.grid().length,1);
  assert.equal(f.grid()[0],f.cards[29]);
  assert.equal(f.ids.get("tcg903-empty").hidden,true);
  search.value="card 29";
  search.emit("input");
  assert.equal(f.grid().length,1,"human readable name still searchable");
  assert.equal(f.grid()[0],f.cards[29]);
});

test("selected card price lookup preserves exact game edition and kind with overlapping IDs",()=>{
  const f=fixture({cardOverrides:{
    2:{dataset:{cardCode:"CARD-1"}},
    3:{dataset:{cardCode:"CARD-1"}},
    41:{dataset:{cardCode:"CARD-1"}}
  }}),link=f.menuLinks[0];
  link.parentElement=f.cards[1];
  link.attrs.href="/index.html?feature=grading-economics";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  assert.equal(f.body.dataset.tcg903View,"tool");
  f.route("/index.html?feature=market-search");
  assert.equal(f.body.dataset.tcg903View,"home");
  assert.equal(f.ids.get("tcg903-query").value,"CARD-1");
  assert.equal(f.ids.get("tcg903-game").value,"pokemon");
  assert.equal(f.ids.get("tcg903-kind").value,"CARD");
  assert.equal(f.countries[2].attrs["aria-pressed"],"true");
  assert.equal(f.countries[3].attrs["aria-pressed"],"false");
  assert.equal(f.grid().length,2,"same exact card may have multiple source entries");
  assert(f.grid().every(row=>row.dataset.game==="pokemon"&&row.dataset.region==="JP"&&row.dataset.kind==="CARD"));
  assert(f.grid().every(row=>row.dataset.cardCode==="CARD-1"),"prefix-matched other card is not a price quote");
  assert(!f.grid().includes(f.cards[11]),"CARD-11 must not match exact CARD-1 market identity");
  assert(!f.grid().includes(f.cards[2]),"other game's matching number must not leak");
  assert(!f.grid().includes(f.cards[3]),"other edition / BOX must not leak");
});

test("editing search after exact market lookup restores ordinary user search without stale identity lock",()=>{
  const f=fixture(),link=f.menuLinks[0],query=f.ids.get("tcg903-query");
  link.parentElement=f.cards[1];
  link.attrs.href="/index.html?feature=grading-economics";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  f.route("/index.html?feature=market-search");
  assert.equal(f.grid().length,1);
  query.value="CARD-11";
  query.emit("input"); // Explicit user edit clears the exact selected-card scope.
  assert.equal(f.grid().length,1);
  assert.equal(f.grid()[0],f.cards[11]);
  assert.equal(f.ids.get("tcg904-selected-card").textContent,"");
});

test("Chinese simple and traditional edition market results never cross",()=>{
  const f=fixture({cardOverrides:{
    4:{dataset:{cardCode:"DUP-CN"}},
    8:{dataset:{cardCode:"DUP-CN"}}
  }}),link=f.menuLinks[0];
  link.parentElement=f.cards[8];
  link.attrs.href="/index.html?feature=grading-economics";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  f.route("/index.html?feature=market-search");
  assert.equal(f.ids.get("tcg903-game").value,"onepiece");
  assert.equal(f.countries[5].attrs["aria-pressed"],"true");
  assert.equal(f.countries[6].attrs["aria-pressed"],"false");
  assert.equal(f.grid().length,1);
  assert.equal(f.grid()[0],f.cards[8]);
});

test("missing canonical number is an explicitly unverified named market candidate",()=>{
  const f=fixture({cardOverrides:{1:{textContent:"미확인 카드 홍련",dataset:{cardCode:""}}}}),
    link=f.menuLinks[0];
  link.parentElement=f.cards[1];
  link.attrs.href="/index.html?feature=grading-economics";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  f.route("/index.html?feature=market-search");
  assert.equal(f.ids.get("tcg903-query").value,"미확인 카드 홍련");
  assert.equal(f.ids.get("tcg903-game").value,"pokemon");
  assert.equal(f.countries[2].attrs["aria-pressed"],"true");
  assert.equal(f.grid().length,1);
  assert.equal(f.grid()[0],f.cards[1]);
  assert.match(f.ids.get("tcg903-status").textContent,/카드번호 미확인.*후보 검색/);
  assert.deepEqual(f.engineClicks,[],"unverified card number never runs grading");
});

test("BOX browse clears previous card's exact market number before product filtering",()=>{
  const f=fixture(),link=f.menuLinks[0];
  link.parentElement=f.cards[1];
  link.attrs.href="/index.html?feature=grading-economics";
  link.href=new URL(link.attrs.href,f.location.href).href;
  f.emit("click",f.event(link));
  f.route("/index.html?feature=market-search");
  assert.equal(f.ids.get("tcg903-query").value,"CARD-1");
  f.route("/index.html?feature=box-knowledge");
  assert.equal(f.ids.get("tcg903-query").value,"");
  assert.equal(f.ids.get("tcg903-kind").value,"PRODUCT");
  assert.equal(f.ids.get("tcg904-selected-card").textContent,"");
  assert(f.grid().length>0,"BOX browse must not inherit stale card search");
  assert(f.grid().every(row=>row.dataset.kind==="PRODUCT"));
});

test("pagination keeps each active page at 24 and visits all 65 distinct originals",()=>{const f=fixture(),seen=[...f.grid()];f.ids.get("tcg903-next").emit("click");assert.equal(f.grid().length,24);seen.push(...f.grid());f.ids.get("tcg903-next").emit("click");assert.equal(f.grid().length,17);seen.push(...f.grid());assert.equal(new Set(seen).size,65);assert.equal(f.ids.get("tcg903-next").disabled,true);});
test("home card/BOX aliases and text filters stay on the home screen",()=>{const f=fixture();f.route("/index.html?pane=home&kind=PRODUCT");assert.equal(f.body.dataset.tcg903View,"home");assert(f.grid().every(r=>r.dataset.kind==="PRODUCT"));f.ids.get("tcg903-query").value="missing fixture";f.ids.get("tcg903-query").emit("input");assert.equal(f.grid().length,0);});
test("unknown menu targets fail without changing the URL",()=>{const f=fixture();for(const q of ["?feature=bad","?target=bad","?pane=bad","#bad"])assert.equal(f.route(q),false);assert.equal(f.historyWrites.length,0);assert(f.ids.get("tcg903-status").textContent.includes("찾지 못"));});
test("result gates open input owners and never reveal old result nodes",()=>{const f=fixture();f.route("?target=out");assert(f.opened.includes("precisionHub"));assert.equal(f.ids.get("out").hidden,true);f.route("/index.html#simpleGradeResult");assert(f.opened.includes("simpleGradeV32"));assert.equal(f.ids.get("simpleGradeResult").hidden,true);});
test("advanced details use managed ancestor and category targets reopen menu",()=>{const f=fixture();f.route("?target=advancedFixture");assert.equal(f.ids.get("advancedFixture").open,true);f.route("?target=migrationSection2");assert.equal(f.body.dataset.tcg903View,"home");assert.equal(f.body.dataset.tcg903Menu,"open");});
test("mobile Escape restores outside focus even after menu reentry",()=>{const f=fixture(),toggle=f.ids.get("tcg903-toggle");f.win.TCGMenuShellV903.menu(true);assert.equal(f.ids.get("tcg903-drawer").attrs["aria-modal"],"true");f.win.TCGMenuShellV903.menu(true);f.emit("keydown",f.event(toggle,{key:"Escape"}));assert.equal(f.doc.activeElement,toggle);assert.equal(f.ids.get("tcg903-drawer").inert,true);});
test("Tab focus trap wraps and desktop drawer is nonmodal",()=>{const f=fixture();f.win.TCGMenuShellV903.menu(true);f.menuLinks[1].focus();f.emit("keydown",f.event(f.menuLinks[1],{key:"Tab"}));assert.equal(f.doc.activeElement,f.ids.get("tcg903-close"));f.wide(true);assert.equal(f.ids.get("tcg903-drawer").attrs["aria-modal"],undefined);assert.equal(f.ids.get("tcg903-drawer").inert,false);});
test("leaving camera stops it and back/popstate reuse home",()=>{const f=fixture();f.route("?feature=auto-grade");const before=f.stopped();f.route("?pane=home");assert(f.stopped()>before);f.location.href="http://127.0.0.1:8765/index.html?pane=events";const n=f.historyWrites.length;f.win.dispatchEvent({type:"popstate"});assert.equal(f.body.dataset.tcg903View,"events");assert.equal(f.historyWrites.length,n);});
test("unavailable gallery never reports a confirmed zero count",()=>{const f=fixture({viewState:"UNAVAILABLE"});assert(f.ids.get("tcg903-count").textContent.includes("읽기 보류"));assert(!f.ids.get("tcg903-count").textContent.startsWith("0개"));});


test("market BOX and news primary buttons never invoke original screen links",()=>{const f=fixture();for(const key of ["market-search","trading-catalog","box-knowledge"]){f.route("/index.html?feature="+key);assert.equal(f.body.dataset.tcg903View,"home");}assert.equal(f.ids.get("tcg903-kind").value,"PRODUCT");for(const key of ["promo-event-info","release-info"]){f.route("/index.html?feature="+key);assert.equal(f.body.dataset.tcg903View,"events");}assert.equal(f.clicks.length,0);});

test("workspace reserves gated results without forcing them visible",()=>{const f=fixture();f.route("?feature=auto-grade");assert.equal(f.ids.get("simpleGradeV32").attrs["data-tcg904-surface"],"true");assert.equal(f.ids.get("simpleGradeResult").attrs["data-tcg904-surface"],"true");assert.equal(f.ids.get("simpleGradeResult").hidden,true);f.route("?feature=grading-economics");assert.equal(f.ids.get("gradingEconomics").attrs["data-tcg904-surface"],"true");assert.equal(f.ids.get("simpleGradeV32").attrs["data-tcg904-surface"],undefined);});
console.log("V904 offline DOM fixture: "+passed+" tests passed");
