"use strict";
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ui = require("../../docs/tablet/v679/tablet_unified_dashboard_v679.js");

const trusted = { source_grade: "official", source: "https://www.pokemon.com/us/pokemon-news" };
function event(fields={}) {
  return { name_ko: "공식 카드 행사", game: "pokemon", region: "KR", category: "promo", ...trusted, ...fields };
}
function renderedDate(row) {
  const r = ui.normalize(null, {items:[row]}).find(x => x.group==="event");
  assert.ok(r,"event must be present");
  return r;
}

test("confirmed day and start-only labels preserve correct semantics", () => {
  const normal=renderedDate(event({start_date:"2026-10-25", date_precision:"day"}));
  assert.equal(normal.date, "2026-10-25");
  assert.equal(normal.dateDisplay, "기록된 날짜 · 2026-10-25");
  const starts=renderedDate(event({start_date:"2026-09-01",date_precision:"start-only"}));
  assert.equal(starts.dateDisplay,"시작일 · 2026-09-01");
  const legacy=renderedDate(event({start_date:"2026-10-09"}));
  assert.equal(legacy.dateDisplay,"기록된 날짜 · 2026-10-09");
});

test("tracking and unannounced dates never become displayed calendar dates", () => {
  for (const attrs of [
    {tracking_only:true,date_precision:"day"},
    {tracking_only:false,date_precision:"unannounced"},
    {tracking_only:true,date_precision:"unannounced"},
  ]) {
    const row=renderedDate(event({...attrs,start_date:"2026-08-23",date_label:"개봉일 공식 미발표"}));
    assert.equal(row.date,"");
    assert.match(row.dateDisplay,/미발표 · 추적 중/);
    assert.doesNotMatch(row.dateDisplay,/2026-08-23/);
  }
});

test("month and season placeholders never claim precise release day", () => {
  for (const precision of ["month","season"]) {
    const row=renderedDate(event({start_date:"2027-02-01",date_precision:precision,date_label:"정확한 날짜 미발표"}));
    assert.equal(row.date,"");
    assert.match(row.dateDisplay,/날짜 미발표/);
    assert.doesNotMatch(row.dateDisplay,/2027-02-01/);
  }
});

test("unknown precision, malformed date, and nonofficial source fail closed", () => {
  for (const attrs of [
    {date_precision:"quarter", start_date:"2026-08-23"},
    {date_precision:"day", start_date:"2026-02-30"},
    {date_precision:"day", start_date:"2026-13-99"},
    {date_precision:"day", start_date:"2026-08-23",source_grade:"unverified"},
    {date_precision:"day", start_date:"2026-08-23",source:"http://invalid.example"}
  ]) {
    const row=renderedDate(event(attrs));
    assert.equal(row.date,"");
    assert.doesNotMatch(row.dateDisplay,/2026-08-23|2026-02-30|2026-13-99/);
  }
});

test("historical real promo feed: every unannounced tracking row has no shown date", () => {
  const content=JSON.parse(fs.readFileSync(path.resolve(__dirname,"../../promo_events.json"),"utf8"));
  const items=content.items.filter(r=>r.date_precision==="unannounced");
  assert.ok(items.length>=8,"the known evidence set must not disappear silently");
  const normalized=ui.normalize(null,{items:content.items});
  const byName=new Map(normalized.filter(r=>r.group==="event").map(r=>[r.name,r]));
  for (const eventRow of items) {
    const row=byName.get(eventRow.name_ko||eventRow.name_native||eventRow.title);
    assert.ok(row,"known unannounced event must be in catalog");
    assert.equal(row.date,"");
    assert.match(row.dateDisplay,/미발표/);
  }
  const season=normalized.find(r=>r.name.includes("한국 나루토 카드게임 행사"));
  assert.ok(season);
  assert.equal(season.date,"");
});

test("forked UI only emits text safely and preserves China combined filter",()=>{
  assert.equal(ui.safeLink("javascript:alert(1)"),"");
  const cn=ui.filterRows([
    {group:"card",region:"CN-S",game:"pokemon",name:"간체",kind:"CARD",meta:{}},
    {group:"card",region:"CN-T",game:"pokemon",name:"번체",kind:"CARD",meta:{}}
  ],{country:"CN"});
  assert.equal(cn.length,2);
  assert.equal(ui.eventDate({date_precision:"unannounced",date_label:"<img src=x onerror=alert(1)>"},true).date,"");
});
