"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const mod=require("../../docs/tablet/v679/tablet_unified_dashboard_v679.js");
const ROOT=path.resolve(__dirname,"../..");
const event=(other={})=>({
 game:"포켓몬 카드",region:"JP",category:"collab",name_ko:"공식 일정",
 source_grade:"official",source:"https://www.pokemon-card.com/info/005397.html",
 start_date:"2026-10-25",link_status:"정상",...other
});
test("tracking placeholders and unannounced events never show a confirmed date",()=>{
 for(const e of [
  event({date_precision:"unannounced",date_label:"공식 미발표",tracking_only:true}),
  event({date_precision:"day",tracking_only:true}),
  event({date_precision:"unannounced",tracking_only:false}),
  event({date_precision:"unknown"}),
  event()
 ]){
  const row=mod.normalize(null,{items:[e]})[0];
  assert.equal(row.date,"");
  assert.ok(row.dateNote);
 }
});
test("actual promo feed never promotes unannounced date placeholders",()=>{
 const data=JSON.parse(fs.readFileSync(path.join(ROOT,"promo_events.json"),"utf8"));
 const items=data.items.filter(e=>e.date_precision==="unannounced"&&e.start_date);
 assert.ok(items.length>0);
 for(const e of items){
  const date=mod.eventSchedule(e);
  assert.equal(date.date,"",e.name_ko);
  assert.ok(date.dateNote,e.name_ko);
 }
});
test("day with verified precision survives, invalid day and coarse precision fail closed",()=>{
 assert.equal(mod.eventSchedule(event({date_precision:"day"})).date,"2026-10-25");
 assert.equal(mod.normalize(null,{items:[event({date_precision:"day"})]})[0].date,"2026-10-25");
 for(const value of [
  event({date_precision:"day",start_date:"2026-02-30"}),
  event({date_precision:"day",start_date:"2026-99-99"}),
  event({date_precision:"month"}),
  event({date_precision:"season"}),
  event({date_precision:"unannounced",date_label:"<script>alert(1)</script>"}),
 ])assert.equal(mod.eventSchedule(value).date,"");
});
test("read-only V679 reuses frozen V676 CSS and preserves local CSP",()=>{
 const html=fs.readFileSync(path.join(ROOT,"docs/tablet/v679/tablet_unified_dashboard_v679.html"),"utf8");
 assert.match(html,/href="..\/v676\/tablet_unified_dashboard_v676\.css"/);
 assert.match(html,/src="\.\/tablet_unified_dashboard_v679\.js"/);
 assert.match(html,/img-src 'self'; connect-src 'self'/);
 assert.match(html,/id="tcg-v676"/);
});

test("source and date proof must agree before showing a confirmed public event day",()=>{
 for(const item of [
  event({date_precision:"day",source_grade:"social"}),
  event({date_precision:"day",source_grade:"candidate"}),
  event({date_precision:"day",source:"https://evil.example/events/1"}),
  event({date_precision:"day",source:"javascript:alert(1)"}),
  event({date_precision:"day",link_status:"네트워크 지연 · 재확인 필요"}),
  event({date_precision:"day",link_status:"404"}),
 ]){
  const evidence=mod.eventSchedule(item);
  assert.equal(evidence.date,"",JSON.stringify(item));
  assert.match(evidence.dateNote,/재확인/);
  assert.equal(mod.normalize(null,{items:[item]})[0].date,"");
 }
});
test("an official start-only date stays start-only and never fabricates an end date",()=>{
 const item=event({date_precision:"start-only",start_date:"2026-11-12",link_status:"정상"});
 const e=mod.eventSchedule(item);
 assert.equal(e.date,"2026-11-12");
 assert.match(e.dateNote,/종료일 미확인/);
 assert.equal(mod.normalize(null,{items:[item]})[0].dateNote,e.dateNote);
});
test("unannounced tracking and impossible dates stay unknown despite forged labels",()=>{
 for(const item of [
  event({date_precision:"day",start_date:"2026-02-29"}),
  event({date_precision:"day",start_date:"2026-13-02"}),
  event({date_precision:"day",start_date:"2026-00-13"}),
  event({date_precision:"start-only",start_date:"2026-02-30"}),
  event({date_precision:"unannounced",date_label:"<img src=x onerror=alert(1)>"}),
  event({date_precision:"day",tracking_only:true,date_label:"2026-11-12"}),
 ])assert.equal(mod.eventSchedule(item).date,"");
});
test("unverified month and season social hints never become official dates or schedule labels",()=>{
 for(const precision of ["month","season","unannounced"]){
  const item=event({date_precision:precision,date_label:"공식일정 확인됨",source_grade:"social"});
  const v=mod.eventSchedule(item);
  assert.equal(v.date,"");
  assert.doesNotMatch(v.dateNote,/공식일정 확인됨/);
 }
});

