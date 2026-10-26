"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path");
const mod=require("../../docs/tablet/v679/tablet_unified_dashboard_v679.js");
const ROOT=path.resolve(__dirname,"../..");
const event=(other={})=>({
 game:"포켓몬 카드",region:"JP",category:"collab",name_ko:"공식 일정",
 source_grade:"official",source:"https://www.pokemon-card.com/info/005397.html",
 start_date:"2026-10-25",...other
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
