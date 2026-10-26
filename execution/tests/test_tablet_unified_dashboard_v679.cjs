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
  event({date_precision:"start-only"}),
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