test("ASIA and GLOBAL events remain visible without acquiring a country printing",()=>{
 const rows=mod.normalize(null,{items:[
  event({name_ko:"아시아 행사",region:"ASIA"}),
  event({name_ko:"글로벌 행사",region:"GLOBAL"}),
  event({name_ko:"중국 행사",region:"CN-T"}),
 ]});
 assert.deepEqual(rows.map(x=>x.region),["ASIA","GLOBAL","CN-T"]);
 assert.equal(mod.filterRows(rows,{country:"ALL",group:"event"}).length,3);
 assert.deepEqual(mod.filterRows(rows,{country:"CN"}).map(x=>x.region),["CN-T"]);
 for(const country of ["KR","JP","US"])
  assert.equal(mod.filterRows(rows,{country}).length,0,country);
 const feed=JSON.parse(fs.readFileSync(path.join(ROOT,"promo_events.json"),"utf8"));
 const regional=feed.items.filter(x=>["ASIA","GLOBAL"].includes(x.region));
 assert.ok(regional.length>0);
 const actual=mod.normalize(null,{items:regional});
 assert.equal(actual.length,regional.length,"existing cross-region canonical events must remain visible");
 assert.ok(actual.every(x=>x.group==="event" && ["ASIA","GLOBAL"].includes(x.region)));
});

test("marketplace links, another game's official host and unknown source health cannot prove dates",()=>{
 const baseline=event({date_precision:"day"});
 assert.equal(mod.safeLink("https://ebay.com/listing/123"),"https://ebay.com/listing/123");
 for(const other of [
  {source:"https://ebay.com/listing/123"},
  {game:"나루토 카드"}, {game:"other"}, {game:"unverified pokemon fan game"},
  {source:"https://unknown.pokemon-card.com/info/005397.html"},
  {source:"https://www.pokemon-card.com.attacker.invalid/info/005397.html"},
  {source:"https://user@www.pokemon-card.com/info/005397.html"},
  {source:"https://www.pokemon-card.com:8443/info/005397.html"},
  {source:"http://www.pokemon-card.com/info/005397.html"},
  {source:"https://www.pokemon-card.com/info/005397.html#forged"},
  {source:"https://www.pokemon-card.com/../info/005397.html"},
  {source:"not a URL"}, {link_status:undefined}, {link_status:"UNKNOWN"},
  {link_status:"DEGRADED"}, {link_status:"301 redirect"},
  {link_statuses:{source:"403"}}, {source_grade:"social"},
 ]){
  const row={...baseline,...other};
  assert.equal(mod.officialEventSource(row),"",JSON.stringify(other));
  assert.equal(mod.eventSchedule(row).date,"",JSON.stringify(other));
  const normalized=mod.normalize(null,{items:[row]})[0];
  assert.match(normalized.sourceState,/再|재확인/);
 }
 // Link permission does not confer official evidence on a market listing.
 const listing=mod.normalize(null,{items:[{...baseline,source:"https://ebay.com/listing/123"}]})[0];
 assert.equal(listing.source,"https://ebay.com/listing/123");
 assert.equal(listing.date,"");
});

test("reviewed social proof applies only to its exact publisher post, scope and source health",()=>{
 const feed=JSON.parse(fs.readFileSync(path.join(ROOT,"promo_events.json"),"utf8"));
 const post=feed.items.find(x=>x.source==="https://x.com/smg_comic/status/2081560207646441942");
 assert.ok(post);assert.equal(mod.officialEventSource(post),post.source);
 for(const other of [
  {source:post.source+"1"}, {source:"https://x.com/other/status/2081560207646441942"},
  {game:"포켓몬 카드"}, {region:"JP"}, {category:"promo"},
  {verification_source:"https://attacker.invalid/"}, {verification_source:undefined},
  {event_scope:"tcg_tournament"}, {link_statuses:{source:"정상",verification_source:"403"}},
 ])assert.equal(mod.officialEventSource({...post,...other}),"",JSON.stringify(other));
});

test("canonical core-game web sources retain links and official provenance while new articles stay collectable",()=>{
 const feed=JSON.parse(fs.readFileSync(path.join(ROOT,"promo_events.json"),"utf8"));
 const rows=mod.normalize(null,feed);
 assert.equal(rows.length,feed.items.length);
 assert.equal(rows.filter(x=>x.source).length,feed.items.length);
 for(const item of feed.items.filter(x=>["포켓몬 카드","원피스 카드","나루토 카드"].includes(x.game)))
  assert.equal(mod.officialEventSource(item),item.source,item.name_ko);
 assert.equal(mod.officialEventSource(event({source:"https://pokemonkorea.co.kr/news/2/new-reviewed-article"})),
  "https://pokemonkorea.co.kr/news/2/new-reviewed-article");
 const other=feed.items.find(x=>x.region==="GLOBAL");
 assert.ok(other);assert.equal(mod.officialEventSource(other),"");
});

// A deterministic local DOM harness covers real event handlers, including
// selecting a tile before changing a filter. It is not a tablet/browser test.
class Element{
 constructor(tag){
  this.tag=tag;this.children=[];this.dataset={};this.attributes={};
  this.listeners={};this.hidden=false;
 }
 setAttribute(key,value){this.attributes[key]=value;}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 addEventListener(name,handler){this.listeners[name]=handler;}
 scrollIntoView(){}
}
function findElement(root,predicate){
 if(predicate(root))return root;
 for(const child of root.children){const found=findElement(child,predicate);if(found)return found;}
 return null;
}
test("search, category, country and game changes clear the prior selected detail",async()=>{
 const originalDocument=Object.getOwnPropertyDescriptor(globalThis,"document");
 const originalFetch=globalThis.fetch;
 globalThis.document={createElement:tag=>new Element(tag)};
 globalThis.fetch=async url=>({ok:true,status:200,headers:{get:()=>null},json:async()=>
  url==="/promo_events.json"?{items:[event({name_ko:"선택한 행사"})]}:
  {ok:true,version:46,source_catalog:[],local_catalog:[],catalog_matches:[]}});
 try{
  for(const change of ["search","category","country","game"]){
   const mount=new Element("main");mod.start(mount);
   await new Promise(resolve=>setImmediate(resolve));
   const findClass=name=>findElement(mount,x=>x.className===name);
   const tile=findClass("v676-tile"),detail=findClass("v676-detail");
   assert.ok(tile,change);tile.listeners.click();
   assert.equal(detail.hidden,false,change);
   assert.ok(detail.children.length>0,change);
   if(change==="search"){
    const input=findElement(mount,x=>x.tag==="input");
    input.value="일치하는 자료 없음";input.listeners.input();
   }else{
    const target=change==="category"?"v676-tabs":change==="country"?"v676-countries":"v676-games";
    findClass(target).children[change==="game"?2:1].listeners.click();
   }
   assert.equal(detail.hidden,true,change);
   assert.equal(detail.children.length,0,change);
   assert.equal(findClass("v676-grid").children[0].className,"v676-empty",change);
  }
 }finally{
  if(originalDocument)Object.defineProperty(globalThis,"document",originalDocument);
  else delete globalThis.document;
  globalThis.fetch=originalFetch;
 }
});


test("learning panel keeps stored, verified, missing and unknown counts distinct",()=>{
 const snapshot={schema:"tcg-tablet-learning-advisor/v676",mode:"READ_ONLY_NO_TRAINING",
  models:{query:{stored_labels:315,eligible_labels:6,labels_missing:994,positive_missing:94,negative_missing:100},
          job:{stored_labels:600,eligible_labels:600,labels_missing:400,positive_missing:0,negative_missing:0}},
  image_training:{requires_verified_raw_photos:true}};
 const fields=Object.fromEntries(mod.learningSummary(snapshot));
 assert.match(fields["검색 Query 누적"],/315개 저장 · 6개 검증/);
 assert.match(fields["검색 Query 부족"],/994개 · 양성 94 \/ 음성 100개/);
 assert.match(fields["수집 Job 부족"],/400개/);
 assert.match(fields["사진 학습"],/추가 필요/);
 assert.match(fields["자동 재검사"],/실행 여부는 별도 확인/);
 assert.match(mod.learningSummary(null)[0][1],/부족량 미확인/);
 const malformed={...snapshot,models:{query:{stored_labels:true,eligible_labels:-1,labels_missing:"0"}},image_training:{}};
 for(const [label,value] of mod.learningSummary(malformed)){
  if(label!=="자동 재검사")assert.match(value,/미확인/);
 }
});

test("failed learning status does not prevent gallery load or fabricate zero remaining",async()=>{
 const originalDocument=Object.getOwnPropertyDescriptor(globalThis,"document"),originalFetch=globalThis.fetch;
 globalThis.document={createElement:tag=>new Element(tag)};
 globalThis.fetch=async url=>{
  if(url==="/api/verified-learning-gaps")throw Error("offline");
  return {ok:true,status:200,headers:{get:()=>null},json:async()=>url==="/promo_events.json"?
   {items:[event({name_ko:"행사 로딩 지속"})]}:{ok:true,version:46,source_catalog:[],local_catalog:[],catalog_matches:[]}};
 };
 try{
  const mount=new Element("main");mod.start(mount);await new Promise(resolve=>setImmediate(resolve));
  const panel=findElement(mount,x=>x.attributes["aria-label"]==="학습 데이터 누적과 부족량");
  assert.ok(panel);assert.match(panel.children[1].textContent,/조회 실패.*부족량 미확인/);
  assert.ok(findElement(mount,x=>x.className==="v676-tile"));
 }finally{
  if(originalDocument)Object.defineProperty(globalThis,"document",originalDocument);else delete globalThis.document;
  globalThis.fetch=originalFetch;
 }
});
